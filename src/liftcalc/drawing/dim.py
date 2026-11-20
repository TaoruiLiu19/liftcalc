"""尺寸标注与引线（图面坐标，mm）。

尺寸线一律画在 DIM 图层（绿）；引线在 NOTE 图层（灰）。所有函数只负责把
图元追加到 Figure，不做任何比例换算——调用方先用 ``paper()`` 把模型坐标
（m）换算成图面坐标（mm）。
"""

from __future__ import annotations

import math

from liftcalc.drawing.primitives import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    Circle,
    Figure,
    Line,
    Polyline,
    Text,
    text_width,
)
from liftcalc.drawing.style import LAYER_CENTER, LAYER_DIM, LAYER_NOTE

ARROW_SIZE = 1.7
ARROW_SPREAD = 0.42      # 开口箭头半宽 / 长度
EXT_GAP = 1.2            # 尺寸界线与被测点的间隙
EXT_OVER = 1.4           # 尺寸界线超出尺寸线的长度
TEXT_GAP = 0.7           # 尺寸文字与尺寸线的间隙
DIM_TEXT_H = 2.8
LABEL_TEXT_H = 2.8


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 1.0, 0.0
    return dx / length, dy / length


def arrow(figure: Figure, x: float, y: float, ux: float, uy: float,
          *, size: float = ARROW_SIZE, layer: str = LAYER_DIM) -> None:
    """开口箭头：尖端在 (x, y)，指向 (ux, uy)。"""
    for sign in (1.0, -1.0):
        dx = -ux * size + sign * -uy * size * ARROW_SPREAD
        dy = -uy * size + sign * ux * size * ARROW_SPREAD
        figure.add(Line(x1=x, y1=y, x2=x + dx, y2=y + dy, layer=layer))


def _text_above(figure: Figure, x: float, y: float, content: str,
                *, height: float = DIM_TEXT_H, align: str = ALIGN_CENTER,
                layer: str = LAYER_DIM) -> None:
    figure.add(Text(x=x, y=y + height + TEXT_GAP, content=content, height=height,
                    align=align, layer=layer))


def _text_below(figure: Figure, x: float, y: float, content: str,
                *, height: float = DIM_TEXT_H, align: str = ALIGN_CENTER,
                layer: str = LAYER_DIM) -> None:
    figure.add(Text(x=x, y=y - TEXT_GAP, content=content, height=height,
                    align=align, layer=layer))


def h_dim(figure: Figure, x1: float, x2: float, y: float, content: str,
          *, ref_y: float | None = None, above: bool = True,
          height: float = DIM_TEXT_H, text_at: float | None = None,
          ext_ends: tuple[str, ...] = ("lo", "hi")) -> None:
    """水平尺寸：尺寸线在 y，被测两点在 (x1, y) 与 (x2, y)。

    ref_y 给出时，从被测点画竖向尺寸界线（用于被测点不在尺寸线上的情况）。
    """
    if abs(x2 - x1) < 1e-6:
        return
    lo, hi = min(x1, x2), max(x1, x2)
    sign = -1.0 if above else 1.0
    if ref_y is not None:
        start = ref_y - sign * EXT_GAP
        end = y + sign * EXT_OVER
        for tag, xx in (("lo", lo), ("hi", hi)):
            if tag in ext_ends:
                figure.add(Line(x1=xx, y1=start, x2=xx, y2=end, layer=LAYER_DIM))
    figure.add(Line(x1=lo, y1=y, x2=hi, y2=y, layer=LAYER_DIM))
    arrow(figure, lo, y, -1.0, 0.0)
    arrow(figure, hi, y, 1.0, 0.0)

    mid = (lo + hi) / 2.0 if text_at is None else text_at
    fits = text_width(content, height) + 2 * ARROW_SIZE + 1.0 < (hi - lo)
    if fits:
        if above:
            _text_above(figure, mid, y, content, height=height)
        else:
            _text_below(figure, mid, y, content, height=height)
    else:
        # 尺寸界线之间放不下：文字移到右侧，加一条引出线
        figure.add(Line(x1=hi, y1=y, x2=hi + 3.0 + text_width(content, height), y2=y,
                        layer=LAYER_DIM))
        figure.add(Text(x=hi + 3.5, y=y + height / 2 + TEXT_GAP, content=content,
                        height=height, align=ALIGN_LEFT, layer=LAYER_DIM))


