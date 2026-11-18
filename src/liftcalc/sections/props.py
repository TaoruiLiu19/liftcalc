"""截面几何特性的数值核心。

坐标系：x 水平、y 竖向向上，单位 **米**（内部约定）。

公开 API 一律接受/返回 `pint.Quantity`；本模块内部先归一为 SI 浮点，
以避免在积分过程中反复搬运单位（这是唯一允许"裸浮点长度"的层，
且不对外暴露）。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from liftcalc.core.errors import DegenerateGeometryError, NonPositiveAreaError
from liftcalc.core.units import Q
from liftcalc.sections.models import RawIntegrals, SectionProps, empty_integrals

Point = tuple[float, float]
Polygon = Sequence[Point]


def _clamp_zero(value: float, tol: float = 1e-12) -> float:
    """把数值噪声导致的极小负值归零。"""
    return 0.0 if abs(value) < tol else value


def raw_integrals(points: Polygon) -> RawIntegrals:
    """用格林公式求多边形关于原点的有符号积分（精确，非网格近似）。

    面积：A = 1/2 Σ cross
    一次矩：Ax = 1/6 Σ (x_i + x_{i+1}) cross
    二次矩：Ix = 1/12 Σ (y_i² + y_i y_{i+1} + y_{i+1}²) cross
    """
    if len(points) < 3:
        raise DegenerateGeometryError("多边形至少需要 3 个顶点", points=len(points))

    area = ax = ay = ixo = iyo = ixylo = 0.0
    x_min = y_min = math.inf
    x_max = y_max = -math.inf

    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        cross = x1 * y2 - x2 * y1
        area += cross
        ax += (x1 + x2) * cross
        ay += (y1 + y2) * cross
        ixo += (y1 * y1 + y1 * y2 + y2 * y2) * cross
        iyo += (x1 * x1 + x1 * x2 + x2 * x2) * cross
        ixylo += (x1 * y2 + x2 * y1 + 2 * x1 * y1 + 2 * x2 * y2) * cross
        x_min = min(x_min, x1)
        x_max = max(x_max, x1)
        y_min = min(y_min, y1)
        y_max = max(y_max, y1)

    return RawIntegrals(
        area=area / 2.0,
        ax=ax / 6.0,
        ay=ay / 6.0,
        ixo=ixo / 12.0,
        iyo=iyo / 12.0,
        ixylo=ixylo / 24.0,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
    )


def _reverse(points: Polygon) -> list[Point]:
    return list(reversed(list(points)))


def make_section(
    *,
    area: float,
    cx: float,
    cy: float,
    ix: float,
    iy: float,
    ixy: float,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    torsion: float | None = None,
) -> SectionProps:
    """由质心系积分构造 SectionProps（补齐主轴、模量、回转半径）。"""
    if area <= 0:
        raise NonPositiveAreaError(f"截面面积必须为正：{area}")

    ix = _clamp_zero(ix)
    iy = _clamp_zero(iy)

    avg = (ix + iy) / 2.0
    radius = math.hypot((ix - iy) / 2.0, ixy)
    i1 = avg + radius
    i2 = avg - radius
    theta = 0.5 * math.atan2(2.0 * ixy, ix - iy)

    dx_left = cx - x_min
    dx_right = x_max - cx
    dy_top = y_max - cy
    dy_bottom = cy - y_min
    if dy_top <= 0 or dy_bottom <= 0 or dx_left <= 0 or dx_right <= 0:
        raise NonPositiveAreaError("截面包围盒退化，无法求截面模量")

    wx = ix / max(dy_top, dy_bottom)
    wy = iy / max(dx_left, dx_right)
    rx = math.sqrt(ix / area)
    ry = math.sqrt(iy / area)

    return SectionProps(
        area=Q(area, "m**2"),
        cx=Q(cx, "m"),
        cy=Q(cy, "m"),
        ix=Q(ix, "m**4"),
        iy=Q(iy, "m**4"),
        ixy=Q(ixy, "m**4"),
        i1=Q(i1, "m**4"),
        i2=Q(i2, "m**4"),
        principal_angle_deg=math.degrees(theta),
        wx=Q(wx, "m**3"),
        wy=Q(wy, "m**3"),
        rx=Q(rx, "m"),
        ry=Q(ry, "m"),
        y_top=Q(y_max, "m"),
        y_bottom=Q(y_min, "m"),
        x_left=Q(x_min, "m"),
        x_right=Q(x_max, "m"),
        torsion_constant=None if torsion is None else Q(torsion, "m**4"),
    )


def section_from_polygons(
    regions: Sequence[Polygon],
    holes: Sequence[Polygon] = (),
    *,
    torsion_constant: float | None = None,
) -> SectionProps:
    """由若干实心区域与孔洞求组合截面（孔洞自动反绕，积分为负）。"""
    total = empty_integrals()
    for region in regions:
        total = total + raw_integrals(region)
    for hole in holes:
        total = total + raw_integrals(_reverse(hole))

    if total.area < 0:
        # 顶点总体为顺时针：整体翻号，得到一个正面积区域
        total = RawIntegrals(
            area=-total.area,
            ax=-total.ax,
            ay=-total.ay,
            ixo=-total.ixo,
            iyo=-total.iyo,
            ixylo=-total.ixylo,
            x_min=total.x_min,
            x_max=total.x_max,
            y_min=total.y_min,
            y_max=total.y_max,
        )

    area = total.area
    if area <= 0:
        raise NonPositiveAreaError("组合截面净面积不为正，请检查孔洞尺寸")

    cx = total.ax / area
    cy = total.ay / area
    ix = total.ixo - area * cy * cy
    iy = total.iyo - area * cx * cx
    ixy = total.ixylo - area * cx * cy

    return make_section(
        area=area,
        cx=cx,
        cy=cy,
        ix=ix,
        iy=iy,
        ixy=ixy,
        x_min=total.x_min,
        x_max=total.x_max,
        y_min=total.y_min,
        y_max=total.y_max,
        torsion=torsion_constant,
    )
