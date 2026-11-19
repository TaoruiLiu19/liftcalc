"""汽车吊矢量底盘：SVG / PNG / DXF 共用同一套线稿。

轮廓按参考图的像素坐标描点（`docs/handover/assets/原版吊装立面-汽车吊.png` 的车身），
所以形状与素材一致，但**矢量化**——放大不发虚，DXF 里也有车身。

轴数为吨级示意（≤100 t 五轴、100–300 t 六轴、≥300 t 八轴），轮胎按真实直径画，
不是厂商的轴距/轴荷数据。坐标同样走 ``paper``（模型 m → 图面 mm），与立面几何严格对齐。
"""

from __future__ import annotations

import csv
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

# 每个轴数的轴距范围（参考图 px），取够放下 n 个 1.28 m 轮胎且不互相盖住
AXLE_SPANS = {5: (209.0, 726.0), 6: (196.0, 784.0), 8: (168.0, 862.0)}
DEFAULT_AXLES = 5


@lru_cache(maxsize=1)
def _catalog_tonnages() -> dict[tuple[str, str], float]:
    pack = Path(__file__).resolve().parents[1] / "data/pack/crane/models.csv"
    with pack.open(encoding="utf-8-sig", newline="") as stream:
        return {
            (row["brand"], row["model"]): float(row["tonnage_class_t"])
            for row in csv.DictReader(stream)
            if row["tonnage_class_t"]
        }


def axle_count(tonnage: float | None) -> int | None:
    """吨级 → 轴数示意。阈值只是"看起来像那么大的车"，不是厂商参数。"""
    if tonnage is None or tonnage <= 0:
        return None
    if tonnage <= 100:
        return 5
    return 8 if tonnage >= 300 else 6


def drawing_axles(cap: dict, detail: dict, brand: str) -> int | None:
    tonnage = cap.get("tonnage_class")
    if tonnage is None:
        tonnage = _catalog_tonnages().get((brand, detail.get("model") or cap.get("model")))
    return axle_count(tonnage)


def axle_stations(count: int | None) -> tuple[float, ...]:
    """按轴数在参考图上均布轴位（单位：参考图 px）。"""
    if not count:
        return ()
    low, high = AXLE_SPANS.get(count, AXLE_SPANS[DEFAULT_AXLES])
    if count == 1:
        return (low,)
    step = (high - low) / (count - 1)
    return tuple(low + step * index for index in range(count))


def draw_truck(figure: Figure, paper, axles: int | None) -> None:
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

    # 底盘 + 车头轮廓
    contour(((67, 194), (685, 194), (706, 161), (838, 161), (851, 154),
             (969, 154), (979, 160), (995, 208), (1007, 217), (1007, 264),
             (983, 274), (956, 287), (887, 287), (843, 260), (836, 242),
             (765, 242), (750, 258), (743, 287), (691, 287), (691, 216),
             (162, 216), (162, 284), (130, 284), (130, 297), (67, 297)))
    detail((69, 201), (877, 201), (883, 208), (883, 265), (990, 265))
    detail((128, 211), (877, 211))
    # 驾驶室
    contour(((924, 163), (969, 163), (976, 185), (976, 208), (935, 208), (929, 201)),
            fine=True)
    detail((919, 162), (919, 299), (941, 299), (953, 286))
    detail((991, 215), (998, 217), (998, 252), (991, 254), (991, 215))
    # 后视镜
    detail((813, 157), (815, 146), (851, 146), (860, 154))
    detail((858, 151), (875, 138), (875, 124), (880, 124), (893, 154))
    # 支腿箱 / 工具箱
    for left, right in ((133, 160), (694, 720)):
        panel(left, 213, right, 283)
        for level in (227, 246, 265, 280):
            detail((left + 3, level), (right - 3, level))
    panel(73, 194, 100, 287)
    panel(101, 195, 125, 272)
    for left in (400, 448):
        panel(left, 217, left + 44, 284)
        detail((left + 12, 226), (left + 23, 226))

    # 车轮：每轴一轮（立面只见外轮），三道同心圆 + 轮拱
    for station in axle_stations(axles):
        center = (point(station, 0.0)[0], paper(0.0, WHEEL_R)[1])
        for fraction, layer in ((1.0, LAYER_OUTLINE), (0.57, LAYER_THIN),
                                (0.24, LAYER_OUTLINE)):
            figure.add(Circle(*center, WHEEL_R * fraction * paper.s, layer))
        contour(((station - 48, 276), (station - 44, 257), (station - 25, 236),
                 (station + 23, 236), (station + 43, 256), (station + 48, 275)),
                closed=False, fine=True)

    # 平台 / 操纵室
    panel(246, 184, 421, 194, False)
    contour(((193, 149), (203, 142), (223, 89), (285, 85), (301, 138),
             (288, 183), (196, 183)))
    contour(((208, 139), (228, 96), (254, 95), (254, 135)), fine=True)
    contour(((265, 95), (282, 95), (290, 131), (265, 134)), fine=True)
    detail((199, 153), (290, 142))
    detail((200, 172), (282, 172))
    # 回转台与配重
    contour(((293, 183), (301, 151), (377, 117), (387, 108), (511, 109),
             (526, 120), (526, 185)))
    detail((379, 180), (385, 119), (471, 119), (471, 180))
    detail((495, 121), (495, 173))
    contour(((313, 147), (443, 92), (478, 89), (483, 100), (331, 162),
             (324, 180), (299, 180)))
    figure.add(Circle(*point(309, 166), 0.11 * paper.s, LAYER_OUTLINE))
    # 臂架搁架 + 铰点（接到模型铰点，保证与臂架对齐）
    contour(((383, 107), (383, 81), (455, 81), (468, 70), (616, 70),
             (619, 113), (532, 113), (519, 106), (487, 106), (472, 115)))
    figure.add(Circle(*point(561, 94), 0.16 * paper.s, LAYER_THIN))
    hinge = paper(0.0, 4.7)
    figure.add(Polyline((point(296, 150), hinge, point(382, 134)), False, LAYER_OUTLINE))
    figure.add(Circle(*hinge, 0.13 * paper.s, LAYER_OUTLINE))
