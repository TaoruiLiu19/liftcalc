"""单位与量纲。

ADR-003：单位只在边界转换一次；内核函数只接受 `pint.Quantity`。
"""

from __future__ import annotations

from typing import Final

import pint

UREG: Final[pint.UnitRegistry] = pint.UnitRegistry()
Q = UREG.Quantity

SI_UNITS: Final[dict[str, str]] = {
    "length": "meter",
    "force": "newton",
    "stress": "pascal",
    "moment": "newton * meter",
    "area": "meter ** 2",
    "inertia": "meter ** 4",
    "section_modulus": "meter ** 3",
    "mass": "kilogram",
    "angle": "radian",
    "volume": "meter ** 3",
}


class UnitError(ValueError):
    """单位缺失、无法识别，或量纲不匹配。"""


def to_quantity(value: float, unit: str) -> Q:
    """把 (数值, 单位字符串) 转成 Quantity。

    这是外部世界进入内核的唯一入口；单位缺失一律报错，不猜默认值。
    """
    if not unit or not isinstance(unit, str):
        raise UnitError(f"缺少单位: {unit!r}")
    try:
        unit_obj = UREG.parse_units(unit)
    except Exception as exc:  # pint 抛的异常类型较多，统一收敛
        raise UnitError(f"无法识别的单位 {unit!r}: {exc}") from exc
    return Q(float(value), unit_obj)


def as_si(quantity: Q, kind: str) -> float:
    """把 Quantity 换成指定物理量的 SI 数值。"""
    try:
        target = SI_UNITS[kind]
    except KeyError as exc:
        raise UnitError(f"未知物理量类别 {kind!r}") from exc
    try:
        return float(quantity.to(target).magnitude)
    except pint.DimensionalityError as exc:
        raise UnitError(f"量纲不匹配：期望 {kind}，实际 {quantity.units}") from exc


def to_si(quantity: Q, kind: str) -> Q:
    """把 Quantity 换成指定物理量的 SI 单位。"""
    try:
        return quantity.to(SI_UNITS[kind])
    except KeyError as exc:
        raise UnitError(f"未知物理量类别 {kind!r}") from exc


def magnitude(quantity: Q, unit: str) -> float:
    """取指定单位下的数值（用于输出显示）。"""
    try:
        return float(quantity.to(unit).magnitude)
    except Exception as exc:
        raise UnitError(f"无法换算到 {unit!r}: {exc}") from exc
