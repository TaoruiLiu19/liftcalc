"""工况编排：case.json → 内核 → result.json（设计 §3.1 L3）。

内核不认识数据库：机型/型钢数据由本层注入。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from liftcalc.core.errors import DataError, InputError, LiftcalcError, UnknownKindError
from liftcalc.core.result import CheckResult, ComputationResult, Verdict, summarize
from liftcalc.core.units import Q, to_quantity
from liftcalc.core.version import digest, engine_version
from liftcalc.data.repo import Repo
from liftcalc.crane import capability as crane_capability
from liftcalc.crane import select as crane_select
from liftcalc.crane.select import OutriggerLayout
from liftcalc.fea import frame2d
from liftcalc.geometry import solids as solid_lib
from liftcalc.geometry.centroid import AssemblyItem, assembly_centroid
from liftcalc.lifting.beam import BeamInput, check_beam
from liftcalc.lifting.eye import EyeGeometry, EyeLoad, EyeWeld, check_eye
from liftcalc.lifting.rigging import (
    RopeSpec,
    SelectionOption,
    SlingArrangement,
    check_rigging,
)
from liftcalc.sections import custom
from liftcalc.sections.models import SectionProps
from liftcalc.sections.outline import (
    angle_section as outline_angle,
    annulus as outline_annulus,
    box as outline_box,
    channel as outline_channel,
    circle as outline_circle,
    i_section as outline_i,
    rect as outline_rect,
    t_section as outline_t,
)
from liftcalc.sections.steel import get_section
from liftcalc.services.cases import (
    CASE_MODELS,
    BeamCase,
    CapabilityCase,
    CaseEnvelope,
    CentroidCase,
    CraneCase,
    EyeCase,
    FrameCase,
    RiggingCase,
    SectionCase,
    SectionSpec,
)

Point = tuple[float, float]


def _reject_extra_error(exc: ValidationError) -> InputError:
    return InputError("Case 结构不合法", errors=exc.errors(include_url=False))


def parse_case(data: dict[str, Any]) -> CaseEnvelope:
    kind = data.get("kind")
    if not isinstance(kind, str):
        raise InputError("case 缺少 kind 字段")
    model = CASE_MODELS.get(kind)
    if model is None:
        raise UnknownKindError(f"未知的 case 类型：{kind}", known=sorted(CASE_MODELS))
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise _reject_extra_error(exc) from exc


def _length(value: float, units: Any) -> Q:
    return to_quantity(value, units.length)


def _force(value: float, units: Any) -> Q:
    if units.force == "t":
        # pint 的 "t" 是质量单位；吨力显式换算，避免量纲歧义
        return Q(value * 9.80665, "kN")
    return to_quantity(value, units.force)


def _stress(value: float, units: Any) -> Q:
    return to_quantity(value, units.stress)


def _section_from_spec(
    spec: SectionSpec, units: Any, repo: Repo | None
) -> tuple[SectionProps, str, dict[str, Any] | None]:
    """返回 (截面特性, 数据来源说明, 原始数据行)。"""
    if spec.type == "steel":
        if repo is None:
            raise DataError("steel 截面需要数据库；请先 liftcalc data build")
        if not spec.family or not spec.designation:
            raise InputError("steel 截面必须给出 family 与 designation")
        rows = repo.sections()
        props = get_section(rows, spec.family, spec.designation)
        row = next(
            r for r in rows
            if str(r["family"]) == spec.family and str(r["designation"]) == spec.designation
        )
        has_table = all(row.get(key) for key in ("A", "Ix", "Iy"))
        origin = "型钢表值" if has_table else "由公称尺寸计算（非标准表值）"
        return props, origin, row

    def need(field: str) -> Q:
        value = getattr(spec, field)
        if value is None:
            raise InputError(f"截面类型 {spec.type} 缺少字段 {field}")
        return _length(value, units)

    if spec.type == "rect":
        return custom.rect(need("b"), need("h")), "参数化实心矩形", None
    if spec.type == "box":
        return custom.box(need("b"), need("h"), need("t")), "参数化箱型", None
    if spec.type == "round":
        diameter = spec.d_outer if spec.d_outer is not None else spec.h
        if diameter is None:
            raise InputError("截面类型 round 需要 d_outer 或 h")
        return custom.round_bar(_length(diameter, units)), "参数化圆钢（解析解）", None
    if spec.type == "pipe":
        return custom.pipe(need("d_outer"), need("d_inner")), "参数化圆管（解析解）", None
    if spec.type == "ishape":
        return custom.i_section(need("h"), need("b"), need("tw"), need("tf")), "参数化工字形", None
    if spec.type == "channel":
        return custom.channel(need("h"), need("b"), need("tw"), need("tf")), "参数化槽钢", None
    if spec.type == "t":
        return custom.t_section(need("h"), need("b"), need("tw"), need("tf")), "参数化 T 形", None
    if spec.type == "angle":
        return custom.angle_section(need("b_long"), need("b_short"), need("t")), "参数化角钢", None
    raise InputError(f"未实现的截面类型：{spec.type}")


def _outline_of(
    spec: SectionSpec, units: Any, row: dict[str, Any] | None = None
) -> list[list[Point]]:
    """为绘图提供轮廓（毫米）；不参与计算。"""
    mm_per_unit = {"mm": 1.0, "cm": 10.0, "m": 1000.0}

    def mm(field: str) -> float:
        raw = getattr(spec, field)
        if raw is None:
            raise InputError(f"绘图需要字段 {field}")
        return float(raw) * mm_per_unit[units.length]

    def outline_from_row() -> tuple[list[list[Point]], list[list[Point]]] | None:
        if row is None:
            return None
        family = str(row.get("family"))
        h = float(row.get("h") or 0.0)
        b = float(row.get("b") or 0.0)
        tw = float(row.get("tw") or 0.0)
        tf = float(row.get("tf") or 0.0)
        if family in {"H", "I"}:
            return outline_i(h, b, tw, tf)
        if family == "C":
            return outline_channel(h, b, tw, tf)
        if family == "T":
            return outline_t(h, b, tw, tf)
        if family == "L":
            return outline_angle(b, h, tw)
        if family == "PIPE":
            return outline_annulus(h, b, segments=48)
        if family == "BAR":
            return outline_circle(h, segments=48)
        return None

    try:
        if spec.type == "steel":
            built = outline_from_row()
            if built is None:
                return []
            regions, holes = built
        elif spec.type == "rect":
            regions, holes = outline_rect(mm("b"), mm("h"))
        elif spec.type == "box":
            regions, holes = outline_box(mm("b"), mm("h"), mm("t"))
        elif spec.type == "ishape":
            regions, holes = outline_i(mm("h"), mm("b"), mm("tw"), mm("tf"))
        elif spec.type == "channel":
            regions, holes = outline_channel(mm("h"), mm("b"), mm("tw"), mm("tf"))
        elif spec.type == "t":
            regions, holes = outline_t(mm("h"), mm("b"), mm("tw"), mm("tf"))
        elif spec.type == "angle":
            regions, holes = outline_angle(mm("b_long"), mm("b_short"), mm("t"))
        elif spec.type == "round":
            diameter = mm("d_outer") if spec.d_outer is not None else mm("h")
            regions, holes = outline_circle(diameter)
        elif spec.type == "pipe":
            regions, holes = outline_annulus(mm("d_outer"), mm("d_inner"))
        else:
            return []
    except (InputError, KeyError, TypeError, ZeroDivisionError):
        return []
    return [list(region) for region in regions] + [list(hole) for hole in holes]


def _section_case(case: SectionCase, repo: Repo | None) -> ComputationResult:
    props, origin, row = _section_from_spec(case.section, case.units, repo)
    data = props.as_dict()
    checks = [
        CheckResult(id="section.area", title="截面面积", value=round(data["area"], 4), unit="mm²",
                    verdict=Verdict.NA, source=origin),
        CheckResult(id="section.ix", title="惯性矩 Ix", value=round(data["ix"], 4), unit="mm⁴",
                    verdict=Verdict.NA, source=origin),
        CheckResult(id="section.iy", title="惯性矩 Iy", value=round(data["iy"], 4), unit="mm⁴",
                    verdict=Verdict.NA, source=origin),
        CheckResult(id="section.wx", title="截面模量 Wx", value=round(data["wx"], 4), unit="mm³",
                    verdict=Verdict.NA, source=origin),
        CheckResult(id="section.rx", title="回转半径 ix", value=round(data["rx"], 4), unit="mm",
                    verdict=Verdict.NA, source=origin),
    ]
    aux: dict[str, Any] = {
        "section": data,
        "outline_mm": _outline_of(case.section, case.units, row),
        "origin": origin,
        "figure": "section",
    }
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        checks=checks,
        aux=aux,
        warnings=[] if origin == "型钢表值" else [f"截面数据来源：{origin}"],
    )


def _solid_from_spec(spec_type: str, dims: dict[str, float], units: Any) -> Any:
    def length(key: str) -> Q:
        if key not in dims:
            raise InputError(f"立体 {spec_type} 缺少尺寸 {key}")
        return _length(dims[key], units)

    if spec_type == "box":
        return solid_lib.box(length("a"), length("b"), length("c"))
    if spec_type == "cylinder":
        return solid_lib.cylinder(length("d"), length("h"))
    if spec_type == "hollow_cylinder":
        return solid_lib.hollow_cylinder(length("d_outer"), length("d_inner"), length("h"))
    if spec_type == "sphere":
        return solid_lib.sphere(length("d"))
    if spec_type == "spherical_cap":
        return solid_lib.spherical_cap(length("d"), length("h"))
    if spec_type == "ellipsoid_head":
        return solid_lib.ellipsoid_head(length("d"))
    if spec_type == "cone_frustum":
        return solid_lib.cone_frustum(length("d_bottom"), length("d_top"), length("h"))
    if spec_type == "elbow":
        return solid_lib.elbow(
            length("d_outer"), length("d_inner"), length("bend_radius"),
            float(dims.get("angle_deg", 90.0)),
        )
    if spec_type == "torus":
        return solid_lib.torus(length("d"), length("bend_radius"))
    raise InputError(f"未实现的立体类型：{spec_type}")


def _centroid_case(case: CentroidCase) -> ComputationResult:
    items: list[AssemblyItem] = []
    for spec in case.solids:
        solid = _solid_from_spec(spec.type, spec.dims, case.units)
        offset = tuple(_length(value, case.units) for value in spec.offset)
        density = None if spec.density is None else Q(spec.density, "kg/m**3")
        items.append(AssemblyItem(solid=solid, offset=offset, density=density))  # type: ignore[arg-type]

    result = assembly_centroid(items)
    volume_m3 = float(result.volume.to("m**3").magnitude)
    centroid_mm = [float(coordinate.to("mm").magnitude) for coordinate in result.centroid]

    checks = [
        CheckResult(id="geo.volume", title="总体积", value=round(volume_m3, 6), unit="m³",
                    verdict=Verdict.NA, source="解析公式"),
        CheckResult(id="geo.cx", title="形心 x", value=round(centroid_mm[0], 3), unit="mm",
                    verdict=Verdict.NA, source="Σ(Vᵢxᵢ)/ΣVᵢ"),
        CheckResult(id="geo.cy", title="形心 y", value=round(centroid_mm[1], 3), unit="mm",
                    verdict=Verdict.NA, source="Σ(Vᵢyᵢ)/ΣVᵢ"),
        CheckResult(id="geo.cz", title="形心 z", value=round(centroid_mm[2], 3), unit="mm",
                    verdict=Verdict.NA, source="Σ(Vᵢzᵢ)/ΣVᵢ"),
    ]
    warnings: list[str] = []
    if result.mass is not None:
        checks.append(
            CheckResult(id="geo.mass", title="总质量", value=round(float(result.mass.to("kg").magnitude), 3),
                        unit="kg", verdict=Verdict.NA, source="Σ(Vᵢρᵢ)")
        )
    else:
        warnings.append("未给全部密度，只出几何形心，未出质量重心")

    aux: dict[str, Any] = {
        "volume_m3": volume_m3,
        "centroid_mm": centroid_mm,
        "mass_kg": None if result.mass is None else float(result.mass.to("kg").magnitude),
        "figure": "none",
    }
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        checks=checks,
        aux=aux,
        warnings=warnings,
    )


def _eye_case(case: EyeCase, repo: Repo | None) -> ComputationResult:
    fy: Q | None = None
    if case.material.fy is not None:
        fy = _stress(case.material.fy, case.units)
    elif repo is not None:
        row = repo.material(case.material.grade)
        if row.get("fy") is not None:
            fy = Q(float(row["fy"]), "MPa")
    if fy is None:
        raise DataError(
            f"无法确定 {case.material.grade} 的 fy：请在 case 里给 material.fy，或先建库"
        )

    weld = None
    if case.weld is not None:
        weld = EyeWeld(
            leg=_length(case.weld.leg, case.units),
            length=_length(case.weld.length, case.units),
            electrode=case.weld.electrode,
        )
    pin = None if case.pin is None else _length(case.pin.diameter, case.units)

    outcome = check_eye(
        geometry=EyeGeometry(
            plate_t=_length(case.geometry.plate_t, case.units),
            plate_b=_length(case.geometry.plate_b, case.units),
            plate_h=_length(case.geometry.plate_h, case.units),
            hole_d=_length(case.geometry.hole_d, case.units),
            hole_edge=_length(case.geometry.hole_edge, case.units),
        ),
        load=EyeLoad(
            design=_force(case.load.design, case.units),
            dynamic_factor=case.load.dynamic_factor,
            angle_deg=case.load.angle_deg,
        ),
        fy=fy,
        weld=weld,
        pin_diameter=pin,
    )

    verdict, governing, utilization = summarize(outcome.checks)
    warnings = list(outcome.warnings)
    if any("占位系数" in note for check in outcome.checks for note in check.notes):
        warnings.append("限值为占位系数，尚未按规范核定（见 codecheck.limits）")

    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        verdict=verdict,
        governing=governing,
        utilization=utilization,
        checks=outcome.checks,
        aux=outcome.aux,
        warnings=warnings,
    )


def _fy_of(material: Any, units: Any, repo: Repo | None) -> Q | None:
    if material.fy is not None:
        return _stress(material.fy, units)
    if repo is not None:
        row = repo.material(material.grade)
        if row.get("fy") is not None:
            return Q(float(row["fy"]), "MPa")
    return None


def _e_of(material: Any, repo: Repo | None) -> Q:
    if repo is not None:
        try:
            row = repo.material(material.grade)
            if row.get("E") is not None:
                return Q(float(row["E"]), "MPa")
        except Exception:  # 材质缺失时退回钢的常用值
            pass
    return Q(206000.0, "MPa")


def _beam_case(case: BeamCase, repo: Repo | None) -> ComputationResult:
    if case.section is not None:
        props, origin, row = _section_from_spec(case.section, case.units, repo)
        inertia = props.ix
        modulus = props.wx
        web_area: Q | None = None
        if row is not None:
            h = float(row.get("h") or 0.0)
            tw = float(row.get("tw") or 0.0)
            tf = float(row.get("tf") or 0.0)
            if tw > 0 and h - 2 * tf > 0:
                web_area = Q(tw * (h - 2 * tf), "mm**2")
    elif case.properties is not None:
        inertia = Q(case.properties.inertia, "mm**4")
        modulus = Q(case.properties.section_modulus, "mm**3")
        web_area = (
            None
            if case.properties.web_area is None
            else Q(case.properties.web_area, "mm**2")
        )
        origin = "显式给定截面特性"
    else:
        raise InputError("吊梁必须提供 section 或 properties")

    fy = _fy_of(case.material, case.units, repo)
    outcome = check_beam(
        BeamInput(
            support=case.beam.support,
            span=_length(case.beam.span, case.units),
            total_load=_force(case.beam.total, case.units),
            load_type=case.beam.load_type,
            inertia=inertia,
            section_modulus=modulus,
            e_modulus=_e_of(case.material, repo),
            web_area=web_area,
            deflection_ratio=case.beam.deflection_ratio,
            fy=fy,
        )
    )
    verdict, governing, utilization = summarize(outcome.checks)
    warnings = list(outcome.warnings)
    warnings.append(f"截面来源：{origin}")
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        verdict=verdict,
        governing=governing,
        utilization=utilization,
        checks=outcome.checks,
        aux={**outcome.aux, "origin": origin},
        warnings=warnings,
    )


def _rigging_case(case: RiggingCase) -> ComputationResult:
    options_shackle = (
        None
        if case.shackles is None
        else [SelectionOption(name=item.name, capacity=item.capacity) for item in case.shackles]
    )
    options_hook = (
        None
        if case.hooks is None
        else [SelectionOption(name=item.name, capacity=item.capacity) for item in case.hooks]
    )
    rope = (
        None
        if case.rope is None
        else RopeSpec(
            diameter=_length(case.rope.diameter, case.units),
            rated_strength=Q(case.rope.rated_strength, "MPa"),
            k_prime=case.rope.k_prime,
            safety_factor=case.rope.safety_factor,
        )
    )
    outcome = check_rigging(
        total_load=_force(case.load.total, case.units),
        arrangement=SlingArrangement(branches=case.sling.branches, angle_deg=case.sling.angle_deg),
        rope=rope,
        shackle_options=options_shackle,
        hook_options=options_hook,
    )
    verdict, governing, utilization = summarize(outcome.checks)
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        verdict=verdict,
        governing=governing,
        utilization=utilization,
        checks=outcome.checks,
        aux=outcome.aux,
        warnings=list(outcome.warnings),
    )


def _crane_case(case: CraneCase, repo: Repo | None) -> ComputationResult:
    if case.capacity_table:
        rows = [
            crane_select.CapacityRow(
                boom_len=item.boom_len, radius=item.radius, rated_load=item.rated_load
            )
            for item in case.capacity_table
        ]
        source = "case 内给定性能表"
    else:
        if repo is None or case.crane is None:
            raise DataError("未提供 capacity_table，且没有可用的机型数据（需要 --db 与 crane 参数）")
        crane = case.crane
        if not (crane.brand and crane.model and crane.config and crane.boom_len is not None):
            raise InputError("crane 需要 brand / model / config / boom_len")
        db_rows = repo.capacity(crane.brand, crane.model, crane.config, crane.boom_len)
        rows = [
            crane_select.CapacityRow(boom_len=crane.boom_len, radius=radius, rated_load=load)
            for radius, load in db_rows
        ]
        source = f"{crane.brand} {crane.model} {crane.config} {crane.boom_len:g}m"

    crane_select.check_working_region(region=case.region, fifth_outrigger=case.fifth_outrigger)
    lookup = crane_select.lookup_capacity(
        rows,
        boom_len=case.boom_len,
        radius=case.radius,
        jib_installed=case.jib_installed,
    )
    ratio = crane_select.load_ratio(
        payload=case.payload,
        hook_mass=case.hook_mass,
        rigging=case.rigging,
        dynamic_factor=case.dynamic_factor,
        rated_load=lookup.adjusted_load,
    )

    rounding_note = []
    if lookup.boom_rounded:
        rounding_note.append(f"臂长 {case.boom_len:g}→{lookup.used_boom_len:g} m")
    if lookup.radius_rounded:
        rounding_note.append(f"幅度 {case.radius:g}→{lookup.used_radius:g} m")
    rounding_text = (
        "；按说明第 7 条取下一档：" + "、".join(rounding_note) if rounding_note else "；查表精确命中"
    )

    checks = [
        CheckResult(
            id="crane.rated_load",
            title="该工况额定起重量",
            formula_id="crane.lookup",
            substituted=(
                f"臂长 {lookup.used_boom_len:g} m、幅度 {lookup.used_radius:g} m → "
                f"额定 {lookup.rated_load:g} t{rounding_text}"
            ),
            inputs={
                "boom_len": case.boom_len,
                "radius": case.radius,
                "used_boom": lookup.used_boom_len,
                "used_radius": lookup.used_radius,
            },
            value=round(lookup.rated_load, 3),
            verdict=Verdict.NA,
            unit="t",
            source=source,
            notes=list(lookup.adjustments),
        ),
        CheckResult(
            id="crane.load_ratio",
            title="吊装负荷率",
            formula_id="crane.load_ratio",
            substituted=(
                f"η = ({case.payload:g} + {case.hook_mass:g} + {case.rigging:g}×"
                f"{case.dynamic_factor:g}) / {lookup.adjusted_load:.2f}"
            ),
            inputs={
                "G": case.payload,
                "hook": case.hook_mass,
                "g": case.rigging,
                "k": case.dynamic_factor,
                "R": round(lookup.adjusted_load, 3),
            },
            value=round(ratio, 4),
            limit=case.ratio_limit,
            ratio=round(ratio / case.ratio_limit, 4) if case.ratio_limit > 0 else None,
            verdict=Verdict.PASS if ratio <= case.ratio_limit + 1e-12 else Verdict.FAIL,
            unit="—",
            source=f"负荷率上限 {case.ratio_limit:g}（TBD-核定）",
            notes=["负荷率 =（吊件 + 吊钩 + 索具×动载系数）/ 额定起重量；额定值已含吊钩吊具"],
        ),
    ]

    aux: dict[str, Any] = {
        "rated_load_t": lookup.rated_load,
        "adjusted_load_t": lookup.adjusted_load,
        "used_boom_len": lookup.used_boom_len,
        "used_radius": lookup.used_radius,
        "ratio": ratio,
        "source": source,
    }
    warnings: list[str] = []
    if rounding_note:
        warnings.append(
            "已按原厂说明第 7 条取下一档（不插值）：" + "、".join(rounding_note)
        )
    if lookup.adjustments:
        warnings.extend(lookup.adjustments)

    if case.outrigger is not None:
        layout = OutriggerLayout(
            lx=case.outrigger.lx,
            ly=case.outrigger.ly,
            ex=case.outrigger.ex,
            ey=case.outrigger.ey,
        )
        total = case.machine_mass + case.payload + case.hook_mass + case.rigging
        reactions = crane_select.outrigger_reactions(total, layout)
        worst_name = max(reactions, key=lambda key: reactions[key])
        worst = reactions[worst_name]
        checks.append(
            CheckResult(
                id="crane.outrigger",
                title="最大支腿反力",
                formula_id="crane.outrigger",
                substituted=(
                    "R = W/4·(1 ± 2eₓ/Lₓ)·(1 ± 2e_y/L_y)，"
                    f"最大在 {worst_name} = {worst:.2f} t"
                ),
                inputs=reactions,
                value=round(worst, 3),
                verdict=Verdict.NA,
                unit="t",
                source="刚性平台四点支承（静力平衡）",
                notes=["假定支承平台为刚体；地基不均匀时需另行验算"],
            )
        )
        if case.machine_mass <= 0:
            warnings.append(
                "未提供整机自重，支腿反力只含吊重部分，不能作为整机倾覆判据（请补 machine_mass）"
            )
        else:
            model_row = None
            if case.crane is not None and repo is not None and case.crane.brand and case.crane.model:
                try:
                    model_row = repo.crane_model(case.crane.brand, case.crane.model)
                except Exception:
                    model_row = None
            limit_kn = None if model_row is None else model_row.get("max_outrigger_reaction_kN")
            if limit_kn:
                limit_t = float(limit_kn) / 9.80665
                checks.append(
                    CheckResult(
                        id="crane.outrigger_limit",
                        title="单腿反力与原厂限值对照",
                        formula_id="crane.outrigger",
                        substituted=f"R_max = {worst:.2f} t　原厂最大支腿反力 = {limit_t:.2f} t",
                        inputs={"R": round(worst, 3), "limit": round(limit_t, 3)},
                        value=round(worst, 3),
                        limit=round(limit_t, 3),
                        ratio=round(worst / limit_t, 4) if limit_t > 0 else None,
                        verdict=Verdict.PASS if worst <= limit_t + 1e-12 else Verdict.FAIL,
                        unit="t",
                        source="原厂性能表 操作说明第 11 条",
                        notes=["原厂给出的是该机型最大支腿反力，作为上限校核"],
                    )
                )
        if case.outrigger.plate_area:
            pressure = crane_select.ground_pressure(worst, case.outrigger.plate_area)
            checks.append(
                CheckResult(
                    id="crane.ground_pressure",
                    title="接地比压",
                    formula_id="crane.ground_pressure",
                    substituted=(
                        f"p = {worst:.2f} / {case.outrigger.plate_area:g} = {pressure:.2f} t/m²"
                    ),
                    inputs={"R": round(worst, 3), "A": case.outrigger.plate_area},
                    value=round(pressure, 3),
                    verdict=Verdict.NA,
                    unit="t/m²",
                    source="静力计算",
                    notes=["需与地基承载力特征值比较，承载力由地勘提供"],
                )
            )
            aux["ground_pressure"] = pressure
        aux["outrigger_reactions"] = reactions

    verdict, governing, utilization = summarize(checks)
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        verdict=verdict,
        governing=governing,
        utilization=utilization,
        checks=checks,
        aux=aux,
        warnings=warnings,
    )


def _frame_case(case: FrameCase) -> ComputationResult:
    nodes = [frame2d.FrameNode(x=node.x / 1000.0, y=node.y / 1000.0) for node in case.nodes]
    elements = [
        frame2d.FrameElement(
            i=element.i,
            j=element.j,
            e_modulus=element.e_modulus * 1e6,
            area=element.area * 1e-6,
            inertia=element.inertia * 1e-12,
            udl=element.udl * 1e3,
        )
        for element in case.elements
    ]
    supports = [
        frame2d.Support(node=s.node, fix_ux=s.fix_ux, fix_uy=s.fix_uy, fix_rz=s.fix_rz)
        for s in case.supports
    ]
    loads = [
        frame2d.NodalLoad(node=load.node, fy=load.fy, mz=load.mz * 1e-3) for load in case.loads
    ]

    result = frame2d.solve_frame(nodes, elements, supports, loads)
    checks = [
        CheckResult(
            id="fea.max_moment",
            title="最大弯矩包络",
            formula_id="fea.frame_k",
            substituted=f"|M|max = {result.max_moment / 1e3:.3f} kN·m",
            value=round(result.max_moment / 1e3, 4),
            verdict=Verdict.NA,
            unit="kN·m",
            source="有限元（Euler-Bernoulli 梁单元）",
        ),
        CheckResult(
            id="fea.max_shear",
            title="最大剪力包络",
            formula_id="fea.frame_k",
            substituted=f"|V|max = {result.max_shear / 1e3:.3f} kN",
            value=round(result.max_shear / 1e3, 4),
            verdict=Verdict.NA,
            unit="kN",
            source="有限元（Euler-Bernoulli 梁单元）",
        ),
        CheckResult(
            id="fea.max_deflection",
            title="最大竖向位移",
            formula_id="fea.frame_k",
            substituted=f"|δ|max = {result.max_deflection * 1000:.3f} mm（节点 {result.deflection_node}）",
            value=round(result.max_deflection * 1000, 4),
            verdict=Verdict.NA,
            unit="mm",
            source="有限元（Euler-Bernoulli 梁单元）",
        ),
    ]
    for node, (rx, ry, mz) in result.reactions.items():
        checks.append(
            CheckResult(
                id=f"fea.reaction.{node}",
                title=f"支座反力（节点 {node}）",
                formula_id="fea.frame_k",
                substituted=f"Rx={rx / 1e3:.3f} kN, Ry={ry / 1e3:.3f} kN, M={mz / 1e3:.3f} kN·m",
                value=round(ry / 1e3, 4),
                verdict=Verdict.NA,
                unit="kN",
                source="有限元",
            )
        )

    aux: dict[str, Any] = {
        "max_moment_kNm": result.max_moment / 1e3,
        "max_shear_kN": result.max_shear / 1e3,
        "max_deflection_mm": result.max_deflection * 1000,
        "reactions": {str(k): [v[0] / 1e3, v[1] / 1e3, v[2] / 1e3] for k, v in result.reactions.items()},
        "figure": "none",
    }
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        checks=checks,
        aux=aux,
        warnings=list(result.notes),
    )


def _capability_case(case: CapabilityCase, repo: Repo | None) -> ComputationResult:
    """能力反查：单机 90%、双机每台 80%。"""
    if repo is None:
        raise DataError("能力反查需要机型数据（先用 data build 建库并给 --db）")

    limit = case.limit
    if limit is None:
        limit = (
            crane_capability.DUAL_LIMIT
            if case.mode == "dual"
            else crane_capability.SINGLE_LIMIT
        )

    hook_mass = case.hook_mass
    hook_from_db = False
    if hook_mass == 0.0:
        try:
            model_row = repo.crane_model(case.crane.brand, case.crane.model)
        except DataError:
            model_row = None
        if model_row is not None and model_row.get("hook_main_t"):
            hook_mass = float(model_row["hook_main_t"])
            hook_from_db = True

    required = crane_capability.required_load(
        payload=case.payload,
        hook_mass=hook_mass,
        rigging=case.rigging,
        dynamic_factor=case.dynamic_factor,
    )

    def load_points(ref: Any) -> list[Any]:
        rows = repo.model_capacity(ref.brand, ref.model)
        if not rows:
            raise DataError(f"机型 {ref.model} 没有性能数据")
        return [
            crane_capability.Point(
                boom_len=float(row["boom_len"]),
                radius=float(row["radius"]),
                rated_load=float(row["rated_load"]),
                boom_angle=None if row["boom_angle"] is None else float(row["boom_angle"]),
                lift_height=None if row["lift_height"] is None else float(row["lift_height"]),
                config=str(row.get("config_name") or ""),
            )
            for row in rows
        ]

    def points_payload(points: list[Any]) -> list[list[float]]:
        return [[p.boom_len, p.radius, p.rated_load] for p in points]

    checks: list[CheckResult] = []
    aux: dict[str, Any] = {"figure": "capability", "mode": case.mode}
    warnings: list[str] = []
    if hook_from_db:
        warnings.append(
            f"未指定吊钩重量，已按机型库取主钩自重 {hook_mass:g} t 计入计算荷载"
        )
    elif hook_mass == 0.0:
        warnings.append(
            "未提供吊钩重量，且机型库中没有该机型的主钩自重，本次计算荷载未含吊钩——"
            "结果偏不安全，请补填吊钩重量后重新计算"
        )
    left_points = load_points(case.crane)

    if case.mode == "single":
        verdict = crane_capability.find_capability(left_points, required=required, ratio_limit=limit)
        ok = verdict.ok
        checks.append(
            CheckResult(
                id="capability.result",
                title="反查结论",
                formula_id="crane.capability",
                substituted=(
                    f"计算荷载 {required:.2f} t，负荷率上限 {limit:.0%}，扫描 {verdict.checked} 个格点 → "
                    + (f"能吊，最远 {verdict.max_radius:g} m" if ok else "不能吊")
                ),
                inputs={"required": round(required, 3), "limit": limit},
                value=0.0 if verdict.max_radius is None else round(verdict.max_radius, 3),
                verdict=Verdict.PASS if ok else Verdict.FAIL,
                unit="m",
                source="原厂性能表（查表取档，不插值）",
            )
        )
        if ok:
            checks.append(
                CheckResult(
                    id="capability.critical",
                    title="临界工况",
                    formula_id="crane.capability",
                    substituted=(
                        (f"{verdict.config}　" if verdict.config else "")
                        + f"臂长 {verdict.boom_len:g} m、幅度 {verdict.max_radius:g} m、"
                        f"仰角 {'—' if verdict.boom_angle is None else f'{verdict.boom_angle:g}°'}、"
                        f"起升高度 {'—' if verdict.lift_height is None else f'{verdict.lift_height:g} m'}、"
                        f"额定 {verdict.rated_load:g} t"
                    ),
                    inputs={
                        "boom_len": verdict.boom_len or 0.0,
                        "radius": verdict.max_radius or 0.0,
                        "rated": verdict.rated_load or 0.0,
                    },
                    value=round(verdict.utilization or 0.0, 4),
                    limit=limit,
                    ratio=round((verdict.utilization or 0.0) / limit, 4),
                    verdict=Verdict.PASS,
                    unit="—",
                    source="原厂性能表",
                    notes=["负荷率 = 计算荷载 ÷ 该格额定值"],
                )
            )
            if case.required_lift_height is not None and verdict.lift_height is not None:
                height_ok = verdict.lift_height >= case.required_lift_height - 1e-9
                checks.append(
                    CheckResult(
                        id="capability.lift_height",
                        title="起升高度（净空）",
                        formula_id="crane.lift_height",
                        substituted=(
                            f"该格起升高度 {verdict.lift_height:g} m ≥ 需求 {case.required_lift_height:g} m"
                            if height_ok
                            else f"该格起升高度 {verdict.lift_height:g} m < 需求 {case.required_lift_height:g} m"
                        ),
                        inputs={"available": verdict.lift_height, "required": case.required_lift_height},
                        value=round(verdict.lift_height, 3),
                        limit=case.required_lift_height,
                        verdict=Verdict.PASS if height_ok else Verdict.FAIL,
                        unit="m",
                        source="原厂性能表 起升高度列",
                    )
                )
                ok = ok and height_ok
        else:
            checks.append(
                CheckResult(
                    id="capability.shortfall",
                    title="最接近工况与缺口",
                    formula_id="crane.capability",
                    substituted=(
                        f"最有利格点：幅度 {verdict.closest_radius:g} m，"
                        f"负荷率 {verdict.closest_utilization:.2f}，"
                        f"超出上限 {verdict.shortfall_t:.2f} t"
                    ),
                    inputs={
                        "radius": verdict.closest_radius or 0.0,
                        "utilization": round(verdict.closest_utilization or 0.0, 4),
                        "shortfall": round(verdict.shortfall_t or 0.0, 3),
                    },
                    value=round(verdict.shortfall_t or 0.0, 3),
                    verdict=Verdict.FAIL,
                    unit="t",
                    source="原厂性能表",
                    notes=["缺口 = 计算荷载 − 该格额定值 × 负荷率上限"],
                )
            )
        aux["capability"] = {
            "mode": "single",
            "model": case.crane.model,
            "required": required,
            "hook_mass": hook_mass,
            "hook_from_db": hook_from_db,
            "limit": limit,
            "checked": verdict.checked,
            "ok": ok,
            "max_radius": verdict.max_radius,
            "config": verdict.config,
            "boom_len": verdict.boom_len,
            "boom_angle": verdict.boom_angle,
            "lift_height": verdict.lift_height,
            "rated_load": verdict.rated_load,
            "utilization": verdict.utilization,
            "shortfall_t": verdict.shortfall_t,
            "closest_radius": verdict.closest_radius,
            "points": points_payload(left_points),
        }
    else:
        if case.second is None:
            raise InputError("双机模式需要给出第二台机型 second")
        right_points = load_points(case.second)
        left_req, right_req = crane_capability.split_by_ratio(
            required * case.asynchronism, case.left_share
        )
        verdict_left, verdict_right = crane_capability.find_dual(
            left_points,
            right_points,
            required_left=left_req,
            required_right=right_req,
            ratio_limit=limit,
        )
        ok = verdict_left.ok and verdict_right.ok

        def side(check_id: str, title: str, verdict: Any, ref: Any) -> CheckResult:
            angle_text = "—" if verdict.boom_angle is None else f"{verdict.boom_angle:g}°"
            height_text = "—" if verdict.lift_height is None else f"{verdict.lift_height:g} m"
            text = (
                f"{ref.model}：计算荷载 {verdict.required_load:.2f} t → 能吊，最远 {verdict.max_radius:g} m"
                f"（臂长 {verdict.boom_len:g} m、仰角 {angle_text}、"
                f"起升 {height_text}、负荷率 {verdict.utilization:.2f}）"
                if verdict.ok
                else f"{ref.model}：计算荷载 {verdict.required_load:.2f} t → 不能吊"
                f"（最有利 {verdict.closest_radius:g} m 处仍超限 {verdict.shortfall_t:.2f} t）"
            )
            return CheckResult(
                id=check_id,
                title=title,
                formula_id="crane.capability",
                substituted=text,
                inputs={"required": round(verdict.required_load, 3)},
                value=0.0 if verdict.max_radius is None else round(verdict.max_radius, 3),
                limit=limit,
                verdict=Verdict.PASS if verdict.ok else Verdict.FAIL,
                unit="m",
                source="原厂性能表（查表取档，不插值）",
            )

        checks.append(
            CheckResult(
                id="capability.result",
                title="双机抬吊结论",
                formula_id="crane.capability",
                substituted=(
                    f"总计算荷载 {required:.2f} t，按 {case.left_share:.0%}/{1 - case.left_share:.0%} 分配，"
                    f"不同步系数 {case.asynchronism:g}，每台上限 {limit:.0%} → "
                    + ("两台均满足" if ok else "存在不满足的机组")
                ),
                inputs={
                    "required": round(required, 3),
                    "left_share": case.left_share,
                    "asynchronism": case.asynchronism,
                    "limit": limit,
                },
                value=round(required, 3),
                verdict=Verdict.PASS if ok else Verdict.FAIL,
                unit="t",
                source="原厂性能表 + 双机负荷分配",
            )
        )
        checks.append(side("capability.left", "主吊（左机）", verdict_left, case.crane))
        checks.append(side("capability.right", "辅吊（右机）", verdict_right, case.second))
        if case.asynchronism != 1.0:
            warnings.append(f"已计入不同步系数 {case.asynchronism:g}，两台的计算荷载均已放大")
        aux["capability"] = {
            "mode": "dual",
            "model": case.crane.model,
            "second_model": case.second.model,
            "required": required,
            "limit": limit,
            "left_share": case.left_share,
            "asynchronism": case.asynchronism,
            "ok": ok,
            "left": {
                "model": case.crane.model,
                "required": verdict_left.required_load,
                "ok": verdict_left.ok,
                "max_radius": verdict_left.max_radius,
                "boom_len": verdict_left.boom_len,
                "boom_angle": verdict_left.boom_angle,
                "lift_height": verdict_left.lift_height,
                "rated_load": verdict_left.rated_load,
                "utilization": verdict_left.utilization,
            },
            "right": {
                "model": case.second.model,
                "required": verdict_right.required_load,
                "ok": verdict_right.ok,
                "max_radius": verdict_right.max_radius,
                "boom_len": verdict_right.boom_len,
                "boom_angle": verdict_right.boom_angle,
                "lift_height": verdict_right.lift_height,
                "rated_load": verdict_right.rated_load,
                "utilization": verdict_right.utilization,
            },
            "points": points_payload(left_points),
            "points_right": points_payload(right_points),
        }

    verdict_name, governing, utilization = summarize(checks)
    if case.mode == "single" and not aux["capability"]["ok"]:
        verdict_name = Verdict.FAIL
    if case.mode == "dual" and not aux["capability"]["ok"]:
        verdict_name = Verdict.FAIL
    return ComputationResult(
        kind=case.kind,
        engine_version=engine_version(),
        input_digest=digest(case.model_dump(mode="json")),
        verdict=verdict_name,
        governing=governing,
        utilization=utilization,
        checks=checks,
        aux=aux,
        warnings=warnings,
    )


def run_case(data: dict[str, Any], repo: Repo | None = None) -> ComputationResult:
    case = parse_case(data)
    if isinstance(case, SectionCase):
        result = _section_case(case, repo)
    elif isinstance(case, CentroidCase):
        result = _centroid_case(case)
    elif isinstance(case, EyeCase):
        result = _eye_case(case, repo)
    elif isinstance(case, BeamCase):
        result = _beam_case(case, repo)
    elif isinstance(case, RiggingCase):
        result = _rigging_case(case)
    elif isinstance(case, CraneCase):
        result = _crane_case(case, repo)
    elif isinstance(case, CapabilityCase):
        result = _capability_case(case, repo)
    elif isinstance(case, FrameCase):
        result = _frame_case(case)
    else:  # pragma: no cover - 注册表与模型必须同步
        raise UnknownKindError(f"未实现的 case 类型：{case.kind}")

    if repo is not None:
        result.data_version = repo.meta().get("data_version", "")
    result.aux.setdefault("case", case.model_dump(mode="json"))
    return result


def run_many(cases: Sequence[dict[str, Any]], repo: Repo | None = None) -> list[ComputationResult]:
    results: list[ComputationResult] = []
    for data in cases:
        try:
            results.append(run_case(data, repo))
        except LiftcalcError:
            raise
    return results
