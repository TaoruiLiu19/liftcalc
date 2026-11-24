"""汽车吊矢量底盘：SVG / PNG / DXF 共用同一套线稿。

轮廓按参考图的像素坐标描点（`docs/handover/assets/原版吊装立面-汽车吊.png` 的车身），
所以形状与素材一致，但**矢量化**——放大不发虚，DXF 里也有车身。

轴数取机型库 ``models.csv`` 的 ``axles`` 列（来自厂商规格书轴荷表/转向驱动描述的真实车轴数），
查不到的机型按五轴示意描点，轮胎按真实直径画，轴距是示意布局、不是厂商轴距数据。
坐标同样走 ``paper``（模型 m → 图面 mm），与立面几何严格对齐。
"""

from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path

from liftcalc.drawing.primitives import Circle, Figure, Polyline
from liftcalc.drawing.style import LAYER_OUTLINE, LAYER_THIN

# 参考图标定：车身长 942 px 对应 13 m；纵向必须用同一 px/m，否则车身被压扁 10%
TRACE_PX = 942.0
TRACE_M = 13.0
PX_PER_M = TRACE_PX / TRACE_M          # ≈ 72.5 px/m
MODEL_REAR = 3.45                      # 车尾（参考图 x=64 px）距回转中心
BODY_MODEL_FRONT = TRACE_M - MODEL_REAR  # 车头前沿距回转中心 = 9.55 m
GROUND_PX = 328.0                      # 参考图上地面线的 y
WHEEL_R = 0.64                         # 轮胎半径（按参考图轮拱约 1.28 m 直径）
DECK_HEIGHT = (GROUND_PX - 150) / PX_PER_M
CAB_ROOF_HEIGHT = (GROUND_PX - 77) / PX_PER_M
CAB_LEFT_EDGE = MODEL_REAR - (165 - 64) / PX_PER_M
CAB_RIGHT_EDGE = MODEL_REAR - (273 - 64) / PX_PER_M
MAIN_WINCH = (-2.31, 3.02)              # 立面示意坐标 (m)
MAIN_WINCH_RADIUS = .30

# 每个轴数的轴距范围（参考图 px），取够放下 n 个 1.28 m 轮胎且不互相盖住
AXLE_SPANS = {3: (209.0, 620.0), 4: (209.0, 726.0), 5: (209.0, 726.0),
              6: (196.0, 784.0), 7: (168.0, 838.0), 8: (168.0, 862.0)}
DEFAULT_AXLES = 5


@lru_cache(maxsize=1)
def _catalog_axles() -> dict[tuple[str, str], int]:
    """机型库里的真实轴数（厂商规格书提取，非吨级推算）。"""
    pack = Path(__file__).resolve().parents[1] / "data/pack/crane/models.csv"
    with pack.open(encoding="utf-8-sig", newline="") as stream:
        catalog: dict[tuple[str, str], int] = {}
        for row in csv.DictReader(stream):
            value = (row.get("axles") or "").strip()
            if value:
                catalog[(row["brand"], row["model"])] = int(float(value))
        return catalog


def drawing_axles(cap: dict, detail: dict, brand: str) -> int | None:
    """真实轴数：优先结果/机型信息里显式给出的 axles，否则按机型查机型库；
    都查不到返回 None（车身仍按五轴示意描点，不留空底盘）。"""
    for source in (cap, detail):
        value = source.get("axles") if isinstance(source, dict) else None
        if value:
            return int(value)
    return _catalog_axles().get((brand, detail.get("model") or cap.get("model")))


def axle_stations(count: int | None, model_name: str = "") -> tuple[float, ...]:
    """按轴数布置轴位，单位为参考图 px。"""
    if not count:
        return ()
    if count == 4 and model_name == "QY70K-1":
        # 徐工操作手册图 3-1，按车尾到车头换算轴距比例。
        wheelbase = (0.0, 1.350, 5.455, 6.925)
        return tuple(254.0 + 564.0 * offset / wheelbase[-1] for offset in wheelbase)
    low, high = AXLE_SPANS.get(count, AXLE_SPANS[DEFAULT_AXLES])
    if count == 1:
        return (low,)
    step = (high - low) / (count - 1)
    return tuple(low + step * index for index in range(count))


