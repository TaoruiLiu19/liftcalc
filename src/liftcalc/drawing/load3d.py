"""吊物与重心三维示意（轴测投影，不按比例尺）。

只画"货"本身：长方体轮廓、四角吊点、四根吊索、吊钩、重心符号与坐标轴。
尺寸与重心的数值来自 ``result.aux["load"]``（services/calc.py 写入），
这里不重复计算任何工程量。

坐标约定与 ``lifting/load_geometry.py`` 一致：原点在形心，x 沿长度指向远离
吊车，y 沿宽度，z 竖向向上。投影是正轴测：先绕 z 转 yaw，再按 pitch 抬头。
"""

from __future__ import annotations

import math

from liftcalc.core.result import ComputationResult
from liftcalc.drawing.dim import dash_dot
from liftcalc.drawing.primitives import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    Circle,
    Figure,
    Line,
    Text,
)
from liftcalc.drawing.style import (
    LAYER_CENTER,
    LAYER_DIM,
    LAYER_HIDDEN,
    LAYER_NOTE,
    LAYER_OUTLINE,
    LAYER_RIGGING,
    LAYER_TEXT,
)

YAW_DEG = 34.0
PITCH_DEG = 21.0
PAGE_W = 210.0
PAGE_H = 150.0


def _project(x: float, y: float, z: float) -> tuple[float, float]:
    """模型坐标 (m) → 轴测平面坐标（同一尺度）。"""
    yaw = math.radians(YAW_DEG)
    pitch = math.radians(PITCH_DEG)
    x1 = x * math.cos(yaw) - y * math.sin(yaw)
    depth = x * math.sin(yaw) + y * math.cos(yaw)
    return x1, z * math.cos(pitch) + depth * math.sin(pitch)


class _Frame:
    """把轴测坐标缩放到纸面。"""

    def __init__(self, scale: float, ox: float, oy: float) -> None:
        self.s = scale
        self.ox = ox
        self.oy = oy

    def __call__(self, x: float, y: float, z: float) -> tuple[float, float]:
        u, v = _project(x, y, z)
        return self.ox + u * self.s, self.oy + v * self.s


