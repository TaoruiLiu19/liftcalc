"""汽车吊矢量底盘：所有格式共用；轮距与轴数为吨级示意，不是厂商参数。

坐标同样走 ``paper``（模型 m → 图面 mm），故与立面几何严格对齐。
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from liftcalc.drawing.primitives import Circle, Figure, Polyline
from liftcalc.drawing.style import LAYER_OUTLINE, LAYER_THIN

# 轴距（m，模型 x：正值朝吊物侧即车尾，负值朝车头）
@lru_cache(maxsize=1)
def _catalog_tonnages():
    pack = Path(__file__).resolve().parents[1] / 'data/pack/crane/models.csv'
    with pack.open(encoding='utf-8-sig', newline='') as stream:
        return {(row['brand'], row['model']): float(row['tonnage_class_t'])
                for row in csv.DictReader(stream) if row['tonnage_class_t']}


def axle_count(tonnage: float | None) -> int | None:
    if tonnage is None or tonnage <= 0:
        return None
    return 4 if tonnage <= 100 else 8 if tonnage >= 300 else 6


def drawing_axles(cap: dict, detail: dict, brand: str) -> int | None:
    tonnage = cap.get('tonnage_class')
    if tonnage is None:
        tonnage = _catalog_tonnages().get((brand, detail.get('model') or cap.get('model')))
    return axle_count(tonnage)

WHEEL_R = 0.55


def draw_truck(figure: Figure, paper, axles: int | None) -> None:
    """Trace the carrier in reference-image coordinates; tyres remain true circles."""
    def point(horizontal, vertical):
        return paper(3.45 - (horizontal - 64) * 13 / 942, (328 - vertical) / 80)

    def contour(vertices, *, closed=True, fine=False):
        figure.add(Polyline(tuple(point(*vertex) for vertex in vertices), closed,
                            LAYER_THIN if fine else LAYER_OUTLINE))

    def detail(*vertices):
        contour(vertices, closed=False, fine=True)

    def panel(left, top, right, bottom, fine=True):
        contour(((left, top), (right, top), (right, bottom), (left, bottom)), fine=fine)

    contour(((67, 194), (685, 194), (706, 161), (838, 161), (851, 154),
             (969, 154), (979, 160), (995, 208), (1007, 217), (1007, 264),
             (983, 274), (956, 287), (887, 287), (843, 260), (836, 242),
             (765, 242), (750, 258), (743, 287), (691, 287), (691, 216),
             (162, 216), (162, 284), (130, 284), (130, 297), (67, 297)))
    detail((69, 201), (877, 201), (883, 208), (883, 265), (990, 265))
    detail((128, 211), (877, 211))
    contour(((924, 163), (969, 163), (976, 185), (976, 208), (935, 208),
             (929, 201)), fine=True)
    detail((919, 162), (919, 299), (941, 299), (953, 286))
    detail((991, 215), (998, 217), (998, 252), (991, 254), (991, 215))
    detail((813, 157), (815, 146), (851, 146), (860, 154))
    detail((858, 151), (875, 138), (875, 124), (880, 124), (893, 154))
    for left, right in ((133, 160), (694, 720)):
        panel(left, 213, right, 283)
        for level in (227, 246, 265, 280):
            detail((left + 3, level), (right - 3, level))
    panel(73, 194, 100, 287)
    panel(101, 195, 125, 272)
    for left in (400, 448):
        panel(left, 217, left + 44, 284)
        detail((left + 12, 226), (left + 23, 226))

    groups = {4: (220, 334, 625, 805), 6: (218, 320, 421, 594, 698, 805),
              8: (176, 269, 362, 455, 548, 641, 734, 827)}
    for station in groups.get(axles, ()):
        center = point(station, 284)
        for fraction, layer in ((1, LAYER_OUTLINE), (.57, LAYER_THIN), (.24, LAYER_OUTLINE)):
            figure.add(Circle(*center, WHEEL_R * fraction * paper.s, layer))
        contour(((station - 48, 276), (station - 44, 257), (station - 25, 236),
                 (station + 23, 236), (station + 43, 256), (station + 48, 275)), closed=False, fine=True)

    panel(246, 184, 421, 194, False)
    contour(((193, 149), (203, 142), (223, 89), (285, 85), (301, 138),
             (288, 183), (196, 183)))
    contour(((208, 139), (228, 96), (254, 95), (254, 135)), fine=True)
    contour(((265, 95), (282, 95), (290, 131), (265, 134)), fine=True)
    detail((199, 153), (290, 142))
    detail((200, 172), (282, 172))
    contour(((293, 183), (301, 151), (377, 117), (387, 108), (511, 109),
             (526, 120), (526, 185)))
    detail((379, 180), (385, 119), (471, 119), (471, 180))
    detail((495, 121), (495, 173))
    contour(((313, 147), (443, 92), (478, 89), (483, 100), (331, 162),
             (324, 180), (299, 180)))
    figure.add(Circle(*point(309, 166), .11 * paper.s, LAYER_OUTLINE))
    contour(((383, 107), (383, 81), (455, 81), (468, 70), (616, 70),
             (619, 113), (532, 113), (519, 106), (487, 106), (472, 115)))
    figure.add(Circle(*point(561, 94), .16 * paper.s, LAYER_THIN))
    hinge = paper(0, 4.7)
    figure.add(Polyline((point(296, 150), hinge, point(382, 134)), False, LAYER_OUTLINE))
    figure.add(Circle(*hinge, .13 * paper.s, LAYER_OUTLINE))
