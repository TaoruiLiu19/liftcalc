"""能力反查：给定吊重，问"能吊吗、最远多少米、多高"。

判定一律基于原厂性能表格点（不插值）：
    负荷率 = 计算荷载 / 该格额定起重量
单机上限 90%，双机每台 80%。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from liftcalc.core.errors import InfeasibleSectionError, OutOfTableError

SINGLE_LIMIT = 0.90
DUAL_LIMIT = 0.80
TOL = 1e-9


@dataclass(frozen=True)
class Point:
    boom_len: float
    radius: float
    rated_load: float
    boom_angle: float | None = None
    lift_height: float | None = None
    config: str = ""


@dataclass(frozen=True)
class Verdict:
    ok: bool
    required_load: float
    ratio_limit: float
    checked: int
    max_radius: float | None = None
    boom_len: float | None = None
    boom_angle: float | None = None
    lift_height: float | None = None
    rated_load: float | None = None
    utilization: float | None = None
    config: str | None = None
    closest_radius: float | None = None
    closest_utilization: float | None = None
    shortfall_t: float | None = None


def required_load(
    *, payload: float, hook_mass: float = 0.0, rigging: float = 0.0, dynamic_factor: float = 1.1
) -> float:
    if payload < 0 or hook_mass < 0 or rigging < 0:
        raise InfeasibleSectionError("重量不得为负")
    if dynamic_factor <= 0:
        raise InfeasibleSectionError("动载系数必须为正")
    return payload + hook_mass + rigging * dynamic_factor


def find_capability(points: Sequence[Point], *, required: float, ratio_limit: float) -> Verdict:
    if not points:
        raise OutOfTableError("性能表为空")
    if required <= 0:
        raise InfeasibleSectionError("所需吊重必须为正")
    if not 0 < ratio_limit <= 1:
        raise InfeasibleSectionError("负荷率上限需在 (0, 1] 内")

    feasible = [p for p in points if required <= p.rated_load * ratio_limit + TOL]
    if feasible:
        radius = max(p.radius for p in feasible)
        at_radius = [p for p in feasible if abs(p.radius - radius) <= TOL]
        best = max(at_radius, key=lambda p: p.rated_load)
        return Verdict(
            ok=True,
            required_load=required,
            ratio_limit=ratio_limit,
            checked=len(points),
            max_radius=radius,
            boom_len=best.boom_len,
            boom_angle=best.boom_angle,
            lift_height=best.lift_height,
            rated_load=best.rated_load,
            utilization=required / best.rated_load,
            config=best.config or None,
        )

    closest = min(points, key=lambda p: required / p.rated_load)
    utilization = required / closest.rated_load
    return Verdict(
        ok=False,
        required_load=required,
        ratio_limit=ratio_limit,
        checked=len(points),
        closest_radius=closest.radius,
        closest_utilization=utilization,
        shortfall_t=required - closest.rated_load * ratio_limit,
    )


def find_dual(
    left: Sequence[Point],
    right: Sequence[Point],
    *,
    required_left: float,
    required_right: float,
    ratio_limit: float = DUAL_LIMIT,
) -> tuple[Verdict, Verdict]:
    """双机抬吊：两台各自按同一上限反查，两台都通过才算通过。"""
    return (
        find_capability(left, required=required_left, ratio_limit=ratio_limit),
        find_capability(right, required=required_right, ratio_limit=ratio_limit),
    )


def split_by_ratio(total: float, left_ratio: float = 0.6) -> tuple[float, float]:
    """按比例分配双机荷载（默认 60/40，偏保守）。"""
    if not 0 < left_ratio < 1:
        raise InfeasibleSectionError("分配比例需在 (0, 1) 内")
    return total * left_ratio, total * (1 - left_ratio)