def v_dim(figure: Figure, y1: float, y2: float, x: float, content: str,
          *, ref_x: float | None = None, side: str = "left",
          height: float = DIM_TEXT_H, text_at: float | None = None,
          ext_ends: tuple[str, ...] = ("lo", "hi")) -> None:
    """竖直尺寸：尺寸线在 x，被测两点在 (x, y1) 与 (x, y2)；文字竖排（旋转 90°）。"""
    if abs(y2 - y1) < 1e-6:
        return
    lo, hi = min(y1, y2), max(y1, y2)
    sign = -1.0 if side == "left" else 1.0
    if ref_x is not None:
        start = ref_x - sign * EXT_GAP
        end = x + sign * EXT_OVER
        for tag, yy in (("lo", lo), ("hi", hi)):
            if tag in ext_ends:
                figure.add(Line(x1=start, y1=yy, x2=end, y2=yy, layer=LAYER_DIM))
    figure.add(Line(x1=x, y1=lo, x2=x, y2=hi, layer=LAYER_DIM))
    arrow(figure, x, lo, 0.0, -1.0)
    arrow(figure, x, hi, 0.0, 1.0)

    mid = (lo + hi) / 2.0 if text_at is None else text_at
    span_room = hi - lo - 2 * ARROW_SIZE - 1.0
    # 放不下"名称=数值"时退化为只写数值（尺寸链惯例），仍竖排
    short = content.split("=")[-1] if "=" in content else content
    label = content
    if text_width(content, height) >= span_room and text_width(short, height) < span_room:
        label = short
    fits = text_width(label, height) + 2 * ARROW_SIZE + 1.0 < (hi - lo)
    if fits:
        figure.add(
            Text(
                x=x - TEXT_GAP - height if side == "left" else x + TEXT_GAP,
                y=mid,
                content=label,
                height=height,
                align=ALIGN_CENTER,
                angle=90.0,
                layer=LAYER_DIM,
            )
        )
    elif (hi - lo) >= height + 1.2:
        # 竖直放不下但带宽够：文字横排放在尺寸线内侧，与尺寸带同高
        anchor_x = x + TEXT_GAP + 1.0 if side == "left" else x - TEXT_GAP - 1.0
        figure.add(
            Text(x=anchor_x, y=(lo + hi) / 2.0 + height / 2.0, content=label,
                 height=height, align=ALIGN_LEFT if side == "left" else ALIGN_RIGHT,
                 layer=LAYER_DIM)
        )
    else:
        # 带宽也不够：文字移到上限之外，仍按竖排，读法与相邻尺寸一致
        offset = text_width(content, height) / 2.0 + 1.5
        figure.add(
            Text(
                x=x - TEXT_GAP - height if side == "left" else x + TEXT_GAP,
                y=hi + offset,
                content=content,
                height=height,
                align=ALIGN_CENTER,
                angle=90.0,
                layer=LAYER_DIM,
            )
        )


def aligned_dim(figure: Figure, p1: tuple[float, float], p2: tuple[float, float],
                offset: float, content: str, *, height: float = DIM_TEXT_H) -> None:
    """对齐尺寸：尺寸线平行于 p1→p2，向左侧偏移 offset（offset 取正）。"""
    (x1, y1), (x2, y2) = p1, p2
    ux, uy = _unit(x2 - x1, y2 - y1)
    if ux == 0.0 and uy == 0.0:
        return
    nx, ny = -uy, ux                      # 左法向
    if offset < 0:
        nx, ny, offset = -nx, -ny, -offset

    a1 = (x1 + nx * offset, y1 + ny * offset)
    a2 = (x2 + nx * offset, y2 + ny * offset)

    for px, py in ((x1, y1), (x2, y2)):
        figure.add(
            Line(
                x1=px + nx * EXT_GAP,
                y1=py + ny * EXT_GAP,
                x2=px + nx * (offset + EXT_OVER),
                y2=py + ny * (offset + EXT_OVER),
                layer=LAYER_DIM,
            )
        )

    figure.add(Line(x1=a1[0], y1=a1[1], x2=a2[0], y2=a2[1], layer=LAYER_DIM))
    arrow(figure, a1[0], a1[1], -ux, -uy)
    arrow(figure, a2[0], a2[1], ux, uy)

    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    if 90.0 < angle % 360.0 <= 270.0:     # 让文字始终朝上可读
        angle -= 180.0
    mid = ((a1[0] + a2[0]) / 2.0, (a1[1] + a2[1]) / 2.0)
    figure.add(
        Text(
            x=mid[0] + nx * (TEXT_GAP + height),
            y=mid[1] + ny * (TEXT_GAP + height),
            content=content,
            height=height,
            align=ALIGN_CENTER,
            angle=angle,
            layer=LAYER_DIM,
        )
    )


