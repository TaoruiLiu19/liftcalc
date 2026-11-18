"""规则立体的体积与形心（解析公式）。

约定：**基准点在底/贴合面中心**，形心坐标自基准点量起，单位 m。
这样多件装配时可以直接按标高相加，不必来回换基准。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from liftcalc.core.errors import NonPositiveDimensionError
from liftcalc.core.units import Q


@dataclass(frozen=True)
class Solid:
    name: str
    volume: Q
    centroid: tuple[Q, Q, Q]
    area_reference: Q | None = None  # 可选：贴合面面积，用于校核


def _pos(value: Q, label: str) -> float:
    try:
        magnitude = float(value.to("m").magnitude)
    except Exception as exc:
        raise NonPositiveDimensionError(f"{label} 需要长度单位：{value}") from exc
    if magnitude <= 0:
        raise NonPositiveDimensionError(f"{label} 必须为正：{magnitude} m")
    return magnitude


def _nonneg(value: Q, label: str) -> float:
    try:
        magnitude = float(value.to("m").magnitude)
    except Exception as exc:
        raise NonPositiveDimensionError(f"{label} 需要长度单位：{value}") from exc
    if magnitude < 0:
        raise NonPositiveDimensionError(f"{label} 不得为负：{magnitude} m")
    return magnitude


def _mk(name: str, volume: float, cx: float, cy: float, cz: float) -> Solid:
    return Solid(
        name=name,
        volume=Q(volume, "m**3"),
        centroid=(Q(cx, "m"), Q(cy, "m"), Q(cz, "m")),
    )


def box(a: Q, b: Q, c: Q) -> Solid:
    """长方体：a×b 为底面，c 为高。"""
    aa, bb, cc = _pos(a, "长 a"), _pos(b, "宽 b"), _pos(c, "高 c")
    return _mk("box", aa * bb * cc, 0.0, 0.0, cc / 2)


def cylinder(d: Q, h: Q) -> Solid:
    """实心圆柱。"""
    dd, hh = _pos(d, "直径 d"), _pos(h, "高 h")
    return _mk("cylinder", math.pi * dd**2 / 4 * hh, 0.0, 0.0, hh / 2)


def hollow_cylinder(d_outer: Q, d_inner: Q, h: Q) -> Solid:
    """空心圆柱（管）。"""
    do, di, hh = _pos(d_outer, "外径"), _pos(d_inner, "内径"), _pos(h, "高 h")
    if di >= do:
        raise NonPositiveDimensionError("内径必须小于外径")
    volume = math.pi * (do**2 - di**2) / 4 * hh
    return _mk("hollow_cylinder", volume, 0.0, 0.0, hh / 2)


def sphere(d: Q) -> Solid:
    """球：基准点为球底切点，形心在球心。"""
    dd = _pos(d, "直径 d")
    return _mk("sphere", math.pi * dd**3 / 6, 0.0, 0.0, dd / 2)


def spherical_cap(d: Q, h: Q) -> Solid:
    """球缺（封头）：h 为从球心所在平面量起的高度。

    形心自切平面量起：z̄ = h(4R − h) / (4(3R − h))
    """
    dd, hh = _pos(d, "球径 d"), _pos(h, "球缺高 h")
    radius = dd / 2
    if hh > radius:
        raise NonPositiveDimensionError("球缺高不得超过球半径（本实现仅覆盖 ≤1/2 球）")
    volume = math.pi * hh**2 * (3 * radius - hh) / 3
    cz = hh * (4 * radius - hh) / (4 * (3 * radius - hh))
    return _mk("spherical_cap", volume, 0.0, 0.0, cz)


def ellipsoid_head(d: Q) -> Solid:
    """2:1 标准椭圆封头（不含直边段）。

    V = πD³/24，形心自切平面量起 z̄ = 3D/32
    """
    dd = _pos(d, "封头直径 d")
    volume = math.pi * dd**3 / 24
    return _mk("ellipsoid_head", volume, 0.0, 0.0, 3 * dd / 32)


def cone_frustum(d_bottom: Q, d_top: Q, h: Q) -> Solid:
    """圆台（锥台）：形心自底面量起。顶径可为 0（退化为圆锥）。"""
    db, dt, hh = _pos(d_bottom, "底径"), _nonneg(d_top, "顶径"), _pos(h, "高 h")
    r1, r2 = db / 2, dt / 2
    volume = math.pi * hh * (r1 * r1 + r1 * r2 + r2 * r2) / 3
    cz = hh * (r1 * r1 + 2 * r1 * r2 + 3 * r2 * r2) / (4 * (r1 * r1 + r1 * r2 + r2 * r2))
    return _mk("cone_frustum", volume, 0.0, 0.0, cz)


def elbow(d_outer: Q, d_inner: Q, bend_radius: Q, angle_deg: float = 90.0) -> Solid:
    """弯管（环形扇区）。

    局部坐标：弯头中心在原点，入射端沿 +x、出口绕 z 轴转过 angle。
    形心在角平分线上，距弯头中心 R。
    """
    do, di, radius = _pos(d_outer, "外径"), _pos(d_inner, "内径"), _pos(bend_radius, "弯曲半径")
    if di >= do:
        raise NonPositiveDimensionError("内径必须小于外径")
    if not 0 < angle_deg <= 360:
        raise NonPositiveDimensionError("弯管角度需在 (0, 360] 度")
    theta = math.radians(angle_deg)
    area = math.pi * (do**2 - di**2) / 4
    volume = area * radius * theta
    half = theta / 2
    return _mk("elbow", volume, radius * math.cos(half), radius * math.sin(half), 0.0)


def torus(d_tube: Q, bend_radius: Q) -> Solid:
    """整圈环体（360° 弯管）。"""
    dt, radius = _pos(d_tube, "管径"), _pos(bend_radius, "环半径")
    tube_radius = dt / 2
    volume = 2 * math.pi**2 * radius * tube_radius**2
    return _mk("torus", volume, 0.0, 0.0, 0.0)