def _arrow(figure: Figure, tail: tuple[float, float], head: tuple[float, float],
           size: float = 2.6) -> None:
    dx, dy = head[0] - tail[0], head[1] - tail[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    ux, uy = dx / length, dy / length
    for sign in (1.0, -1.0):
        figure.add(
            Line(
                x1=head[0],
                y1=head[1],
                x2=head[0] - ux * size + sign * -uy * size * 0.38,
                y2=head[1] - uy * size + sign * ux * size * 0.38,
                layer=LAYER_DIM,
            )
        )


def _centroid(figure: Figure, x: float, y: float, radius: float = 1.7) -> None:
    """形心/重心符号：圆 + 十字 + 对角象限示意阴影。"""
    figure.add(Circle(cx=x, cy=y, r=radius, layer=LAYER_CENTER),
               Line(x1=x - radius, y1=y, x2=x + radius, y2=y, layer=LAYER_CENTER),
               Line(x1=x, y1=y - radius, x2=x, y2=y + radius, layer=LAYER_CENTER))
    for sx, sy in ((1.0, 1.0), (-1.0, -1.0)):
        for step in (0.4, 0.7, 0.95):
            outer = radius * step
            figure.add(Line(x1=x + sx * outer * 0.3, y1=y + sy * outer,
                            x2=x + sx * outer, y2=y + sy * outer * 0.3,
                            layer=LAYER_CENTER))


def load_figure(result: ComputationResult) -> Figure | None:
    load = result.aux.get("load") or {}
    if not load.get("length_m"):
        return None
    length = float(load["length_m"])
    width = float(load["width_m"])
    height = float(load["height_m"])
    weight = float(load.get("weight_t") or 0.0)
    cg = load.get("cg") or {}
    cg_x, cg_y, cg_z = float(cg.get("x") or 0.0), float(cg.get("y") or 0.0), float(cg.get("z") or 0.0)
    sling_h = float(load.get("sling_height_m") or 0.0)
    slings = load.get("slings") or []
    inset = float(load.get("lug_inset_m") or 0.0)

    hx, hy, hz = length / 2.0, width / 2.0, height / 2.0
    hook_x, hook_y = load.get("hook_xy_m", (0.0, 0.0))  # 旧结果的索长按形心计算
    apex = (hook_x, hook_y, hz + sling_h)
    lugs = [
        (hx - inset, hy - inset, hz),
        (-(hx - inset), hy - inset, hz),
        (hx - inset, -(hy - inset), hz),
        (-(hx - inset), -(hy - inset), hz),
    ]

    # ---- 先算投影外包，再定比例与位置 -------------------------------------
    points = [apex, *lugs]
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                points.append((sx * hx, sy * hy, sz * hz))
    projections = [_project(*point) for point in points]
    us = [item[0] for item in projections]
    vs = [item[1] for item in projections]
    span_u = max(us) - min(us)
    span_v = max(vs) - min(vs)
    draw_w, draw_h = 138.0, 88.0
    scale = min(draw_w / max(span_u, 1e-6), draw_h / max(span_v, 1e-6))
    ox = PAGE_W / 2.0 - (min(us) + span_u / 2.0) * scale
    oy = 84.0 - (min(vs) + span_v / 2.0) * scale
    frame = _Frame(scale, ox, oy)

    figure = Figure(
        title="吊物与重心三维示意",
        width=PAGE_W,
        height=PAGE_H,
        notes=["轴测示意 · 不按比例", "坐标原点在形心"],
    )

    # ---- 坐标轴（点划线，伸到箱体外） ------------------------------------
    axis_xy = max(hx, hy) * 1.85 + 0.3
    axis_z = apex[2] + 0.9
    for vector, label, offset, align in (
        ((axis_xy, 0.0, 0.0), "x（长度，远离吊车）", (2.4, -1.2), ALIGN_LEFT),
        ((0.0, axis_xy, 0.0), f"y（宽度 B={width:.2f} m）", (0.0, 4.2), ALIGN_CENTER),
        ((0.0, 0.0, axis_z), "z（竖向）", (2.4, 1.0), ALIGN_LEFT),
    ):
        tail = frame(0.0, 0.0, 0.0)
        head = frame(*vector)
        dash_dot(figure, tail, head, layer=LAYER_DIM)
        _arrow(figure, tail, head)
        figure.add(Text(x=head[0] + offset[0], y=head[1] + offset[1], content=label,
                        height=2.8, align=align, layer=LAYER_DIM))

    # ---- 长方体 ----------------------------------------------------------
    corners = {
        (sx, sy, sz): frame(sx * hx, sy * hy, sz * hz)
        for sx in (-1, 1)
        for sy in (-1, 1)
        for sz in (-1, 1)
    }
    # yaw 在 (0°, 90°) 内时，最深（y 轴投影向上最远）的底角被箱体挡住
    hidden = (-1, -1, -1)
    edges = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            edges.append(((sx, sy, -1), (sx, sy, 1)))
    for sz in (-1, 1):
        for sy in (-1, 1):
            edges.append(((-1, sy, sz), (1, sy, sz)))
        for sx in (-1, 1):
            edges.append(((sx, -1, sz), (sx, 1, sz)))
    for start, end in edges:
        layer = LAYER_HIDDEN if hidden in (start, end) else LAYER_OUTLINE
        p1, p2 = corners[start], corners[end]
        figure.add(Line(x1=p1[0], y1=p1[1], x2=p2[0], y2=p2[1], layer=layer))

    # ---- 吊点、吊索、吊钩 ------------------------------------------------
    hook = frame(*apex)
    for lug in lugs:
        target = frame(*lug)
        figure.add(Line(x1=hook[0], y1=hook[1], x2=target[0], y2=target[1],
                        layer=LAYER_RIGGING),
                   Circle(cx=target[0], cy=target[1], r=0.85, layer=LAYER_RIGGING))
    figure.add(Circle(cx=hook[0], cy=hook[1], r=2.2, layer=LAYER_RIGGING))
    figure.add(Text(x=hook[0] - 3.2, y=hook[1] + 1.2, content="吊钩", height=2.8,
                    align=ALIGN_RIGHT, layer=LAYER_NOTE))

    # ---- 重心 ------------------------------------------------------------
    cg_point = frame(cg_x, cg_y, cg_z)
    origin = frame(0.0, 0.0, 0.0)
    if abs(cg_x) + abs(cg_y) + abs(cg_z) > 1e-9:
        figure.add(Line(x1=origin[0], y1=origin[1], x2=cg_point[0], y2=cg_point[1],
                        layer=LAYER_CENTER))
        # 三条偏心分量虚线
        for end in ((cg_x, 0.0, 0.0), (cg_x, cg_y, 0.0), (cg_x, cg_y, cg_z)):
            if abs(end[0]) + abs(end[1]) + abs(end[2]) > 1e-9:
                a, b = frame(*end), frame(cg_x, cg_y, cg_z)
                figure.add(Line(x1=a[0], y1=a[1], x2=b[0], y2=b[1], layer=LAYER_HIDDEN))
    _centroid(figure, cg_point[0], cg_point[1])
    figure.add(Text(x=cg_point[0] - 3.2, y=cg_point[1] - 4.2, content="重心 G",
                    height=2.8, align=ALIGN_RIGHT, layer=LAYER_TEXT))

    # ---- 尺寸文字 --------------------------------------------------------
    def mid(a: tuple[float, float, float], b: tuple[float, float, float],
            dx: float = 0.0, dy: float = 0.0) -> tuple[float, float]:
        pa, pb = frame(*a), frame(*b)
        return (pa[0] + pb[0]) / 2.0 + dx, (pa[1] + pb[1]) / 2.0 + dy

    x_mid = mid((-hx, -hy, -hz), (hx, -hy, -hz), 0.0, -4.2)
    figure.add(Text(x=x_mid[0], y=x_mid[1], content=f"L={length:.2f} m", height=3.0,
                    align=ALIGN_CENTER, layer=LAYER_DIM))
    z_mid = mid((-hx, hy, -hz), (-hx, hy, hz), -4.0, 0.0)
    figure.add(Text(x=z_mid[0], y=z_mid[1], content=f"H={height:.2f} m", height=3.0,
                    align=ALIGN_RIGHT, layer=LAYER_DIM))

    # ---- 标题与底部信息 --------------------------------------------------
    figure.add(Text(x=8.0, y=PAGE_H - 8.0, content="吊物与重心三维示意", height=4.6))
    figure.add(Text(x=8.0, y=PAGE_H - 13.6, content="轴测示意 · 不按比例 · 原点在形心",
                    height=2.6, layer=LAYER_NOTE))
    figure.add(Text(x=8.0, y=12.0, content=f"吊物 {length:.2f} × {width:.2f} × {height:.2f} m",
                    height=3.4))
    figure.add(Text(x=8.0, y=7.6, content=f"重量 {weight:.2f} t", height=3.4))
    figure.add(Text(x=8.0, y=3.2,
                    content=f"重心 G 相对形心（{cg_x:+.2f}, {cg_y:+.2f}, {cg_z:+.2f}）m；"
                            "x 指向远离吊车",
                    height=2.8, layer=LAYER_NOTE))
    if slings:
        forces = [float(item["force_t"])*9.80665 for item in slings]
        angles = [float(item["angle_deg"]) for item in slings]
        figure.add(Text(x=PAGE_W - 8.0, y=12.0,
                        content=f"索力 {min(forces):.2f}–{max(forces):.2f} kN",
                        height=3.2, align=ALIGN_RIGHT))
        figure.add(Text(x=PAGE_W - 8.0, y=7.6,
                        content=f"与竖直夹角 {min(angles):.1f}°–{max(angles):.1f}°",
                        height=3.2, align=ALIGN_RIGHT))
    figure.add(Text(x=PAGE_W - 8.0, y=3.2, content="轴测示意，不按比例", height=2.8,
                    align=ALIGN_RIGHT, layer=LAYER_NOTE))

    figure.meta = {
        "length": length,
        "width": width,
        "height": height,
        "cg": (cg_x, cg_y, cg_z),
        "scale": scale,
    }
    return figure
