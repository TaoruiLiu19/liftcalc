"""吊物几何与重心：四索夹角/索力、所需起升高度、双机按重心分载。

坐标约定（吊物局部坐标，原点在吊物**形心**）：

* ``x`` 沿吊物长度方向，水平，指向**远离吊车**一侧；
* ``y`` 沿吊物宽度方向，水平，垂直立面（``+y`` 为靠近观察者一侧，记「前」）；
* ``z`` 竖向向上。

吊物按长方体看待：``length`` × ``width`` × ``height``，形心在体心。
重心用相对形心的偏移 ``(cg_x, cg_y, cg_z)`` 描述，这是现场最容易核对的写法
（偏心量直接量自形心）。

四个吊点默认在顶面四角，可用 ``lug_inset`` 向形心内缩。吊钩位于四吊点形心
（也就是吊物形心）正上方，吊索从吊钩接到四个吊点。

索力模型（静力、线分配，与支腿反力同一套假定）::

    R_i = W/4 · (1 + s_x·2e_x/L_x) · (1 + s_y·2e_y/L_y)
    T_i = R_i / cos θ_i,   tan θ_i = run_i / h_sling

式中 ``L_x = 到位后两吊点的 x 跨距``、``L_y`` 为 y 跨距，``e`` 为重心相对吊点
形心的偏心，``run_i`` 为吊点在水平面上到吊钩投影的距离。偏心时四根索受力不同，
这就是"重心偏心时四根索力不均"的来源。

该模型假定吊钩位于吊点形心正上方、吊物保持水平。重心偏心时吊物实际会倾斜到
重心落到吊钩正下方为止；倾斜量由现场倒链调平消除，本模块在 ``notes`` 里写明。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from liftcalc.core.errors import InfeasibleSectionError

#: 未给吊索高度时，按"最短的一根索与水平面成 60°"推算吊索竖向高度
DEFAULT_SLING_ANGLE_TO_HORIZONTAL = 60.0
#: 索与竖直夹角超过此值（即与水平夹角小于 45°）要提示
MAX_SLING_ANGLE_FROM_VERTICAL = 45.0
#: 重心偏心的数值容差（m），小于它按"无偏心"处理
CG_TOL = 1e-6


@dataclass(frozen=True)
class LoadShape:
    """吊物长方体 + 重心偏心 + 吊点内缩 + 吊索高度（全部 m）。"""

    length: float = 3.2
    width: float = 3.2
    height: float = 3.8
    cg_x: float = 0.0
    cg_y: float = 0.0
    cg_z: float = 0.0
    lug_inset: float = 0.0
    sling_height: float | None = None

    def validate(self) -> None:
        for name, value in (("长", self.length), ("宽", self.width), ("高", self.height)):
            if not math.isfinite(value) or value <= 0:
                raise InfeasibleSectionError(f"吊物{name}度必须为正")
        if not math.isfinite(self.lug_inset) or self.lug_inset < 0:
            raise InfeasibleSectionError("吊点内缩距离不得为负")
        if 2 * self.lug_inset >= min(self.length, self.width):
            raise InfeasibleSectionError("吊点内缩过大，两个吊点已经重合")
        if abs(self.cg_x) > self.length / 2 + CG_TOL:
            raise InfeasibleSectionError("重心超出吊物长度范围，请检查重心坐标")
        if abs(self.cg_y) > self.width / 2 + CG_TOL:
            raise InfeasibleSectionError("重心超出吊物宽度范围，请检查重心坐标")
        if abs(self.cg_z) > self.height / 2 + CG_TOL:
            raise InfeasibleSectionError("重心超出吊物高度范围，请检查重心坐标")
        if self.sling_height is not None and (
            not math.isfinite(self.sling_height) or self.sling_height <= 0
        ):
            raise InfeasibleSectionError("吊索高度必须为正")

    # ---- 派生量 -----------------------------------------------------------
    @property
    def lug_x(self) -> float:
        return self.length / 2 - self.lug_inset

    @property
    def lug_y(self) -> float:
        return self.width / 2 - self.lug_inset

    @property
    def cg_from_lug_center(self) -> tuple[float, float]:
        """重心相对四吊点形心的偏心（吊点对称布置时即相对形心）。"""
        return self.cg_x, self.cg_y

    def default_sling_height(self) -> float:
        """按最短索与水平成 60° 推算吊索竖向高度。"""
        run = math.hypot(self.lug_x, self.lug_y)
        return run * math.tan(math.radians(DEFAULT_SLING_ANGLE_TO_HORIZONTAL))


@dataclass(frozen=True)
class Lug:
    """吊点：顶面一个角点（吊物局部坐标，m）。"""

    index: int
    name: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Sling:
    """一根吊索的几何与受力。"""

    index: int
    name: str
    x: float
    y: float
    run: float            # 吊点到吊钩投影的水平距离
    length: float         # 吊索展开长度（吊钩中心到吊点）
    angle_deg: float      # 与竖直方向的夹角
    share: float          # 竖向分载比例（四根之和为 1）
    force_t: float        # 索力（t）


@dataclass(frozen=True)
class SlingReport:
    slings: tuple[Sling, ...]
    sling_height: float
    derived_height: bool
    max_force_t: float
    min_force_t: float
    max_angle_deg: float
    min_angle_deg: float
    notes: tuple[str, ...]


@dataclass(frozen=True)
class DualSplit:
    """双机抬吊的负荷分配。"""

    left_share: float
    right_share: float
    left_x: float
    right_x: float
    basis: str            # "cg" 按重心 | "ratio" 兜底比例


def lugs(shape: LoadShape) -> tuple[Lug, ...]:
    """四个顶面角点，按「远前 / 近前 / 远后 / 近后」排列。"""
    x, y, z = shape.lug_x, shape.lug_y, shape.height / 2
    return (
        Lug(1, "远前", x, y, z),
        Lug(2, "近前", -x, y, z),
        Lug(3, "远后", x, -y, z),
        Lug(4, "近后", -x, -y, z),
    )


def sling_report(shape: LoadShape, weight_t: float) -> SlingReport:
    """四索几何与索力。weight_t 是吊件重量（t），不含吊钩与索具。"""
    shape.validate()
    if not math.isfinite(weight_t) or weight_t <= 0:
        raise InfeasibleSectionError("吊件重量必须为正")

    derived = shape.sling_height is None
    height = shape.default_sling_height() if derived else float(shape.sling_height or 0.0)
    if height <= 0:
        raise InfeasibleSectionError("吊索高度必须为正")

    span_x = 2 * shape.lug_x
    span_y = 2 * shape.lug_y
    fx = 2 * shape.cg_x / span_x
    fy = 2 * shape.cg_y / span_y
    if abs(fx) >= 1 or abs(fy) >= 1:
        raise InfeasibleSectionError(
            "重心超出四个吊点围成的范围，吊物会倾覆；请调整吊点位置或重心"
        )

    quarter = weight_t / 4.0
    items: list[Sling] = []
    for lug in lugs(shape):
        sx = 1.0 if lug.x > 0 else -1.0
        sy = 1.0 if lug.y > 0 else -1.0
        share = quarter * (1 + sx * fx) * (1 + sy * fy)
        run = math.hypot(lug.x, lug.y)
        angle = math.degrees(math.atan2(run, height))
        force = share / math.cos(math.radians(angle))
        items.append(
            Sling(
                index=lug.index,
                name=lug.name,
                x=lug.x,
                y=lug.y,
                run=run,
                length=math.hypot(run, height),
                angle_deg=angle,
                share=share / weight_t,
                force_t=force,
            )
        )

    forces = [item.force_t for item in items]
    angles = [item.angle_deg for item in items]
    notes: list[str] = []
    if derived:
        notes.append(
            f"未给吊索高度，按最短索与水平成 {DEFAULT_SLING_ANGLE_TO_HORIZONTAL:.0f}° "
            f"推算为 {height:.2f} m"
        )
    if max(angles) > MAX_SLING_ANGLE_FROM_VERTICAL + 1e-9:
        notes.append(
            f"索与竖直夹角最大 {max(angles):.1f}°，超过 {MAX_SLING_ANGLE_FROM_VERTICAL:.0f}°，"
            "建议加长吊索或改用横梁"
        )
    if max(forces) - min(forces) > 1e-6:
        notes.append(
            f"重心偏心使四索受力不均：最大 {max(forces):.2f} t、最小 {min(forces):.2f} t"
            f"（相差 {max(forces) / max(min(forces), 1e-9):.2f} 倍）"
        )
    if abs(shape.cg_x) > CG_TOL or abs(shape.cg_y) > CG_TOL:
        notes.append(
            "重心偏心时吊物自由悬挂会倾斜到重心位于吊钩正下方；本计算按吊钩位于吊点"
            "形心正上方、吊物保持水平作静力分配，倾斜量应由倒链调平消除"
        )

    return SlingReport(
        slings=tuple(items),
        sling_height=height,
        derived_height=derived,
        max_force_t=max(forces),
        min_force_t=min(forces),
        max_angle_deg=max(angles),
        min_angle_deg=min(angles),
        notes=tuple(notes),
    )


def required_lift_height(shape: LoadShape, clearance: float) -> float:
    """所需起升高度 = 吊物底净空 + 吊物高度 + 吊索竖直高度（吊钩中心离地）。"""
    if not math.isfinite(clearance) or clearance < 0:
        raise InfeasibleSectionError("吊物底净空不得为负")
    report = sling_report(shape, weight_t=1.0)
    return clearance + shape.height + report.sling_height


def dual_split(
    shape: LoadShape,
    *,
    left_x: float | None = None,
    right_x: float | None = None,
) -> DualSplit:
    """双机抬吊：按重心在两吊点之间的位置分配负荷。

    左吊点在 ``left_x``、右吊点在 ``right_x``（吊物局部坐标，m），默认取两端吊点。
    重心越靠近哪台，哪台分到的荷载越大。
    """
    shape.validate()
    left = -shape.lug_x if left_x is None else float(left_x)
    right = shape.lug_x if right_x is None else float(right_x)
    if not right > left:
        raise InfeasibleSectionError("双机吊点位置需满足右吊点在左吊点右侧")
    if not left <= shape.cg_x <= right:
        raise InfeasibleSectionError(
            "重心落在两台吊车的吊点之外，吊物会倾覆；请调整吊点或重心"
        )
    left_share = (right - shape.cg_x) / (right - left)
    return DualSplit(
        left_share=left_share,
        right_share=1.0 - left_share,
        left_x=left,
        right_x=right,
        basis="cg",
    )


def fallback_split(ratio: float = 0.6) -> DualSplit:
    """没有重心信息时的兜底分配（默认 60/40）。"""
    if not 0 < ratio < 1:
        raise InfeasibleSectionError("分配比例需在 (0, 1) 内")
    return DualSplit(
        left_share=ratio,
        right_share=1.0 - ratio,
        left_x=0.0,
        right_x=0.0,
        basis="ratio",
    )
