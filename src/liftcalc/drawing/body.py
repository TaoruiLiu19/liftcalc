"""汽车吊矢量底盘：SVG / PNG / DXF 共用同一套线稿。

轮廓按参考图的像素坐标描点（`docs/handover/assets/原版吊装立面-汽车吊.png` 的车身），
所以形状与素材一致，但**矢量化**——放大不发虚，DXF 里也有车身。

轴数为吨级示意（≤100 t 四轴、100–300 t 六轴、≥300 t 八轴），轮胎按真实直径画，
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
AXLE_SPANS = {4: (209.0, 726.0), 5: (209.0, 726.0), 6: (196.0, 784.0), 8: (168.0, 862.0)}
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
        return 4
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


def draw_truck(figure: Figure, paper, axles: int | None, hinge: tuple[float, float]) -> None:
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
    # 吨级不明（axles=None）时按描点来源的五轴画，别画成没轮子的车
    for station in axle_stations(axles or DEFAULT_AXLES):
        center = (point(station, 0.0)[0], paper(0.0, WHEEL_R)[1])
        for fraction, layer in ((1.0, LAYER_OUTLINE), (0.57, LAYER_THIN),
                                (0.24, LAYER_OUTLINE)):
            figure.add(Circle(*center, WHEEL_R * fraction * paper.s, layer))
        contour(((station - 48, 276), (station - 44, 257), (station - 25, 236),
                 (station + 23, 236), (station + 43, 256), (station + 48, 275)),
                closed=False, fine=True)

    # 回转平台落在底盘上；臂根销轴和座板共用性能表推导的铰点。
    panel(175, 182, 682, 194, False)
    hx, hy = hinge
    pedestal = (point(186, 182), point(186, 132),
                paper(hx + .43, hy - .24), paper(hx + .39, hy + .16),
                paper(hx + .17, hy + .38), paper(hx - .17, hy + .38),
                paper(hx - .43, hy + .10), paper(hx - .48, hy - .45),
                point(505, 126), point(540, 135), point(540, 182))
    figure.add(Polyline(pedestal, True, LAYER_OUTLINE))
    panel(201, 142, 250, 170)
    for level in (149, 156, 163):
        detail((207, level), (244, level))

    # 上车操纵室位于主臂座靠车头的一侧，窗框、门线与室体一起前移。
    contour(((560, 182), (558, 128), (574, 92), (581, 87),
             (638, 84), (647, 89), (666, 138), (660, 182)))
    contour(((565, 133), (581, 96), (605, 94), (605, 132)), fine=True)
    contour(((614, 94), (636, 92), (652, 130), (614, 132)), fine=True)
    detail((562, 146), (658, 139))
    detail((613, 139), (613, 174), (652, 174))
