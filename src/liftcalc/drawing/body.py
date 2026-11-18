"""汽车吊车身矢量简图（DXF 用）。

DXF 不支持位图块，而 SVG/PNG 可以贴原版车身素材。为了让 DXF 也是一张
完整的图，这里按真实轴距/外形比例画一个简化车身：车架、五轴车轮、
驾驶室、回转台与配重、臂架搁架、支腿梁。

坐标同样走 ``paper``（模型 m → 图面 mm），故与立面几何严格对齐。
"""

from __future__ import annotations

from liftcalc.drawing.primitives import Circle, Figure, Line, Polyline
from liftcalc.drawing.style import LAYER_OUTLINE, LAYER_THIN

# 轴距（m，模型 x：正值朝吊物侧即车尾，负值朝车头）
AXLES = (1.05, -0.55, -2.15, -3.75, -5.95)
WHEEL_R = 0.55
DECK_Y = 1.30
ROOF_Y = 2.05
CAB_FRONT = -9.55
CAB_BACK = -6.60
CAB_TOP = 3.55
HOUSE_REAR = 3.45
HOUSE_FRONT = -0.20
HOUSE_TOP = 4.40
COUNTERWEIGHT = (2.55, 3.45)


def _rect(paper, x0: float, x1: float, y0: float, y1: float) -> Polyline:
    return Polyline(
        points=tuple(paper(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))),
        closed=True,
        layer=LAYER_OUTLINE,
    )


def draw_truck(figure: Figure, paper) -> None:
    """在立面上画简化车身（含车轮、驾驶室、回转台、配重）。"""
    x_rear, x_front = HOUSE_REAR, CAB_FRONT

    # 车架
    figure.add(_rect(paper, x_front, x_rear, 0.72, DECK_Y))

    # 车轮（每轴一轮，左右不做区分——立面图只看得到外轮）
    for axle in AXLES:
        center = paper(axle, WHEEL_R)
        figure.add(
            Circle(cx=center[0], cy=center[1], r=WHEEL_R * paper.s, layer=LAYER_OUTLINE),
            Circle(cx=center[0], cy=center[1], r=WHEEL_R * 0.45 * paper.s,
                   layer=LAYER_THIN),
        )

    # 驾驶室（车头，前低后高）
    figure.add(
        Polyline(
            points=tuple(
                paper(x, y)
                for x, y in ((x_front, DECK_Y), (CAB_FRONT + 0.15, CAB_TOP),
                             (CAB_BACK, CAB_TOP), (CAB_BACK, DECK_Y))
            ),
            closed=True,
            layer=LAYER_OUTLINE,
        )
    )
    # 风挡
    figure.add(
        Line(x1=paper(CAB_FRONT + 0.35, CAB_TOP - 0.15)[0],
             y1=paper(CAB_FRONT + 0.35, CAB_TOP - 0.15)[1],
             x2=paper(CAB_FRONT + 0.75, DECK_Y + 0.25)[0],
             y2=paper(CAB_FRONT + 0.75, DECK_Y + 0.25)[1], layer=LAYER_OUTLINE),
        Line(x1=paper(CAB_BACK + 0.25, DECK_Y + 0.15)[0],
             y1=paper(CAB_BACK + 0.25, DECK_Y + 0.15)[1],
             x2=paper(CAB_BACK + 0.25, CAB_TOP - 0.15)[0],
             y2=paper(CAB_BACK + 0.25, CAB_TOP - 0.15)[1], layer=LAYER_THIN),
    )

    # 回转台与配重
    figure.add(
        _rect(paper, HOUSE_FRONT, HOUSE_REAR, DECK_Y, DECK_Y + 0.30),
        _rect(paper, HOUSE_FRONT, HOUSE_REAR, DECK_Y + 0.30, HOUSE_TOP),
    )
    # 回转台侧窗
    figure.add(
        Line(x1=paper(COUNTERWEIGHT[0], DECK_Y + 0.75)[0],
             y1=paper(COUNTERWEIGHT[0], DECK_Y + 0.75)[1],
             x2=paper(COUNTERWEIGHT[0], HOUSE_TOP - 0.35)[0],
             y2=paper(COUNTERWEIGHT[0], HOUSE_TOP - 0.35)[1], layer=LAYER_THIN)
    )
    # 操纵室（回转台上靠车头一侧）
    figure.add(
        Polyline(
            points=tuple(
                paper(x, y)
                for x, y in ((HOUSE_FRONT, DECK_Y + 0.30), (HOUSE_FRONT - 1.05, DECK_Y + 0.30),
                             (HOUSE_FRONT - 1.05, DECK_Y + 1.55), (HOUSE_FRONT, DECK_Y + 1.85))
            ),
            closed=True,
            layer=LAYER_OUTLINE,
        )
    )
    # 臂架搁架
    figure.add(
        Polyline(
            points=tuple(paper(x, y) for x, y in ((1.15, HOUSE_TOP), (0.55, 5.20),
                                                  (1.75, 5.20), (2.05, HOUSE_TOP))),
            closed=True,
            layer=LAYER_OUTLINE,
        )
    )
    # 支腿梁（立面可见的前后支腿）
    for x0 in (-3.30, 1.55):
        figure.add(_rect(paper, x0, x0 + 0.75, 0.55, 0.95))
        figure.add(
            Line(x1=paper(x0 + 0.37, 0.55)[0], y1=paper(x0 + 0.37, 0.55)[1],
                 x2=paper(x0 + 0.37, 0.0)[0], y2=paper(x0 + 0.37, 0.0)[1],
                 layer=LAYER_THIN)
        )