def draw_truck(figure: Figure, paper, axles: int | None, hinge: tuple[float, float],
               model_name: str = "") -> None:
    """按参考图描点画车身；轮胎用真实圆，半径不随轴数变化。"""

    def point(horizontal: float, vertical: float) -> tuple[float, float]:
        return paper(
            MODEL_REAR - (horizontal - 64.0) * TRACE_M / TRACE_PX,
            (GROUND_PX - vertical) / PX_PER_M,
        )

    def contour(vertices, *, closed: bool = True, fine: bool = False) -> None:
        figure.add(Polyline(tuple(point(*vertex) for vertex in vertices), closed,
                            LAYER_THIN if fine else LAYER_OUTLINE))

    def detail(*vertices) -> None:
        contour(vertices, closed=False, fine=True)

    def panel(left: float, top: float, right: float, bottom: float,
              fine: bool = True) -> None:
        contour(((left, top), (right, top), (right, bottom), (left, bottom)), fine=fine)

    # 正投影：底盘梁高于轮胎，轮罩按实际绘制的轴位留空。
    stations = axle_stations(axles or DEFAULT_AXLES, model_name)
    panel(68, 194, 910, 216, False)
    detail((72, 202), (894, 202))
    contour(((68, 216), (135, 216), (135, 246), (117, 258), (68, 258)))
    # 公路驾驶室与前保险杠构成独立轮廓。
    contour(((907, 216), (907, 165), (916, 151), (969, 151),
             (982, 159), (1000, 205), (1007, 215), (1007, 261),
             (992, 271), (923, 271), (909, 255)))
    contour(((917, 163), (964, 159), (976, 167), (989, 199),
             (918, 201)), fine=True)
    detail((925, 205), (925, 249), (976, 249), (984, 237))
    detail((988, 215), (1003, 215), (1003, 226), (987, 226))
    detail((921, 258), (993, 258))
    contour(((690, 194), (701, 165), (716, 157), (882, 157),
             (897, 166), (897, 194)))
    for level in (169, 176, 183):
        detail((730, level), (791, level))
    for left, right in zip(stations, stations[1:]):
        if right - left > 135:
            panel(left + 52, 218, right - 52, 258)
            detail((left + 58, 230), (right - 58, 230))

    # 作业立面的近侧支腿；足板落在车轮共用的地面线上。
    for x, underside in ((88, 258), (970, 271)):
        panel(x - 10, underside, x + 10, 293, False)
        panel(x - 5, 293, x + 5, 323)
        panel(x - 21, 323, x + 21, GROUND_PX, False)

    for station in stations:
        center = (point(station, 0.0)[0], paper(0.0, WHEEL_R)[1])
        for fraction, layer in ((1.0, LAYER_OUTLINE), (0.64, LAYER_THIN),
                                (0.30, LAYER_OUTLINE)):
            figure.add(Circle(*center, WHEEL_R * fraction * paper.s, layer))
        contour(((station - 49, 269), (station - 42, 248), (station - 22, 233),
                 (station + 22, 233), (station + 42, 248), (station + 49, 269)),
                closed=False, fine=True)

    # 回转支承、上车底架和配重分层；臂根耳板直接落在上车底架上。
    panel(252, 186, 446, 194, False)
    contour(((165, 182), (165, 150), (527, 150),
             (548, 157), (675, 157), (675, 186), (208, 186)))
    left_foot, right_foot = (.27, DECK_HEIGHT), (-2.08, DECK_HEIGHT)
    hx, hy = hinge
    head_radius = .50

    def tangent_angle(foot: tuple[float, float], side: int) -> float:
        down = math.atan2(foot[1] - hy, foot[0] - hx)
        return down + side * math.acos(head_radius / math.dist(hinge, foot))

    start = tangent_angle(left_foot, 1)
    sweep = (tangent_angle(right_foot, -1) - start) % math.tau
    angles = (start + sweep * step / 24 for step in range(25))
    head = tuple(paper(hx + head_radius * math.cos(a), hy + head_radius * math.sin(a)) for a in angles)
    pedestal = (paper(*left_foot), *head, paper(*right_foot))
    figure.add(Polyline(pedestal, True, LAYER_OUTLINE))
    contour(((570, 157), (570, 131), (582, 122), (650, 122), (667, 132), (667, 157)))
    for level in (137, 146):
        detail((573, level), (665, level))

    # 主、副卷扬位于臂根外侧，操纵室位于平台左端。
    winch_frame = ((-2.08, DECK_HEIGHT), (-1.96, 3.27), (-2.12, 3.43),
                   (-3.29, 3.43), (-3.47, 3.25), (-3.47, (GROUND_PX - 157) / PX_PER_M))
    figure.add(Polyline(tuple(paper(*p) for p in winch_frame), False, LAYER_OUTLINE))
    for center, radius in ((MAIN_WINCH, MAIN_WINCH_RADIUS), ((-3.08, 3.02), .26)):
        figure.add(Circle(*paper(*center), radius * paper.s, LAYER_OUTLINE),
                   Circle(*paper(*center), .07 * paper.s, LAYER_THIN))

    contour(((167, 150), (165, 121), (174, 99), (188, 80),
             (224, 77), (245, 80), (254, 87), (273, 131), (267, 150)))
    contour(((172, 126), (181, 100), (191, 89), (212, 87), (212, 125)), fine=True)
    contour(((221, 87), (242, 86), (249, 92), (259, 123), (221, 125)), fine=True)
    detail((169, 139), (265, 132))
    detail((220, 132), (220, 145), (259, 145))