def angle_dim(figure: Figure, cx: float, cy: float, radius: float,
              start_deg: float, end_deg: float, content: str,
              *, height: float = DIM_TEXT_H, text_radius: float | None = None,
              text_at_deg: float | None = None,
              text_xy: tuple[float, float] | None = None,
              text_align: str = ALIGN_RIGHT) -> None:
    """角度尺寸：以 (cx, cy) 为心、radius 为半径画弧，两端带箭头，文字在弧外。"""
    span = end_deg - start_deg
    steps = max(8, int(abs(span) / 6) + 8)
    points = []
    for index in range(steps + 1):
        ang = math.radians(start_deg + span * index / steps)
        points.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    figure.add(Polyline(points=tuple(points), closed=False, layer=LAYER_DIM))

    # 两端箭头沿切向，指向弧外侧
    for ang_deg, direction in ((start_deg, -1.0), (end_deg, 1.0)):
        ang = math.radians(ang_deg)
        tx, ty = -math.sin(ang), math.cos(ang)
        px, py = cx + radius * math.cos(ang), cy + radius * math.sin(ang)
        arrow(figure, px, py, tx * direction, ty * direction)

    if text_xy is not None:
        figure.add(Text(x=text_xy[0], y=text_xy[1], content=content, height=height,
                        align=text_align, layer=LAYER_DIM))
        return

    mid_deg = start_deg + span / 2.0 if text_at_deg is None else text_at_deg
    mid = math.radians(mid_deg)
    r_text = text_radius if text_radius is not None else radius + height + 2.0
    figure.add(
        Text(
            x=cx + r_text * math.cos(mid),
            y=cy + r_text * math.sin(mid) + height / 2,
            content=content,
            height=height,
            align=ALIGN_CENTER,
            layer=LAYER_DIM,
        )
    )


def leader(figure: Figure, target: tuple[float, float], text_xy: tuple[float, float],
           content: str, *, align: str = ALIGN_LEFT, height: float = LABEL_TEXT_H,
           dot: bool = True, knee: float | None = None) -> None:
    """引线标注：文字锚点 text_xy（ty 为字框顶边），引线从文字侧边指向 target。

    knee 给出时，引线先在 knee 的 x 处折一次（工程图两段引线）。
    """
    tx, ty = text_xy
    width = text_width(content, height)
    if align == ALIGN_CENTER:
        x0 = tx - width / 2
    elif align == ALIGN_RIGHT:
        x0 = tx - width
    else:
        x0 = tx
    figure.add(Text(x=tx, y=ty, content=content, height=height,
                    align=align, layer=LAYER_NOTE))

    middle = ty - height / 2
    if target[0] > x0 + width:
        attach = (x0 + width + 1.5, middle)
    elif target[0] < x0:
        attach = (x0 - 1.5, middle)
    else:
        attach = (target[0], middle)

    if knee is None:
        figure.add(Line(x1=attach[0], y1=attach[1], x2=target[0], y2=target[1],
                        layer=LAYER_NOTE))
    else:
        figure.add(Line(x1=attach[0], y1=attach[1], x2=knee, y2=attach[1],
                        layer=LAYER_NOTE),
                   Line(x1=knee, y1=attach[1], x2=target[0], y2=target[1],
                        layer=LAYER_NOTE))
    if dot:
        figure.add(Circle(cx=target[0], cy=target[1], r=0.45, layer=LAYER_NOTE))


def dashed(figure: Figure, p1: tuple[float, float], p2: tuple[float, float],
           *, dash: float = 2.4, gap: float = 1.6, layer: str = LAYER_NOTE) -> None:
    """虚线（无原生虚线图元，按段拆分）。"""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    ux, uy = dx / length, dy / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash, length)
        figure.add(Line(x1=x1 + ux * pos, y1=y1 + uy * pos,
                        x2=x1 + ux * end, y2=y1 + uy * end, layer=layer))
        pos = end + gap


def dash_dot(figure: Figure, p1: tuple[float, float], p2: tuple[float, float],
             *, layer: str = LAYER_CENTER) -> None:
    """点划线（中心线）。"""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    ux, uy = dx / length, dy / length
    pos = 0.0
    first = True
    while pos < length:
        seg = min(12.0 if first else 3.0, length - pos)
        figure.add(Line(x1=x1 + ux * pos, y1=y1 + uy * pos,
                        x2=x1 + ux * (pos + seg), y2=y1 + uy * (pos + seg), layer=layer))
        pos += seg
        if pos >= length:
            break
        dot = min(0.6, length - pos)
        figure.add(Line(x1=x1 + ux * pos, y1=y1 + uy * pos,
                        x2=x1 + ux * (pos + dot), y2=y1 + uy * (pos + dot), layer=layer))
        pos += dot + 1.4
        first = False
