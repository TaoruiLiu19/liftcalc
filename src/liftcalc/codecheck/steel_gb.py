"""GB 钢构件校核（设计 §8.8，基础版）。

**本模块只做"能明确写出来"的判定**：长细比、挠度比例、强度限值引用。
整体稳定系数 φ（GB 50017 的 b 类曲线）需要完整曲线表，尚未实现——
不要在计算书里假装算过。

红线：所有限值来自 `limits.py`，本模块不得内嵌系数。
"""

from __future__ import annotations

from dataclasses import dataclass

from liftcalc.codecheck import limits
from liftcalc.core.errors import InfeasibleSectionError
from liftcalc.core.units import Q

SLENDERNESS_LIMIT_COMPRESSION = 150.0  # TBD-核定
SLENDERNESS_LIMIT_TENSION = 350.0  # TBD-核定


@dataclass(frozen=True)
class SlendernessResult:
    value: float
    limit: float
    ok: bool
    source: str


def slenderness(*, effective_length: Q, radius_of_gyration: Q) -> float:
    """长细比 λ = l₀ / i。"""
    try:
        length_mm = float(effective_length.to("mm").magnitude)
        radius_mm = float(radius_of_gyration.to("mm").magnitude)
    except Exception as exc:
        raise InfeasibleSectionError(f"计算长度与回转半径需要长度单位：{effective_length}") from exc
    if radius_mm <= 0 or length_mm <= 0:
        raise InfeasibleSectionError("计算长度与回转半径都必须为正")
    return length_mm / radius_mm


def check_slenderness(
    *, effective_length: Q, radius_of_gyration: Q, member: str = "compression"
) -> SlendernessResult:
    value = slenderness(effective_length=effective_length, radius_of_gyration=radius_of_gyration)
    limit = (
        SLENDERNESS_LIMIT_COMPRESSION if member == "compression" else SLENDERNESS_LIMIT_TENSION
    )
    return SlendernessResult(
        value=value,
        limit=limit,
        ok=value <= limit,
        source=f"GB 50017-2017 容许长细比（TBD-核定，取 {limit:g}）",
    )


def bending_allowable(fy_mpa: float) -> limits.Limit:
    return limits.tensile_design_strength(fy_mpa)


def shear_allowable(fy_mpa: float) -> limits.Limit:
    return limits.shear_strength(fy_mpa)


def deflection_allowable(span: Q, ratio: float = 400.0) -> Q:
    """容许挠度 = 跨度 / 比例。"""
    if ratio <= 0:
        raise InfeasibleSectionError("挠度比例必须为正")
    span_mm = float(span.to("mm").magnitude)
    return Q(span_mm / ratio, "mm")
