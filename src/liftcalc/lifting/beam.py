"""吊梁校核（设计 §8.4）。

只覆盖四种有闭式解的工况；超出范围必须走 `fea.frame2d`。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from liftcalc.codecheck import limits
from liftcalc.core.errors import InfeasibleSectionError
from liftcalc.core.format import sig
from liftcalc.core.result import CheckResult, Verdict
from liftcalc.core.units import Q

Support = Literal["simply_supported", "cantilever"]
LoadType = Literal["udl", "point_mid", "point_tip"]


@dataclass(frozen=True)
class BeamInput:
    support: Support
    span: Q
    total_load: Q  # 总荷载（含动载），kN
    load_type: LoadType
    inertia: Q  # I，mm^4
    section_modulus: Q  # W，mm^3
    e_modulus: Q  # MPa
    web_area: Q | None = None  # 腹板面积 mm²，用于剪应力
    deflection_ratio: float = 400.0
    fy: Q | None = None  # MPa


@dataclass(frozen=True)
class BeamOutcome:
    checks: list[CheckResult]
    aux: dict[str, object]
    warnings: list[str] = field(default_factory=list)


def _mm(value: Q, label: str) -> float:
    try:
        magnitude = float(value.to("mm").magnitude)
    except Exception as exc:
        raise InfeasibleSectionError(f"{label} 需要长度单位：{value}") from exc
    if magnitude <= 0:
        raise InfeasibleSectionError(f"{label} 必须为正")
    return magnitude


def _kn(value: Q, label: str = "荷载") -> float:
    try:
        magnitude = float(value.to("kN").magnitude)
    except Exception as exc:
        raise InfeasibleSectionError(f"{label} 需要力的单位：{value}") from exc
    if magnitude <= 0:
        raise InfeasibleSectionError(f"{label} 必须为正")
    return magnitude


def _check(
    *,
    check_id: str,
    title: str,
    formula_id: str,
    value: float,
    limit_value: float,
    unit: str,
    substituted: str,
    source: str,
    note: str = "",
    lower_is_better: bool = True,
) -> CheckResult:
    ratio = value / limit_value if limit_value > 0 else None
    ok = ratio is not None and (
        ratio <= 1.0 + 1e-12 if lower_is_better else ratio >= 1.0 - 1e-12
    )
    return CheckResult(
        id=check_id,
        title=title,
        formula_id=formula_id,
        substituted=substituted,
        inputs={"value": round(value, 4), "limit": round(limit_value, 4)},
        value=round(value, 4),
        limit=round(limit_value, 4),
        ratio=None if ratio is None else round(ratio, 4),
        verdict=Verdict.PASS if ok else Verdict.FAIL,
        unit=unit,
        source=source,
        notes=[note] if note else [],
    )


def check_beam(data: BeamInput) -> BeamOutcome:
    length_mm = _mm(data.span, "跨度")
    length_m = length_mm / 1000.0
    total_n = _kn(data.total_load) * 1000.0
    inertia_mm4 = float(data.inertia.to("mm**4").magnitude)
    inertia_m4 = inertia_mm4 * 1e-12
    modulus_mm3 = float(data.section_modulus.to("mm**3").magnitude)
    e_mpa = float(data.e_modulus.to("MPa").magnitude)

    warnings: list[str] = []
    aux: dict[str, object] = {
        "support": data.support,
        "load_type": data.load_type,
        "span_mm": length_mm,
        "total_load_kN": _kn(data.total_load),
    }

    udl = total_n / length_m  # N/m

    if data.support == "simply_supported":
        if data.load_type == "udl":
            moment = udl * length_m**2 / 8.0
            shear = udl * length_m / 2.0
            deflection = 5 * udl * length_m**4 / (384 * e_mpa * 1e6 * inertia_m4)
            formula_m, formula_f = "beam.M_simple_udl", "beam.f_simple_udl"
        elif data.load_type == "point_mid":
            moment = total_n * length_m / 4.0
            shear = total_n / 2.0
            deflection = total_n * length_m**3 / (48 * e_mpa * 1e6 * inertia_m4)
            formula_m, formula_f = "beam.M_simple_point", "beam.f_simple_point"
        else:
            raise InfeasibleSectionError("简支梁不支持 point_tip（端部集中力）工况")
    elif data.support == "cantilever":
        if data.load_type == "udl":
            moment = udl * length_m**2 / 2.0
            shear = udl * length_m
            deflection = udl * length_m**4 / (8 * e_mpa * 1e6 * inertia_m4)
            formula_m, formula_f = "beam.M_cantilever_udl", "beam.f_cantilever_udl"
        elif data.load_type == "point_tip":
            moment = total_n * length_m
            shear = total_n
            deflection = total_n * length_m**3 / (3 * e_mpa * 1e6 * inertia_m4)
            formula_m, formula_f = "beam.M_cantilever_point", "beam.f_cantilever_point"
        else:
            raise InfeasibleSectionError("悬臂梁不支持 point_mid 工况")
    else:  # pragma: no cover
        raise InfeasibleSectionError(f"不支持的支承形式：{data.support}")

    moment_knm = moment / 1e6
    shear_kn = shear / 1000.0
    deflection_mm = deflection * 1000.0
    aux.update(
        {
            "max_moment_kNm": moment_knm,
            "max_shear_kN": shear_kn,
            "max_deflection_mm": deflection_mm,
        }
    )

    checks: list[CheckResult] = []

    # 1) 弯曲正应力（moment 为 N·m，W 为 mm³ → 需把弯矩换成 N·mm）
    sigma = moment * 1000.0 / modulus_mm3
    if data.fy is None:
        warnings.append("未提供 fy，弯曲与剪应力无法判定，仅输出数值")
        checks.append(
            CheckResult(
                id="beam.bending", title="弯曲正应力", formula_id=formula_m,
                substituted=f"σ = {sig(moment_knm)}×10⁶ / {sig(modulus_mm3)}",
                inputs={"M": round(moment_knm, 4), "W": round(modulus_mm3, 4)},
                value=round(sigma, 4), verdict=Verdict.NA, unit="MPa",
                source="待提供材质",
            )
        )
    else:
        fy_mpa = float(data.fy.to("MPa").magnitude)
        bending_limit = limits.tensile_design_strength(fy_mpa)
        checks.append(
            _check(
                check_id="beam.bending", title="弯曲正应力", formula_id=formula_m,
                value=sigma, limit_value=bending_limit.value, unit="MPa",
                substituted=f"σ = {sig(moment_knm)}×10⁶ / {sig(modulus_mm3)}",
                source=bending_limit.source, note=bending_limit.note(),
            )
        )
        # 2) 腹板剪应力（近似：按腹板平均）
        if data.web_area is not None:
            web_area_mm2 = float(data.web_area.to("mm**2").magnitude)
            if web_area_mm2 <= 0:
                raise InfeasibleSectionError("腹板面积必须为正")
            tau = shear / web_area_mm2
            shear_limit = limits.shear_strength(fy_mpa)
            checks.append(
                _check(
                    check_id="beam.shear", title="腹板剪应力", formula_id="beam.tau",
                    value=tau, limit_value=shear_limit.value, unit="MPa",
                    substituted=f"τ = {sig(shear_kn)}×10³ / {sig(web_area_mm2)}",
                    source=shear_limit.source,
                    note="按腹板平均剪应力近似（未计剪流分布）",
                )
            )
        else:
            warnings.append("未提供腹板面积，跳过剪应力校核")

    # 3) 挠度
    limit_deflection = length_mm / data.deflection_ratio
    checks.append(
        _check(
            check_id="beam.deflection", title="挠度", formula_id=formula_f,
            value=deflection_mm, limit_value=limit_deflection, unit="mm",
            substituted=f"f = {sig(deflection_mm)} mm  ≤  L/{data.deflection_ratio:g} = {sig(limit_deflection)} mm",
            source=f"GB 50017-2017 容许挠度 L/{data.deflection_ratio:g}（TBD-核定）",
            note="限值比例由输入给定，默认 L/400",
        )
    )

    aux["figure"] = "beam"
    return BeamOutcome(checks=checks, aux=aux, warnings=warnings)


def required_inertia_for_deflection(
    *, support: Support, load_type: LoadType, total_load: Q, span: Q,
    e_modulus: Q, deflection_ratio: float,
) -> Q:
    """反算满足挠度限值所需的最小惯性矩（用于选型）。"""
    length_m = _mm(span, "跨度") / 1000.0
    total_n = _kn(total_load) * 1000.0
    e_pa = float(e_modulus.to("MPa").magnitude) * 1e6
    limit_m = (length_m / deflection_ratio)
    udl = total_n / length_m
    if support == "simply_supported":
        coefficient = 5 * udl / 384 if load_type == "udl" else total_n / 48
    else:
        coefficient = udl / 8 if load_type == "udl" else total_n / 3
    required = coefficient * length_m**3 / (e_pa * limit_m)
    return Q(required * 1e12, "mm**4")
