"""吊车选型、负荷率与支腿反力。

**选型铁律（原厂说明第 7 条）**：
    当吊臂长度和工作幅度与表中不相同时，应取下一个吊臂长度和工作幅度进行作业。

因此本模块**不做任何插值**：臂长与幅度都向上取到表中相邻档（更保守），
超出表范围一律报错，绝不外推。

其余原厂规则：
- 说明第 2 条：额定总起重量**包括吊钩和吊具**的重量。
- 说明第 5 条：360° 全回转必须先支第五支腿，否则不允许在前方区域作业。
- 说明第 8 条：副臂处于作业状态而使用主臂吊重时，主臂额定起重量应减少 2000 kg。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from liftcalc.core.errors import InfeasibleSectionError, OutOfTableError

JIB_MAIN_REDUCTION_T = 2.0  # 说明第 8 条：2000 kg
TOL = 1e-9


@dataclass(frozen=True)
class CapacityRow:
    """一行性能表：某臂长、某幅度下的额定起重量（t）。"""

    boom_len: float
    radius: float
    rated_load: float


@dataclass(frozen=True)
class LookupResult:
    rated_load: float  # 原始额定值（t）
    adjusted_load: float  # 按配置折减后的额定值（t）
    used_boom_len: float
    used_radius: float
    boom_rounded: bool
    radius_rounded: bool
    adjustments: tuple[str, ...] = ()


def _unique_sorted(values: Sequence[float]) -> list[float]:
    ordered: list[float] = []
    for value in sorted(values):
        if not ordered or abs(ordered[-1] - value) > TOL:
            ordered.append(value)
    return ordered


def lookup_capacity(
    rows: Sequence[CapacityRow],
    *,
    boom_len: float,
    radius: float,
    jib_installed: bool = False,
) -> LookupResult:
    """按原厂规则查表：臂长与幅度都向上取档，不插值。"""
    if not rows:
        raise OutOfTableError("性能表为空")
    if boom_len <= 0 or radius <= 0:
        raise InfeasibleSectionError("臂长与幅度都必须为正")

    booms = _unique_sorted([row.boom_len for row in rows])
    chosen_boom = next((value for value in booms if value >= boom_len - TOL), None)
    if chosen_boom is None:
        raise OutOfTableError(
            f"臂长 {boom_len:g} m 超出性能表范围（最大 {booms[-1]:g} m）",
            boom_len=boom_len,
            max_boom=booms[-1],
        )

    radii = _unique_sorted([row.radius for row in rows if abs(row.boom_len - chosen_boom) <= TOL])
    if not radii:
        raise OutOfTableError(f"臂长 {chosen_boom:g} m 没有性能数据")
    chosen_radius = next((value for value in radii if value >= radius - TOL), None)
    if chosen_radius is None:
        raise OutOfTableError(
            f"幅度 {radius:g} m 超出 {chosen_boom:g} m 臂长的性能表范围（最大 {radii[-1]:g} m）",
            radius=radius,
            boom_len=chosen_boom,
            max_radius=radii[-1],
        )

    for row in rows:
        if abs(row.boom_len - chosen_boom) <= TOL and abs(row.radius - chosen_radius) <= TOL:
            base = row.rated_load
            break
    else:  # pragma: no cover - 上面的筛选保证能命中
        raise OutOfTableError("性能表缺少该组合")

    adjustments: list[str] = []
    adjusted = base
    if jib_installed:
        adjusted = max(base - JIB_MAIN_REDUCTION_T, 0.0)
        adjustments.append(
            f"说明第 8 条：副臂在作业状态，主臂额定值由 {base:g} t 减 {JIB_MAIN_REDUCTION_T:g} t"
        )

    return LookupResult(
        rated_load=base,
        adjusted_load=adjusted,
        used_boom_len=chosen_boom,
        used_radius=chosen_radius,
        boom_rounded=abs(chosen_boom - boom_len) > TOL,
        radius_rounded=abs(chosen_radius - radius) > TOL,
        adjustments=tuple(adjustments),
    )


def load_ratio(
    *,
    payload: float,
    hook_mass: float,
    rigging: float,
    dynamic_factor: float,
    rated_load: float,
) -> float:
    """负荷率 = （吊件 + 吊钩 + 索具 × 动载系数）/ 额定起重量。

    说明第 2 条：额定总起重量已包含吊钩和吊具，故荷载侧必须计入吊钩重量。
    """
    if rated_load <= 0:
        raise InfeasibleSectionError("额定起重量必须为正")
    if payload < 0 or hook_mass < 0 or rigging < 0:
        raise InfeasibleSectionError("重量不得为负")
    if dynamic_factor <= 0:
        raise InfeasibleSectionError("动载系数必须为正")
    return (payload + hook_mass + rigging * dynamic_factor) / rated_load


def check_working_region(*, region: str, fifth_outrigger: bool) -> None:
    """说明第 5 条：不支第五支腿时，前方区域禁止作业。"""
    if region == "前方" and not fifth_outrigger:
        raise InfeasibleSectionError(
            "说明第 5 条：360° 全回转前必须支好第五支腿，否则不允许在前方区域作业"
        )


@dataclass(frozen=True)
class OutriggerLayout:
    """四支腿矩形布置：纵向 Lx、横向 Ly（m），整机重心相对形心的偏移 (ex, ey)。"""

    lx: float
    ly: float
    ex: float = 0.0
    ey: float = 0.0


def outrigger_reactions(total_load: float, layout: OutriggerLayout) -> dict[str, float]:
    """刚性平台四点支承反力（t）。

    R_ij = W/4 · (1 ± 2·ex/Lx) · (1 ± 2·ey/Ly)
    """
    if layout.lx <= 0 or layout.ly <= 0:
        raise InfeasibleSectionError("支腿跨距必须为正")
    if total_load <= 0:
        raise InfeasibleSectionError("总荷载必须为正")
    if abs(layout.ex) >= layout.lx / 2 or abs(layout.ey) >= layout.ly / 2:
        raise InfeasibleSectionError("重心偏移超出支腿范围，整机将倾覆")

    factor_x = 2.0 * layout.ex / layout.lx
    factor_y = 2.0 * layout.ey / layout.ly
    quarter = total_load / 4.0
    return {
        "左前": quarter * (1 - factor_x) * (1 + factor_y),
        "右前": quarter * (1 + factor_x) * (1 + factor_y),
        "左后": quarter * (1 - factor_x) * (1 - factor_y),
        "右后": quarter * (1 + factor_x) * (1 - factor_y),
    }


def ground_pressure(reaction: float, plate_area: float) -> float:
    if plate_area <= 0:
        raise InfeasibleSectionError("路基板面积必须为正")
    return reaction / plate_area


def angle_to_radius(jib_angle_deg: float, boom_length: float) -> float:
    """臂架角度换算工作半径（理想几何 R = L·cosθ，未计臂架挠度与铰点偏移）。"""
    if boom_length <= 0:
        raise InfeasibleSectionError("臂长必须为正")
    angle = math.radians(jib_angle_deg)
    if not 0 <= angle <= 90:
        raise InfeasibleSectionError("臂架角度须在 [0°, 90°] 内")
    return boom_length * math.cos(angle)
