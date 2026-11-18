"""由计算结果生成简图（设计 §11）。

只做"看懂"级示意图：不做施工图、不做三维、不追求 CAD 精度。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from liftcalc.core.result import ComputationResult
from liftcalc.drawing.primitives import (
    LAYER_CENTER,
    LAYER_DIM,
    LAYER_HIDDEN,
    LAYER_NOTE,
    LAYER_TEXT,
    LAYER_RIGGING,
    LAYER_THIN,
    Circle,
    Figure,
    Line,
    Polyline,
    Text,
)
from liftcalc.drawing.primitives import Image as DrawingImage

NOT_TO_SCALE = "示意图 · 不按比例"


def _padding(figure: Figure, ratio: float = 0.12) -> None:
    pad_x = figure.width * ratio
    pad_y = figure.height * ratio
    figure.width += 2 * pad_x
    figure.height += 2 * pad_y


def eye_figure(result: ComputationResult) -> Figure | None:
    aux: dict[str, Any] = result.aux
    if aux.get("figure") != "lifting_eye":
        return None

    plate = aux["plate"]
    hole = aux["hole"]
    extent = aux["extent"]
    x0, x1 = extent["x_mm"]
    y0, y1 = extent["y_mm"]
    d = float(hole["d_mm"])
    e = float(hole["e_mm"])

    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    figure = Figure(title="吊耳校核简图", width=width, height=height, notes=[NOT_TO_SCALE])

    figure.add(
        Polyline(points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)), closed=True),
        Circle(cx=0.0, cy=0.0, r=d / 2),
        Line(x1=-(d / 2 + 10), y1=0.0, x2=(d / 2 + 10), y2=0.0, layer=LAYER_CENTER),
        Line(x1=0.0, y1=-(d / 2 + 10), x2=0.0, y2=(d / 2 + 10), layer=LAYER_CENTER),
        Text(x=x0, y=y1 + 6, content=f"板 {plate['b_mm']:.0f}×{plate['h_mm']:.0f}×{plate['t_mm']:.0f}"),
        Text(x=x0, y=y0 - 12, content=f"孔径 d={d:.0f}   孔边距 e={e:.0f}", height=3.5),
        Text(x=x1 + 4, y=0.0, content="受力方向", layer=LAYER_DIM),
        Line(x1=x1, y1=0.0, x2=x1 + 18, y2=0.0, layer=LAYER_DIM),
        Line(x1=x1 + 18, y1=0.0, x2=x1 + 12, y2=3.0, layer=LAYER_DIM),
        Line(x1=x1 + 18, y1=0.0, x2=x1 + 12, y2=-3.0, layer=LAYER_DIM),
    )
    _padding(figure)
    return figure


def section_figure(result: ComputationResult) -> Figure | None:
    aux: dict[str, Any] = result.aux
    polygons = aux.get("outline_mm") or []
    if aux.get("figure") != "section" or not polygons:
        return None

    xs = [point[0] for polygon in polygons for point in polygon]
    ys = [point[1] for polygon in polygons for point in polygon]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)

    figure = Figure(title="截面简图", width=width, height=height, notes=[NOT_TO_SCALE])
    for polygon in polygons:
        figure.add(Polyline(points=tuple(tuple(point) for point in polygon), closed=True))

    section = aux.get("section") or {}
    cx = float(section.get("cx", 0.0))
    cy = float(section.get("cy", 0.0))
    mark = max(width, height) * 0.04
    figure.add(
        Line(x1=cx - mark, y1=cy, x2=cx + mark, y2=cy, layer=LAYER_CENTER),
        Line(x1=cx, y1=cy - mark, x2=cx, y2=cy + mark, layer=LAYER_CENTER),
        Text(x=cx + mark, y=cy + mark, content="形心", height=mark * 0.9, layer=LAYER_TEXT),
        Text(x=x0, y=y0 - 12, content=f"外包 {width:.0f} × {height:.0f}", height=3.5, layer=LAYER_NOTE),
    )
    _padding(figure)
    return figure


def capability_figure(result: ComputationResult) -> Figure | None:
    """幅度—起重量能力曲线：每个臂长一条，标出吊重水平线与临界点。"""
    cap = result.aux.get("capability") or {}
    points = cap.get("points") or []
    if not points:
        return None

    width, height, pad = 190.0, 120.0, 16.0
    max_radius = max(float(p[1]) for p in points) or 1.0
    max_load = max(float(p[2]) for p in points) or 1.0
    sx = (width - 2 * pad) / max_radius
    sy = (height - 2 * pad) / max_load

    def xy(radius: float, load: float) -> tuple[float, float]:
        return pad + radius * sx, pad + load * sy

    figure = Figure(title="幅度—起重量能力曲线", width=width, height=height, notes=["示意图 · 坐标非等比例"])

    # 坐标轴
    figure.add(
        Line(x1=pad, y1=pad, x2=width - pad, y2=pad),
        Line(x1=pad, y1=pad, x2=pad, y2=height - pad),
        Text(x=width / 2 - 10, y=pad - 17, content="幅度 (m)", height=3.6),
        Text(x=2, y=height - pad + 9, content="额定起重量 (t)", height=3.5),
    )
    for radius in range(0, int(max_radius) + 1, 5):
        x, _ = xy(radius, 0)
        figure.add(Line(x1=x, y1=pad, x2=x, y2=pad - 2, layer=LAYER_DIM),
                   Text(x=x - 2, y=pad - 7, content=str(radius), height=3.0))
    for load in range(0, int(max_load) + 1, 10):
        _, y = xy(0, load)
        figure.add(Line(x1=pad, y1=y, x2=pad + 2, y2=y, layer=LAYER_DIM),
                   Text(x=pad - 9, y=y - 1.5, content=str(load), height=3.0))

    # 各臂长曲线
    by_boom: dict[float, list[tuple[float, float]]] = {}
    for boom, radius, load in points:
        by_boom.setdefault(float(boom), []).append((float(radius), float(load)))
    for boom in sorted(by_boom):
        series = sorted(by_boom[boom])
        pts = tuple(xy(r, q) for r, q in series)
        figure.add(Polyline(points=pts, closed=False))
        figure.add(
            Text(x=pts[0][0] - 8.5, y=pts[0][1] + 1.0,
                 content=f"{boom:g}m", height=2.8, layer=LAYER_DIM)
        )

    # 吊重水平线
    required = float(cap.get("required") or 0.0)
    _, y_req = xy(0, required)
    figure.add(
        Line(x1=pad, y1=y_req, x2=width - pad, y2=y_req, layer=LAYER_DIM),
        Text(x=pad + 2, y=y_req + 2, content=f"计算荷载 {required:.2f} t", height=3.2, layer=LAYER_DIM),
    )

    # 临界点
    if cap.get("ok") and cap.get("max_radius") and cap.get("rated_load"):
        cx, cy = xy(float(cap["max_radius"]), float(cap["rated_load"]))
        figure.add(
            Circle(cx=cx, cy=cy, r=2.4, layer=LAYER_CENTER),
            Text(x=cx + 3, y=cy + 2,
                 content=f"最远 {float(cap['max_radius']):g} m / 额定 {float(cap['rated_load']):g} t",
                 height=3.2, layer=LAYER_TEXT),
        )
    return figure


def _arrow(figure: Figure, x: float, y: float, dx: float, dy: float) -> None:
    """开口箭头，方向 (dx, dy)。"""
    size = 1.7
    perp = (-dy, dx)
    figure.add(
        Line(x1=x, y1=y, x2=x + dx * size + perp[0] * size * 0.45,
             y2=y + dy * size + perp[1] * size * 0.45, layer=LAYER_DIM),
        Line(x1=x, y1=y, x2=x + dx * size - perp[0] * size * 0.45,
             y2=y + dy * size - perp[1] * size * 0.45, layer=LAYER_DIM),
    )


def _arrow(figure: Figure, x: float, y: float, dx: float, dy: float) -> None:
    """开口箭头，方向 (dx, dy)。"""
    size = 1.7
    perp = (-dy, dx)
    figure.add(
        Line(x1=x, y1=y, x2=x + dx * size + perp[0] * size * 0.45,
             y2=y + dy * size + perp[1] * size * 0.45, layer=LAYER_DIM),
        Line(x1=x, y1=y, x2=x + dx * size - perp[0] * size * 0.45,
             y2=y + dy * size - perp[1] * size * 0.45, layer=LAYER_DIM),
    )


def elevation_figure(result: ComputationResult) -> Figure | None:
    """吊装立面图（A3 竖幅，1:100）：图框、分区、标题栏、签署栏、说明。"""
    cap = result.aux.get("capability") or {}
    if not cap.get("ok"):
        return None
    detail = cap.get("left") if cap.get("mode") == "dual" else cap
    boom = detail.get("boom_len")
    angle = detail.get("boom_angle")
    radius = detail.get("max_radius")
    lift = detail.get("lift_height")
    if not any(value is not None for value in (boom, angle, radius, lift)):
        return None

    boom = float(boom or 0.0)
    angle = float(angle or 0.0)
    radius = float(radius or 0.0)
    lift = float(lift or 0.0)

    # A3 竖幅 297 x 420，按 1:100 出图
    width, height = 297.0, 420.0
    frame_l, frame_b = 25.0, 10.0
    frame_r, frame_t = 5.0, 5.0
    draw_l, draw_b = frame_l + 6, frame_b + 96
    draw_r, draw_t = 22, 24

    BODY_M = 16.0                       # 车身按 16 m 长贴图
    hinge_y = 4.7                       # 臂架铰点离地高度
    pivot = (0.0, hinge_y)
    rad = math.radians(angle)
    tip = (boom * math.cos(rad), pivot[1] + boom * math.sin(rad))

    x_min, x_max = -12.0, max(tip[0], radius) + 10.0
    y_min, y_max = -3.0, max(tip[1], lift) + 6.0
    span_x, span_y = x_max - x_min, y_max - y_min

    avail_x = width - draw_l - draw_r
    avail_y = height - draw_b - draw_t
    scale = min(avail_x / span_x, avail_y / span_y)

    def xy(x_m: float, y_m: float) -> tuple[float, float]:
        return draw_l + (x_m - x_min) * scale, draw_b + (y_m - y_min) * scale

    figure = Figure(title="吊装立面图", width=width, height=height,
                    notes=["1:100", "A3"])

    # 图框（外框 + 内框）
    figure.add(Polyline(points=((0.5, 0.5), (width - 0.5, 0.5), (width - 0.5, height - 0.5),
                                (0.5, height - 0.5)), closed=True, layer=LAYER_TEXT))
    figure.add(Polyline(points=((frame_l, frame_b), (width - frame_r, frame_b),
                                (width - frame_r, height - frame_t), (frame_l, height - frame_t)),
                        closed=True, layer=LAYER_TEXT))
    # 分区编号
    for i in range(1, 9):
        gx = frame_l + (width - frame_l - frame_r) * i / 9.0
        figure.add(Text(x=gx, y=height - frame_t - 5.0, content=str(i), height=3.0, layer=LAYER_DIM))
        if gx < width - frame_r - 185.0:
            figure.add(Text(x=gx, y=frame_b + 2.0, content=str(i), height=3.0, layer=LAYER_DIM))
        if i < 8:
            figure.add(Line(x1=gx, y1=frame_b, x2=gx, y2=frame_b + 6, layer=LAYER_TEXT),
                       Line(x1=gx, y1=height - frame_t, x2=gx, y2=height - frame_t - 6, layer=LAYER_TEXT))
    for j, letter in enumerate("ABCDEFGH", start=1):
        gy = frame_b + (height - frame_b - frame_t) * j / 9.0
        figure.add(Text(x=frame_l + 6, y=gy, content=letter, height=3.0, layer=LAYER_DIM),
                   Text(x=width - frame_r - 8, y=gy, content=letter, height=3.0, layer=LAYER_DIM))
        if j < 8:
            figure.add(Line(x1=frame_l, y1=gy, x2=frame_l + 12, y2=gy, layer=LAYER_TEXT),
                       Line(x1=width - frame_r, y1=gy, x2=width - frame_r - 12, y2=gy,
                            layer=LAYER_TEXT))

    ground = xy(x_min, 0.0)[1]
    figure.add(Line(x1=draw_l - 4, y1=ground, x2=width - draw_r + 2, y2=ground, layer=LAYER_TEXT))
    gx0 = draw_l - 4
    while gx0 < width - draw_r + 2:
        figure.add(Line(x1=gx0, y1=ground, x2=gx0 + 2.4, y2=ground - 2.4, layer=LAYER_THIN))
        gx0 += 4.0

    # 车身（原版素材）
    asset = Path(__file__).resolve().parent / "assets" / "crane_body.png"
    if asset.exists():
        body_h = BODY_M * 160.0 / 388.0
        figure.add(
            DrawingImage(
                x=xy(-BODY_M * 0.26, 0.0)[0],
                y=xy(0.0, 0.0)[1],
                w=BODY_M * scale,
                h=body_h * scale,
                path=str(asset),
            )
        )

    # 臂架铰点离地高度
    pivot = (0.0, hinge_y)
    rad = math.radians(angle)
    tip = (boom * math.cos(rad), pivot[1] + boom * math.sin(rad))

    x_min, x_max = -12.0, max(tip[0], radius) + 10.0
    y_min, y_max = -3.0, max(tip[1], lift) + 6.0
    span_x, span_y = x_max - x_min, y_max - y_min

    avail_x = width - draw_l - draw_r
    avail_y = height - draw_b - draw_t
    scale = min(avail_x / span_x, avail_y / span_y)

    def xy(x_m: float, y_m: float) -> tuple[float, float]:
        return draw_l + (x_m - x_min) * scale, draw_b + (y_m - y_min) * scale

    figure = Figure(title="吊装立面图", width=width, height=height,
                    notes=["1:100", "A3"])

    # 图框（外框 + 内框）
    figure.add(Polyline(points=((0.5, 0.5), (width - 0.5, 0.5), (width - 0.5, height - 0.5),
                                (0.5, height - 0.5)), closed=True, layer=LAYER_TEXT))
    figure.add(Polyline(points=((frame_l, frame_b), (width - frame_r, frame_b),
                                (width - frame_r, height - frame_t), (frame_l, height - frame_t)),
                        closed=True, layer=LAYER_TEXT))
    # 分区编号
    for i in range(1, 9):
        gx = frame_l + (width - frame_l - frame_r) * i / 9.0
        figure.add(Text(x=gx, y=height - frame_t - 5.0, content=str(i), height=3.0, layer=LAYER_DIM))
        if gx < width - frame_r - 185.0:
            figure.add(Text(x=gx, y=frame_b + 2.0, content=str(i), height=3.0, layer=LAYER_DIM))
        if i < 8:
            figure.add(Line(x1=gx, y1=frame_b, x2=gx, y2=frame_b + 6, layer=LAYER_TEXT),
                       Line(x1=gx, y1=height - frame_t, x2=gx, y2=height - frame_t - 6, layer=LAYER_TEXT))
    for j, letter in enumerate("ABCDEFGH", start=1):
        gy = frame_b + (height - frame_b - frame_t) * j / 9.0
        figure.add(Text(x=frame_l + 6, y=gy, content=letter, height=3.0, layer=LAYER_DIM),
                   Text(x=width - frame_r - 8, y=gy, content=letter, height=3.0, layer=LAYER_DIM))
        if j < 8:
            figure.add(Line(x1=frame_l, y1=gy, x2=frame_l + 12, y2=gy, layer=LAYER_TEXT),
                       Line(x1=width - frame_r, y1=gy, x2=width - frame_r - 12, y2=gy,
                            layer=LAYER_TEXT))

    ground = xy(x_min, 0.0)[1]
    figure.add(Line(x1=draw_l - 4, y1=ground, x2=width - draw_r + 2, y2=ground, layer=LAYER_TEXT))
    gx0 = draw_l - 4
    while gx0 < width - draw_r + 2:
        figure.add(Line(x1=gx0, y1=ground, x2=gx0 + 2.4, y2=ground - 2.4, layer=LAYER_THIN))
        gx0 += 4.0

        # 车身（原版素材贴图）
    asset = Path(__file__).resolve().parent / "assets" / "crane_body.png"
    if asset.exists():
        body_h = BODY_M * 160.0 / 388.0
        figure.add(
            DrawingImage(
                x=xy(-BODY_M * 0.26, 0.0)[0],
                y=xy(0.0, 0.0)[1],
                w=BODY_M * scale,
                h=body_h * scale,
                path=str(asset),
            )
        )

    # 臂架
    nx, ny = -math.sin(rad), math.cos(rad)
    half = 0.7
    a = (pivot[0] + nx * half, pivot[1] + ny * half)
    b = (pivot[0] - nx * half, pivot[1] - ny * half)
    c = (tip[0] - nx * half, tip[1] - ny * half)
    d = (tip[0] + nx * half, tip[1] + ny * half)
    figure.add(Polyline(points=(xy(*a), xy(*d), xy(*c), xy(*b)), closed=True, layer=LAYER_TEXT))
    for k in range(1, 7):
        f = k / 7.0
        p1 = (a[0] + (d[0] - a[0]) * f, a[1] + (d[1] - a[1]) * f)
        p2 = (b[0] + (c[0] - b[0]) * f, b[1] + (c[1] - b[1]) * f)
        figure.add(Line(x1=xy(*p1)[0], y1=xy(*p1)[1], x2=xy(*p2)[0], y2=xy(*p2)[1],
                        layer=LAYER_THIN))

    sheave = xy(*tip)
    figure.add(Circle(cx=sheave[0], cy=sheave[1], r=max(1.8, 0.8 * scale), layer=LAYER_TEXT))

    hook = xy(radius, lift)

    # 起升绳：臂端滑轮 → 吊钩组（双股）
    figure.add(Line(x1=sheave[0] - 2, y1=sheave[1], x2=xy(radius - 0.16, lift)[0],
                    y2=hook[1], layer=LAYER_TEXT),
               Line(x1=sheave[0] + 2, y1=sheave[1], x2=xy(radius + 0.16, lift)[0],
                    y2=hook[1], layer=LAYER_TEXT))

    # 吊钩组：竖长筒体（上下圆角）
    hw_cyl, h_cyl = 0.52, 2.70
    top_c = (radius, lift - hw_cyl)
    bot_c = (radius, lift - h_cyl + hw_cyl)
    cyl = []
    for k in range(13):                      # 顶盖半圆：180° -> 0°
        ang = math.radians(180 - 180 * k / 12)
        cyl.append((top_c[0] + hw_cyl * math.cos(ang), top_c[1] + hw_cyl * math.sin(ang)))
    for k in range(13):                      # 底盖半圆：0° -> -180°
        ang = math.radians(-180 * k / 12)
        cyl.append((bot_c[0] + hw_cyl * math.cos(ang), bot_c[1] + hw_cyl * math.sin(ang)))
    figure.add(Polyline(points=tuple(xy(x, y) for x, y in cyl), closed=True, layer=LAYER_TEXT))

    # 筒内滑轮
    sxp, syp = xy(radius, lift - 1.55)
    figure.add(Circle(cx=sxp, cy=syp, r=max(0.8, 0.42 * scale), layer=LAYER_TEXT))

    # 弯钩：从筒底向下的钩形（开口向左）
    hx0, hy0 = radius, lift - h_cyl
    hook_pts = [(hx0, hy0), (hx0, hy0 - 0.18)]
    r_hk = 0.42
    for k in range(19):
        ang = math.radians(90 - 250.0 * k / 18.0)
        hook_pts.append((hx0 + r_hk * math.cos(ang), hy0 - 0.18 + r_hk * math.sin(ang)))
    hook_pts.append((hx0 - r_hk * 0.75, hy0 - 0.18 + r_hk * 0.55))
    figure.add(Polyline(points=tuple(xy(x, y) for x, y in hook_pts), closed=False,
                        layer=LAYER_TEXT))

    # 吊物（挂在钩口下方）
    sling_drop = 2.2
    load_top = hy0 - 0.18 - r_hk - sling_drop
    load_bottom = max(0.4, load_top - 3.8)
    hw_l = 1.6
    c1 = xy(radius - hw_l, load_top)
    c2 = xy(radius + hw_l, load_top)
    c3 = xy(radius + hw_l, load_bottom)
    c4 = xy(radius - hw_l, load_bottom)
    figure.add(Polyline(points=(c1, c2, c3, c4), closed=True, layer=LAYER_TEXT))
    figure.add(Line(x1=c1[0], y1=c1[1], x2=c3[0], y2=c3[1], layer=LAYER_THIN),
               Line(x1=c2[0], y1=c2[1], x2=c4[0], y2=c4[1], layer=LAYER_THIN))
    hook_tip = xy(radius, hy0 - 0.18 - r_hk)
    figure.add(Line(x1=hook_tip[0], y1=hook_tip[1], x2=c1[0], y2=c1[1], layer=LAYER_RIGGING),
               Line(x1=hook_tip[0], y1=hook_tip[1], x2=c2[0], y2=c2[1], layer=LAYER_RIGGING))
    figure.add(Text(x=xy(radius, 0.0)[0] - 5, y=xy(0.0, (load_top + load_bottom) / 2)[1] - 2,
                    content="吊物", height=3.2))

    # 补充标注
    tip_y_m = pivot[1] + boom * math.sin(rad)
    tip_dim_x = xy(radius + 8.0, 0.0)[0]
    figure.add(Line(x1=sheave[0], y1=sheave[1], x2=tip_dim_x + 1.5, y2=sheave[1],
                    layer=LAYER_THIN))
    figure.add(Text(x=tip_dim_x - 3, y=sheave[1] + 2.0,
                    content=f"{tip_y_m:.2f}", height=3.0, layer=LAYER_DIM))

    sling_angle = math.degrees(math.atan2(1.6, 2.2))
    figure.add(Text(x=hook[0] + 9, y=hook[1] - 5.0,
                    content=f"{sling_angle:.0f}°", height=2.8, layer=LAYER_DIM))
    figure.add(Text(x=hook[0] - 14, y=hook[1] + 3.5,
                    content="吊钩中心", height=2.8, layer=LAYER_NOTE))
    figure.add(Text(x=xy(0.0, 0.0)[0] - 18, y=ground + 4,
                    content="旋转轴中心", height=2.8, layer=LAYER_NOTE))

    # 起重性能表（右中）
    rows = [
        ("机型", str(cap.get("model") or "")),
        ("臂长 L", f"{boom:.2f} m"),
        ("幅度 R", f"{radius:g} m"),
        ("仰角 a", f"{angle:.1f}°"),
        ("起升高度 H", f"{lift:.2f} m"),
        ("臂端高度", f"{tip_y_m:.2f} m"),
        ("该格额定", f"{float(cap.get('rated_load') or 0):g} t"),
        ("计算荷载", f"{float(cap.get('required') or 0):.2f} t"),
        ("负荷率", f"{float(cap.get('utilization') or 0):.3f}"),
    ]
    tbl_w, row_h = 74.0, 5.4
    tbl_x = width - frame_r - tbl_w - 6
    tbl_y = frame_b + 58
    tbl_h = row_h * (len(rows) + 1)
    figure.add(Polyline(points=((tbl_x, tbl_y), (tbl_x + tbl_w, tbl_y),
                                (tbl_x + tbl_w, tbl_y + tbl_h), (tbl_x, tbl_y + tbl_h)),
                        closed=True, layer=LAYER_TEXT))
    figure.add(Text(x=tbl_x + 2, y=tbl_y + tbl_h - 4.2, content="起重性能（临界格）", height=3.0))
    figure.add(Line(x1=tbl_x, y1=tbl_y + tbl_h - row_h, x2=tbl_x + tbl_w,
                    y2=tbl_y + tbl_h - row_h, layer=LAYER_TEXT))
    for i, (label, value) in enumerate(rows, start=1):
        ry = tbl_y + tbl_h - row_h * (i + 1) + 1.5
        figure.add(Text(x=tbl_x + 2, y=ry, content=label, height=2.6, layer=LAYER_NOTE),
                   Text(x=tbl_x + 32, y=ry, content=value, height=2.6, layer=LAYER_TEXT))
        if i < len(rows):
            figure.add(Line(x1=tbl_x, y1=ry - 1.5, x2=tbl_x + tbl_w, y2=ry - 1.5,
                            layer=LAYER_THIN))

    # 标题栏（右下，含签署栏）
    tb_w, tb_h = 132.0, 30.0
    tb_x, tb_y = width - frame_r - tb_w - 6, frame_b + 2
    figure.add(Polyline(points=((tb_x, tb_y), (tb_x + tb_w, tb_y), (tb_x + tb_w, tb_y + tb_h),
                                (tb_x, tb_y + tb_h)), closed=True, layer=LAYER_TEXT))
    r1, r2 = tb_y + 20.0, tb_y + 11.0
    figure.add(Line(x1=tb_x, y1=r1, x2=tb_x + tb_w, y2=r1, layer=LAYER_TEXT),
               Line(x1=tb_x, y1=r2, x2=tb_x + tb_w, y2=r2, layer=LAYER_TEXT))
    for cx in (tb_x + 58.0, tb_x + 96.0):
        figure.add(Line(x1=cx, y1=tb_y, x2=cx, y2=r1, layer=LAYER_TEXT))
    figure.add(
        Text(x=tb_x + 3, y=tb_y + 23.0,
             content=f"吊装立面图  {cap.get('model') or ''}", height=4.0),
        Text(x=tb_x + 3, y=tb_y + 13.0, content="工程名称", height=2.8, layer=LAYER_NOTE),
        Text(x=tb_x + 61, y=tb_y + 13.0, content="图号 LC-01", height=2.8),
        Text(x=tb_x + 99, y=tb_y + 13.0, content="比例 1:100", height=2.8),
        Text(x=tb_x + 3, y=tb_y + 4.0, content="设计", height=2.8, layer=LAYER_NOTE),
        Text(x=tb_x + 40, y=tb_y + 4.0, content="校核", height=2.8, layer=LAYER_NOTE),
        Text(x=tb_x + 61, y=tb_y + 4.0, content="审核", height=2.8, layer=LAYER_NOTE),
        Text(x=tb_x + 99, y=tb_y + 4.0, content="批准", height=2.8, layer=LAYER_NOTE),
    )
    return figure


def figure_for(result: ComputationResult) -> Figure | None:
    return (
        capability_figure(result)
        or elevation_figure(result)
        or eye_figure(result)
        or section_figure(result)
    )


def figures_for(result: ComputationResult) -> list[Figure]:
    """一次产出该结果支持的全部图（能力曲线 + 立面）。"""
    figures: list[Figure] = []
    for builder in (capability_figure, elevation_figure, eye_figure, section_figure):
        figure = builder(result)
        if figure is not None:
            figures.append(figure)
    return figures
