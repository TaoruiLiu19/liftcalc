"""吊耳校核（设计 §8.3）。

每个校核项都是独立可测的；组合逻辑在本模块，限值在 `codecheck.limits`。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from liftcalc.codecheck import limits
from liftcalc.core.errors import InfeasibleSectionError
from liftcalc.core.format import sig
from liftcalc.core.result import CheckResult, Verdict
from liftcalc.core.units import Q


@dataclass(frozen=True)
class EyeGeometry:
    plate_t: Q
    plate_b: Q
    plate_h: Q
    hole_d: Q
    hole_edge: Q  # 孔中心至板端距离 e


@dataclass(frozen=True)
class EyeLoad:
    design: Q
    dynamic_factor: float = 1.0
    angle_deg: float = 0.0


@dataclass(frozen=True)
class EyeWeld:
    leg: Q
    length: Q
    electrode: str = "E43"


@dataclass(frozen=True)
class EyeOutcome:
    checks: list[CheckResult]
    aux: dict[str, object]
    warnings: list[str] = field(default_factory=list)


def _mm(value: Q, label: str) -> float:
    try:
        magnitude = float(value.to("mm").magnitude)
    except Exception as exc:
        raise InfeasibleSectionError(f"{label} 需要长度单位：{value}") from exc
    if magnitude <= 0:
        raise InfeasibleSectionError(f"{label} 必须为正：{magnitude} mm")
    return magnitude


def _kn(value: Q) -> float:
    try:
        magnitude = float(value.to("kN").magnitude)
    except Exception as exc:
        raise InfeasibleSectionError(f"荷载需要力的单位：{value}") from exc
    if magnitude <= 0:
        raise InfeasibleSectionError(f"荷载必须为正：{magnitude} kN")
    return magnitude


def _check(
    *,
    check_id: str,
    title: str,
    formula_id: str,
    value: float,
    limit: limits.Limit,
    substituted: str,
    inputs: dict[str, float],
    note: str = "",
) -> CheckResult:
    ratio = value / limit.value if limit.value > 0 else None
    verdict = Verdict.PASS if ratio is not None and ratio <= 1.0 + 1e-12 else Verdict.FAIL
    notes = [limit.note()]
    if note:
        notes.append(note)
    return CheckResult(
        id=check_id,
        title=title,
        formula_id=formula_id,
        substituted=substituted,
        inputs=inputs,
        value=round(value, 4),
        limit=round(limit.value, 4),
        ratio=None if ratio is None else round(ratio, 4),
        verdict=verdict,
        unit="MPa",
        source=limit.source,
        notes=notes,
    )


def check_eye(
    *,
    geometry: EyeGeometry,
    load: EyeLoad,
    fy: Q,
    weld: EyeWeld | None = None,
    pin_diameter: Q | None = None,
) -> EyeOutcome:
    """执行吊耳全部校核项。

    fy 以应力单位给出（通常 MPa）。
    """
    t = _mm(geometry.plate_t, "耳板厚度 t")
    b = _mm(geometry.plate_b, "耳板宽度 b")
    h = _mm(geometry.plate_h, "耳板高度 h")
    d = _mm(geometry.hole_d, "销孔直径 d")
    e = _mm(geometry.hole_edge, "孔中心至板端距离 e")

    if b <= d:
        raise InfeasibleSectionError(f"耳板宽度 b={b} 不大于孔径 d={d}，净截面为负")
    if e - d / 2 <= 0:
        raise InfeasibleSectionError(f"孔中心至板端距离 e={e} 过小（e ≤ d/2）")

    fy_mpa = float(fy.to("MPa").magnitude)
    n_kn = _kn(load.design)
    k = float(load.dynamic_factor)
    if k <= 0:
        raise InfeasibleSectionError(f"动载系数必须为正：{k}")
    n_eff_kn = n_kn * k
    n_eff_n = n_eff_kn * 1000.0

    warnings: list[str] = []
    if load.angle_deg > 10.0:
        warnings.append(
            f"受力与板面夹角 {sig(load.angle_deg)}° > 10°：平面外分力未计入，需按规范另行验算"
        )

    checks: list[CheckResult] = []

    # 1) 孔壁承压
    bearing = limits.bearing_strength(fy_mpa)
    sigma_c = n_eff_n / (d * t)
    checks.append(
        _check(
            check_id="eye.hole_bearing",
            title="孔壁承压",
            formula_id="eye.hole_bearing",
            value=sigma_c,
            limit=bearing,
            substituted=f"σ_c = {sig(n_eff_kn)}×10³ / ({sig(d)} × {sig(t)})",
            inputs={"N": round(n_eff_kn, 4), "d": round(d, 4), "t": round(t, 4)},
        )
    )

    # 2) 净截面抗拉
    a_net = (b - d) * t
    tensile = limits.tensile_design_strength(fy_mpa)
    sigma_t = n_eff_n / a_net
    checks.append(
        _check(
            check_id="eye.net_tension",
            title="净截面抗拉",
            formula_id="eye.net_tension",
            value=sigma_t,
            limit=tensile,
            substituted=f"σ = {sig(n_eff_kn)}×10³ / [({sig(b)} − {sig(d)}) × {sig(t)}]",
            inputs={"N": round(n_eff_kn, 4), "b": round(b, 4), "d": round(d, 4), "t": round(t, 4)},
        )
    )

    # 3) 端部抗剪（撕裂）
    shear = limits.shear_strength(fy_mpa)
    tau_end = n_eff_n / (2 * e * t)
    checks.append(
        _check(
            check_id="eye.end_shear",
            title="端部抗剪",
            formula_id="eye.end_shear",
            value=tau_end,
            limit=shear,
            substituted=f"τ = {sig(n_eff_kn)}×10³ / (2 × {sig(e)} × {sig(t)})",
            inputs={"N": round(n_eff_kn, 4), "e": round(e, 4), "t": round(t, 4)},
        )
    )

    # 4) 角焊缝（可选）
    if weld is not None:
        leg = _mm(weld.leg, "焊脚尺寸")
        length = _mm(weld.length, "焊缝计算长度")
        weld_limit = limits.weld_strength(weld.electrode)
        tau_w = n_eff_n / (0.7 * leg * length)
        checks.append(
            _check(
                check_id="eye.fillet_weld",
                title="角焊缝",
                formula_id="eye.fillet_weld",
                value=tau_w,
                limit=weld_limit,
                substituted=f"τ_f = {sig(n_eff_kn)}×10³ / (0.7 × {sig(leg)} × {sig(length)})",
                inputs={"N": round(n_eff_kn, 4), "hf": round(leg, 4), "lw": round(length, 4)},
                note=f"焊条 {weld.electrode}",
            )
        )

    # 5) 销轴（可选）
    if pin_diameter is not None:
        pin_d = _mm(pin_diameter, "销轴直径")
        pin_shear = limits.shear_strength(fy_mpa)
        tau_pin = (n_eff_n / 2.0) / (math.pi * pin_d**2 / 4.0)
        checks.append(
            _check(
                check_id="pin.shear",
                title="销轴抗剪",
                formula_id="pin.shear",
                value=tau_pin,
                limit=pin_shear,
                substituted=f"τ = ({sig(n_eff_kn)}×10³/2) / (π×{sig(pin_d)}²/4)",
                inputs={"N": round(n_eff_kn, 4), "d": round(pin_d, 4)},
                note="按双剪，单剪面承担一半荷载",
            )
        )
        moment = n_eff_n * t / 4.0
        section_modulus = math.pi * pin_d**3 / 32.0
        sigma_pin = moment / section_modulus
        checks.append(
            _check(
                check_id="pin.bending",
                title="销轴抗弯",
                formula_id="pin.bending",
                value=sigma_pin,
                limit=tensile,
                substituted=f"σ = ({sig(n_eff_kn)}×10³ × {sig(t)}/4) / (π×{sig(pin_d)}³/32)",
                inputs={"N": round(n_eff_kn, 4), "t": round(t, 4), "d": round(pin_d, 4)},
                note="支承跨距取耳板厚度，属偏保守近似",
            )
        )

    aux: dict[str, object] = {
        "figure": "lifting_eye",
        "plate": {"b_mm": b, "h_mm": h, "t_mm": t},
        "hole": {"d_mm": d, "e_mm": e},
        "extent": {"x_mm": [-e, b - e], "y_mm": [-h / 2.0, h / 2.0]},
        "load": {"n_kN": n_kn, "factor": k, "n_effective_kN": n_eff_kn, "angle_deg": load.angle_deg},
    }

    return EyeOutcome(checks=checks, aux=aux, warnings=warnings)
