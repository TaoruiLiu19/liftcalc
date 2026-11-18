"""回转体（Pappus 定理）。

V = θ · R̄ · A
其中 θ 为回转角（rad）、R̄ 为形心到回转轴的距离、A 为母线面积。
"""

from __future__ import annotations

import math

from liftcalc.core.errors import NonPositiveDimensionError
from liftcalc.core.units import Q


def pappus_volume(area: Q, centroid_radius: Q, angle_deg: float = 360.0) -> Q:
    """由母线面积与其形心回转半径求回转体体积。"""
    try:
        area_si = float(area.to("m**2").magnitude)
        radius_si = float(centroid_radius.to("m").magnitude)
    except Exception as exc:
        raise NonPositiveDimensionError(f"面积或半径量纲不正确：{area} / {centroid_radius}") from exc

    if area_si <= 0 or radius_si <= 0:
        raise NonPositiveDimensionError("面积与回转半径都必须为正")
    if not 0 < angle_deg <= 360:
        raise NonPositiveDimensionError("回转角需在 (0, 360] 度")

    theta = math.radians(angle_deg)
    return Q(theta * radius_si * area_si, "m**3")


def pappus_surface(perimeter: Q, centroid_radius: Q, angle_deg: float = 360.0) -> Q:
    """由母线周长求回转面面积（同一定理的面积形式）。"""
    try:
        perimeter_si = float(perimeter.to("m").magnitude)
        radius_si = float(centroid_radius.to("m").magnitude)
    except Exception as exc:
        raise NonPositiveDimensionError(f"周长或半径量纲不正确：{perimeter} / {centroid_radius}") from exc
    if perimeter_si <= 0 or radius_si <= 0:
        raise NonPositiveDimensionError("周长与回转半径都必须为正")
    theta = math.radians(angle_deg)
    return Q(theta * radius_si * perimeter_si, "m**2")
