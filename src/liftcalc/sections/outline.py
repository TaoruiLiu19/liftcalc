"""截面轮廓（几何形状的唯一来源）。

截面特性计算与绘图都从这里取轮廓，避免两处各写一套形状。
坐标单位：米。
"""

from __future__ import annotations

import math

Point = tuple[float, float]
Polygon = list[Point]


def rect(b: float, h: float) -> tuple[list[Polygon], list[Polygon]]:
    return [[(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]], []


def box(b: float, h: float, t: float) -> tuple[list[Polygon], list[Polygon]]:
    outer = [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    ib, ih = b - 2 * t, h - 2 * t
    inner = [(-ib / 2, -ih / 2), (ib / 2, -ih / 2), (ib / 2, ih / 2), (-ib / 2, ih / 2)]
    return [outer], [inner]


def i_section(h: float, b: float, tw: float, tf: float) -> tuple[list[Polygon], list[Polygon]]:
    hb, hh = b / 2, h / 2
    poly: Polygon = [
        (-hb, -hh),
        (hb, -hh),
        (hb, -hh + tf),
        (tw / 2, -hh + tf),
        (tw / 2, hh - tf),
        (hb, hh - tf),
        (hb, hh),
        (-hb, hh),
        (-hb, hh - tf),
        (-tw / 2, hh - tf),
        (-tw / 2, -hh + tf),
        (-hb, -hh + tf),
    ]
    return [poly], []


def channel(h: float, b: float, tw: float, tf: float) -> tuple[list[Polygon], list[Polygon]]:
    poly: Polygon = [
        (0.0, -h / 2),
        (b, -h / 2),
        (b, -h / 2 + tf),
        (tw, -h / 2 + tf),
        (tw, h / 2 - tf),
        (b, h / 2 - tf),
        (b, h / 2),
        (0.0, h / 2),
    ]
    return [poly], []


def t_section(h: float, b: float, tw: float, tf: float) -> tuple[list[Polygon], list[Polygon]]:
    poly: Polygon = [
        (-tw / 2, -h / 2),
        (tw / 2, -h / 2),
        (tw / 2, h / 2 - tf),
        (b / 2, h / 2 - tf),
        (b / 2, h / 2),
        (-b / 2, h / 2),
        (-b / 2, h / 2 - tf),
        (-tw / 2, h / 2 - tf),
    ]
    return [poly], []


def angle_section(b_long: float, b_short: float, t: float) -> tuple[list[Polygon], list[Polygon]]:
    poly: Polygon = [(0.0, 0.0), (b_long, 0.0), (b_long, t), (t, t), (t, b_short), (0.0, b_short)]
    return [poly], []


def _ngon(radius: float, segments: int = 72) -> Polygon:
    return [
        (radius * math.cos(2 * math.pi * index / segments), radius * math.sin(2 * math.pi * index / segments))
        for index in range(segments)
    ]


def circle(d: float, segments: int = 72) -> tuple[list[Polygon], list[Polygon]]:
    """仅用于绘图/示意；截面积分走解析解。"""
    return [_ngon(d / 2, segments)], []


def annulus(d_outer: float, d_inner: float, segments: int = 72) -> tuple[list[Polygon], list[Polygon]]:
    return [_ngon(d_outer / 2, segments)], [_ngon(d_inner / 2, segments)]
