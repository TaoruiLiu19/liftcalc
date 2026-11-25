"""由计算结果生成图（设计 §11）。

三类图：
    capability_figure  幅度—起重量能力曲线
    elevation_figure   吊装立面图（A3 竖幅，图框/标题栏/性能表/尺寸链/引线标注）
    eye_figure / section_figure  吊耳、截面简图

立面图约定：模型坐标 x 指向吊物方向（m），y 向上，原点在回转中心地面。
图面坐标 x 向左为正（吊物在图左、车身在图右，与原版图纸一致）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from liftcalc.core.result import ComputationResult
from liftcalc.drawing import dim as D
from liftcalc.drawing import sheet as S
from liftcalc.drawing.annotation import clear_annotation_lines, nearby_labels, place_label
from liftcalc.drawing.body import (
    BODY_MODEL_FRONT,
    CAB_LEFT_EDGE,
    CAB_RIGHT_EDGE,
    CAB_ROOF_HEIGHT,
    DECK_HEIGHT,
    MAIN_WINCH,
    MAIN_WINCH_RADIUS,
    draw_truck,
    drawing_axles,
)
from liftcalc.drawing.primitives import (
    ALIGN_CENTER,
    ALIGN_RIGHT,
    Circle,
    Figure,
    Line,
    Polyline,
    Text,
)
from liftcalc.drawing.primitives import Image as DrawingImage
from liftcalc.drawing.style import (
    LAYER_CENTER,
    LAYER_DIM,
    LAYER_NOTE,
    LAYER_OUTLINE,
    LAYER_RIGGING,
    LAYER_TEXT,
    LAYER_THIN,
    SCALE_LADDER,
)

NOT_TO_SCALE = "示意图 · 不按比例"

# ---- 立面图几何常数（单位 m，可按机型调整） -------------------------------
# 臂架铰点离地高：取 4.7 m 使 臂端高度 = 4.7 + L·sin a 与性能表的数据自洽
# （QY70K-1 临界格 4.7+25.98·sin67.6° = 28.72 m，额定起升高度 24.43 m，
#  两者相差 4.3 m，正好容纳吊钩组与最小绳长）。
HINGE_H = 4.7
BOOM_HALF_FOOT = 0.80     # 臂根半宽
BOOM_HALF_TIP = 0.58      # 臂端半宽
BOOM_JOINTS = (0.30, 0.52, 0.72, 0.88)   # 伸缩节搭接位置（占臂长比例）
BOOM_HEAD_REACH = 0.65   # 立面示意：臂架轴线端点到吊钩铅垂线的水平偏距
BODY_FRONT = BODY_MODEL_FRONT   # 车头前沿距回转中心（车身标定见 drawing/body.py）
BLOCK_H = 2.40            # 吊钩组筒体高
BLOCK_GAP = 0.40          # 筒体底到吊钩中心
LIFT_SHEAVE_RADIUS = .28
GUIDE_SHEAVE_RADIUS = .22
SLING_RATIO = 0.55        # 吊索水平投影 → 竖直高度
ROPE_MIN = 1.6            # 无起升高度数据时，吊钩组顶距臂端的最小绳长
DEFAULT_LOAD_W = 3.2
DEFAULT_LOAD_H = 3.8

# ---- 尺寸链位置（相对吊物远边的图面偏移，mm） -----------------------------
CHAIN_HZ = -20.5           # 地面→臂端
CHAIN_H = -13.5            # 地面→吊钩中心
CHAIN_H123 = -7.0          # h1/h2/h3



def _fit_paper(figure: Figure, ratio: float = 0.10) -> Figure:
    """把图元整体平移进第一象限并留边，同时设置图幅。

    吊耳/截面的图元常常以形心为原点（含负坐标），不平移就会被画到纸外。
    """
    x0, y0, x1, y1 = figure.bbox()
    span = max(x1 - x0, y1 - y0, 1.0)
    pad = span * ratio
    dx, dy = pad - x0, pad - y0
    figure.primitives = _shift(figure.primitives, dx, dy)
    figure.width = (x1 - x0) + 2 * pad
    figure.height = (y1 - y0) + 2 * pad
    return figure


# ===========================================================================
# 吊耳 / 截面简图
# ===========================================================================
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
        Text(x=x0, y=y1 + 3.5, content=f"板 {plate['b_mm']:.0f}×{plate['h_mm']:.0f}×{plate['t_mm']:.0f} mm"),
        Text(x=x0, y=y0 - 3.5, content=f"孔径 d={d:.0f} mm   孔边距 e={e:.0f} mm", height=3.5),
        Text(x=x1 + 4, y=1.75, content="受力方向", layer=LAYER_DIM),
        Line(x1=x1, y1=0.0, x2=x1 + 18, y2=0.0, layer=LAYER_DIM),
        Line(x1=x1 + 18, y1=0.0, x2=x1 + 12, y2=3.0, layer=LAYER_DIM),
        Line(x1=x1 + 18, y1=0.0, x2=x1 + 12, y2=-3.0, layer=LAYER_DIM),
    )
    return _fit_paper(figure)


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
        Text(x=cx + mark, y=cy + mark + 3.5, content="形心", height=3.5, layer=LAYER_TEXT),
        Text(x=x0, y=y0 - 3.5, content=f"外包 {width:.0f} × {height:.0f} mm", height=3.5,
             layer=LAYER_NOTE),
    )
    return _fit_paper(figure)


# ===========================================================================
# 能力曲线
# ===========================================================================
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

    figure = Figure(title="幅度—起重量能力曲线", width=width, height=height,
                    notes=["示意图 · 坐标非等比例"])

    figure.add(
        Line(x1=pad, y1=pad, x2=width - pad, y2=pad),
        Line(x1=pad, y1=pad, x2=pad, y2=height - pad),
        Text(x=width / 2, y=pad - 11.0, content="幅度 (m)", height=3.6, align=ALIGN_CENTER),
        Text(x=2, y=height - pad + 9, content="额定起重量 (t)", height=3.5),
    )
    for radius in range(0, int(max_radius) + 1, 5):
        x, _ = xy(radius, 0)
        figure.add(Line(x1=x, y1=pad, x2=x, y2=pad - 2, layer=LAYER_DIM),
                   Text(x=x, y=pad - 7.0, content=str(radius), height=3.0,
                        align=ALIGN_CENTER))
    for load in range(0, int(max_load) + 1, 10):
        _, y = xy(0, load)
        figure.add(Line(x1=pad, y1=y, x2=pad + 2, y2=y, layer=LAYER_DIM),
                   Text(x=pad - 3, y=y + 1.5, content=str(load), height=3.0,
                        align=ALIGN_RIGHT))

    by_boom: dict[float, list[tuple[float, float]]] = {}
    for boom, radius, load in points:
        by_boom.setdefault(float(boom), []).append((float(radius), float(load)))
    for boom in sorted(by_boom):
        series = sorted(by_boom[boom])
        pts = tuple(xy(r, q) for r, q in series)
        figure.add(Polyline(points=pts, closed=False))
        figure.add(
            Text(x=pts[0][0] - 1.5, y=pts[0][1] + 1.0,
                 content=f"{boom:g} m", height=2.8, align=ALIGN_RIGHT, layer=LAYER_DIM)
        )

    required = float(cap.get("required") or 0.0)
    _, y_req = xy(0, required)
    figure.add(
        Line(x1=pad, y1=y_req, x2=width - pad, y2=y_req, layer=LAYER_DIM),
        Text(x=pad + 2, y=y_req + 2.0, content=f"计算总起重量 {required:.2f} t", height=3.2,
             layer=LAYER_DIM),
    )

    if cap.get("ok") and cap.get("max_radius") and cap.get("rated_load"):
        cx, cy = xy(float(cap["max_radius"]), float(cap["rated_load"]))
        figure.add(
            Circle(cx=cx, cy=cy, r=2.4, layer=LAYER_CENTER),
            Text(x=cx + 3, y=cy + 3.0,
                 content=f"最远 {float(cap['max_radius']):g} m / 额定 {float(cap['rated_load']):g} t",
                 height=3.2),
        )
    return figure


# ===========================================================================
# 吊装立面图
# ===========================================================================
@dataclass(frozen=True)
class ElevationModel:
    """立面图的几何量（m）。x 指向吊物方向，y 向上，原点 = 回转中心地面。"""

    boom_len: float
    boom_angle: float          # 度
    radius: float              # 回转中心 → 吊钩中心水平距
    hook_h: float              # 吊钩中心高
    load_w: float              # 吊物长（立面内）
    load_h: float              # 吊物高
    load_d: float = 0.0        # 吊物宽（垂直立面）
    sling_h: float = 0.0       # 吊索竖直高度：吊钩中心 → 吊点平面
    cg_x: float = 0.0          # 重心相对形心（m）
    cg_y: float = 0.0
    cg_z: float = 0.0
    lug_inset: float = 0.0
    hook_offset_x: float = 0.0

    @property
    def rad(self) -> float:
        return math.radians(self.boom_angle)

    @property
    def hinge(self) -> tuple[float, float]:
        return self.tip[0] - self.boom_len * math.cos(self.rad), HINGE_H

    @property
    def hook_seat(self) -> tuple[float, float]:
        return self.radius, self.hook_h

    @property
    def tip(self) -> tuple[float, float]:
        return self.radius - BOOM_HEAD_REACH, self.tip_height

    @property
    def head_sheave(self) -> tuple[float, float]:
        return self.radius, self.tip_height

    @property
    def guide_sheave(self) -> tuple[float, float]:
        return self.tip[0] - .25, self.tip_height + .47

    @property
    def block_top(self) -> float:
        return self.hook_h + BLOCK_GAP + BLOCK_H

    @property
    def block_sheave(self) -> tuple[float, float]:
        return self.radius, self.block_top - .66

    @property
    def sling_drop(self) -> float:
        return self.sling_h if self.sling_h > 0 else SLING_RATIO * max(self.load_w, 1.0)

    @property
    def load_top(self) -> float:
        return self.hook_h - self.sling_drop

    @property
    def load_bottom(self) -> float:
        return self.load_top - self.load_h

    @property
    def tip_height(self) -> float:
        return HINGE_H + self.boom_len * math.sin(self.rad)

    @property
    def lug_x(self) -> float:
        return self.load_w / 2.0 - self.lug_inset

    @property
    def load_center(self) -> tuple[float, float]:
        return self.radius - self.hook_offset_x, (self.load_top + self.load_bottom) / 2.0

    @property
    def cg(self) -> tuple[float, float]:
        """重心在立面图上的位置（m）。"""
        cx, cy = self.load_center
        return cx + self.cg_x, cy + self.cg_z




def _capability_detail(cap: dict[str, Any]) -> dict[str, Any] | None:
    if not cap.get("ok"):
        return None
    detail = cap.get("left") if cap.get("mode") == "dual" else cap
    if not detail or detail.get("boom_len") is None or detail.get("max_radius") is None:
        return None
    return detail


def _elevation_model(cap: dict[str, Any], detail: dict[str, Any],
                     load: dict[str, Any]) -> tuple[ElevationModel, list[str]]:
    """由性能表临界工况 + 吊物真实尺寸，推出立面图几何。

    吊钩高度 = 吊物底净空 + 吊物高 + 吊索竖直高度（由吊物几何推算），
    而不是取性能表的额定起升高度——后者是能力上限，不是本次吊装姿态。
    """
    notes: list[str] = []
    boom_len = float(detail["boom_len"])
    radius = float(detail["max_radius"])
    angle = detail.get("boom_angle")
    if angle is None:
        ratio = min(max(radius / boom_len, 0.0), 1.0)
        angle = math.degrees(math.acos(ratio))
        notes.append("本机型性能表无仰角列，图示仰角按臂长与幅度反算")
    angle = float(angle)

    cg = load.get("cg") or {}
    load_w = float(load.get("length_m") or DEFAULT_LOAD_W)
    load_d = float(load.get("width_m") or load_w)
    load_h = float(load.get("height_m") or DEFAULT_LOAD_H)
    clearance = float(load.get("clearance_m") if load.get("clearance_m") is not None else 1.0)
    sling = float(load.get("sling_height_m") or SLING_RATIO * max(load_w, 1.0))
    required_hook_h = float(
        load.get("hook_height_m")
        or (clearance + load_h + sling)
    )
    hook_h = required_hook_h

    tip_y = HINGE_H + boom_len * math.sin(math.radians(angle))
    limit = tip_y - (BLOCK_GAP + BLOCK_H + ROPE_MIN)
    if hook_h > limit:
        hook_h = max(limit, 0.4)
        notes.append(
            f"所需吊钩中心离地高度 {required_hook_h:.2f} m 超出示意几何范围，吊钩已按图示臂端极限绘制"
        )

    rated = detail.get("lift_height")
    if rated is not None and required_hook_h > float(rated) + 1e-6:
        notes.append(
            f"该工况的表列起升高度 {float(rated):.2f} m 低于所需吊钩中心离地高度 {required_hook_h:.2f} m，"
            "需另行校核该工况起升高度"
        )

    model = ElevationModel(
        boom_len=boom_len,
        boom_angle=angle,
        radius=radius,
        hook_h=hook_h,
        load_w=load_w,
        load_h=load_h,
        load_d=load_d,
        sling_h=sling,
        cg_x=float(cg.get("x") or 0.0),
        cg_y=float(cg.get("y") or 0.0),
        cg_z=float(cg.get("z") or 0.0),
        lug_inset=float(load.get("lug_inset_m") or 0.0),
        hook_offset_x=load.get("hook_xy_m", (0.0, 0.0))[0],
    )
    return model, notes


class _Paper:
    """模型坐标 (m) → 图面坐标 (mm)；x 取反（吊物在图左）。"""

    def __init__(self, scale: float, ox: float, oy: float) -> None:
        self.s = scale
        self.ox = ox
        self.oy = oy

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        return self.ox - x * self.s, self.oy + y * self.s

    def dx(self, metres: float) -> float:
        return metres * self.s

    def dy(self, metres: float) -> float:
        return metres * self.s




def _boom_half(fraction: float) -> float:
    section = sum(fraction >= joint for joint in BOOM_JOINTS)
    return BOOM_HALF_FOOT - section * 0.115


def _draw_boom(figure: Figure, paper: _Paper, model: ElevationModel) -> None:
    hx, hy = model.hinge
    cosine, sine = math.cos(model.rad), math.sin(model.rad)

    def along(distance, normal):
        return paper(hx + cosine * distance - sine * normal,
                     hy + sine * distance + cosine * normal)

    def profile(vertices, layer=LAYER_OUTLINE):
        figure.add(Polyline(tuple(along(*vertex) for vertex in vertices), True, layer))

    def pin(center, radius):
        figure.add(Circle(*center, paper.s * radius, LAYER_OUTLINE))

    stops = (0.0, *BOOM_JOINTS, 1.0)
    for start, finish in zip(stops, stops[1:]):
        near, far = model.boom_len * start, model.boom_len * finish
        half = _boom_half(start)
        collar = min(.32, (far - near) * .15)
        heel = .40 if start == 0 else 0.0
        profile(((near - heel, half * .55), (near + heel, half),
                 (far - collar, half), (far - collar, -half),
                 (near + heel, -half), (near - heel, -half * .55)))
        profile(((far - collar, half), (far - collar + .07, half + .055),
                 (far, half + .055), (far, -half - .055),
                 (far - collar + .07, -half - .055), (far - collar, -half)))
        figure.add(Line(*along(near + heel + .10, half * .64),
                        *along(far - collar, half * .64), LAYER_THIN))

    pin(along(0, 0), .26)
    pin(along(0, 0), .11)
    tx, ty = model.tip
    # 参照徐工 QY70K-I 操作手册图 2-1 和图 5-18，分画臂头导向轮和定滑轮。
    head_outline = ((-.55, -.57), (-.58, .51), (-.32, .80), (.14, .75),
                    (.95, .24), (1.03, -.08), (.91, -.52), (.61, -.70),
                    (.25, -.73), (.12, -.57))
    figure.add(Polyline(tuple(paper(tx + x, ty + y) for x, y in head_outline), True, LAYER_OUTLINE))
    for center, radius in ((model.guide_sheave, GUIDE_SHEAVE_RADIUS), (model.head_sheave, LIFT_SHEAVE_RADIUS)):
        pin(paper(*center), radius)
        pin(paper(*center), .085)


def _draw_luffing_cylinder(figure: Figure, paper: _Paper, model: ElevationModel,
                          *, annotate: bool = True) -> None:
    hx, hy = model.hinge
    cosine, sine = math.cos(model.rad), math.sin(model.rad)

    def on_boom(distance: float, normal: float) -> tuple[float, float]:
        return hx + cosine * distance - sine * normal, hy + sine * distance + cosine * normal

    distance = min(6.2, model.boom_len * .27)
    upper = on_boom(distance, -1.04)
    base = (1.63, DECK_HEIGHT)
    length = math.dist(base, upper)
    ux, uy = (upper[0] - base[0]) / length, (upper[1] - base[1]) / length

    def cylinder(s: float, offset: float) -> tuple[float, float]:
        return paper(base[0] + ux*s - uy*offset, base[1] + uy*s + ux*offset)

    # 下铰点在操纵室后方，筒体从屋顶或侧缘露出。
    roof_exit = (CAB_ROOF_HEIGHT - base[1]) / uy if uy > 0 else math.inf
    cab_edge = CAB_LEFT_EDGE if ux >= 0 else CAB_RIGHT_EDGE
    side_exit = (cab_edge - base[0]) / ux if abs(ux) > 1e-9 else math.inf
    visible = min(roof_exit, side_exit)
    end = length - .14
    if visible < end:
        collar = visible + .57 * (end - visible)
        figure.add(
            Polyline((cylinder(visible, -.19), cylinder(collar, -.19), cylinder(collar, .19),
                      cylinder(visible, .19)), False, LAYER_OUTLINE),
            Polyline((cylinder(collar, -.10), cylinder(end, -.10), cylinder(end, .10),
                      cylinder(collar, .10)), False, LAYER_OUTLINE),
        )
        if annotate:
            target = cylinder((visible + collar) / 2, .19)
            D.leader(figure, target, (target[0] - 6, target[1] + 5), "变幅油缸", align=ALIGN_RIGHT, height=2.6)

    lug = (on_boom(max(0, distance - .34), -BOOM_HALF_FOOT),
           on_boom(distance + .34, -BOOM_HALF_FOOT), upper)
    figure.add(Polyline(tuple(paper(*p) for p in lug), True, LAYER_OUTLINE),
               Circle(*paper(*upper), .15 * paper.s, LAYER_OUTLINE),
               Circle(*paper(*upper), .055 * paper.s, LAYER_THIN))


def _draw_hook_block(figure: Figure, paper: _Paper, model: ElevationModel) -> None:
    x = model.radius
    bottom = model.hook_h + BLOCK_GAP
    top = bottom + BLOCK_H
    outline = ((-.22, bottom), (-.44, bottom + .42), (-.47, top - .17), (-.35, top),
               (.35, top), (.47, top - .17), (.44, bottom + .42), (.22, bottom))
    center = paper(*model.block_sheave)
    figure.add(Polyline(tuple(paper(x + dx, y) for dx, y in outline), True, LAYER_OUTLINE),
               Circle(*center, LIFT_SHEAVE_RADIUS * paper.s, LAYER_OUTLINE),
               Circle(*center, .08 * paper.s, LAYER_THIN),
               Line(*paper(x - .29, bottom + .16), *paper(x + .29, bottom + .16), LAYER_THIN))

    seat_x, seat_y = model.hook_seat
    hook = ((-.08, BLOCK_GAP), (-.08, .33), (-.20, .24), (-.25, .11),
            (-.22, -.025), (-.13, -.10), (.01, -.13), (.15, -.09),
            (.22, .015), (.23, .16), (.19, .23), (.13, .095),
            (.07, .025), (0, 0), (-.08, .035), (-.12, .11),
            (-.09, .17), (.035, .26), (.07, .33), (.07, BLOCK_GAP))
    figure.add(Polyline(tuple(paper(seat_x + dx, seat_y + dy) for dx, dy in hook),
                        True, LAYER_OUTLINE))


def _rope_behind_boom(model: ElevationModel, start: tuple[float, float],
                      end: tuple[float, float]) -> list[tuple[float, float]]:
    """求入绳段在侧视投影中被各节臂遮住的参数范围。"""
    hx, hy = model.hinge
    c, s = math.cos(model.rad), math.sin(model.rad)
    x, y = start[0] - hx, start[1] - hy
    dx, dy = end[0] - start[0], end[1] - start[1]
    along, normal = x*c + y*s, -x*s + y*c
    du, dv = dx*c + dy*s, -dx*s + dy*c

    def inside(value: float, delta: float, low: float, high: float) -> tuple[float, float]:
        if abs(delta) < 1e-9:
            return (0, 1) if low <= value <= high else (1, 0)
        a, b = (low - value) / delta, (high - value) / delta
        return min(a, b), max(a, b)

    ranges = []
    stops = (0.0, *BOOM_JOINTS, 1.0)
    for near, far in zip(stops, stops[1:]):
        half = _boom_half(near)
        u0, u1 = inside(along, du, near * model.boom_len, far * model.boom_len)
        v0, v1 = inside(normal, dv, -half, half)
        left, right = max(u0, v0, 0), min(u1, v1, 1)
        if left < right:
            ranges.append((left, right))
    return ranges


def _draw_rope(figure: Figure, paper: _Paper, model: ElevationModel, *, annotate: bool = True) -> None:
    """沿切线和轮缘绘制起升绳的侧视投影。"""
    guide, head, block = model.guide_sheave, model.head_sheave, model.block_sheave
    r = LIFT_SHEAVE_RADIUS

    def tangent(first: tuple[float, float], r1: float, second: tuple[float, float], r2: float) -> float:
        angle = math.atan2(second[1] - first[1], second[0] - first[0])
        return angle + math.acos((r1 - r2) / math.dist(first, second))

    def rim(center: tuple[float, float], radius: float, angle: float) -> tuple[float, float]:
        return center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)

    def wrap(center: tuple[float, float], radius: float, start: float, end: float):
        return tuple(paper(*rim(center, radius, start + (end - start) * i / 24)) for i in range(25))

    incoming = tangent(MAIN_WINCH, MAIN_WINCH_RADIUS, guide, GUIDE_SHEAVE_RADIUS)
    outgoing = tangent(guide, GUIDE_SHEAVE_RADIUS, head, r)
    feed = rim(MAIN_WINCH, MAIN_WINCH_RADIUS, incoming)
    contact = rim(guide, GUIDE_SHEAVE_RADIUS, incoming)

    def lead_at(t: float) -> tuple[float, float]:
        return paper(feed[0] + t * (contact[0] - feed[0]), feed[1] + t * (contact[1] - feed[1]))

    # 引线接点同时划分长斜线，避免整段外包框误挤右上性能表。
    marker = .26
    hidden = _rope_behind_boom(model, feed, contact)
    cuts = sorted({0.0, marker, 1.0, *(t for span in hidden for t in span)})
    for first, last in zip(cuts, cuts[1:]):
        a, b = lead_at(first), lead_at(last)
        mid = (first + last) / 2
        if any(lo < mid < hi for lo, hi in hidden):
            D.dashed(figure, a, b, dash=1.7, gap=1.2, layer=LAYER_RIGGING)
        else:
            figure.add(Line(*a, *b, LAYER_RIGGING))

    anchor = (head[0] - r, head[1] - .61)
    guide_arc = wrap(guide, GUIDE_SHEAVE_RADIUS, incoming, outgoing)
    head_arc = wrap(head, r, outgoing, 0)
    block_arc = wrap(block, r, 0, -math.pi)
    figure.add(
        Polyline(guide_arc, False, LAYER_RIGGING),
        Line(*guide_arc[-1], *head_arc[0], LAYER_RIGGING),
        Polyline(head_arc, False, LAYER_RIGGING),
        Line(*head_arc[-1], *block_arc[0], LAYER_RIGGING),
        Polyline(block_arc, False, LAYER_RIGGING),
        Line(*block_arc[-1], *paper(*anchor), LAYER_RIGGING),
        Line(*paper(anchor[0] - .09, anchor[1]), *paper(anchor[0] + .09, anchor[1]), LAYER_OUTLINE),
    )

    if annotate:
        target = lead_at(marker)
        D.leader(figure, target, (target[0] + 8, target[1] + 6), "起升钢丝绳", height=2.6, dot=False)


def centroid_symbol(figure: Figure, paper: _Paper, x: float, y: float,
                    radius: float = 2.2) -> None:
    """形心/重心符号：圆 + 两个对角的四分之一阴影（用短斜线示意阴影）。"""
    cx, cy = paper(x, y)
    figure.add(Circle(cx=cx, cy=cy, r=radius, layer=LAYER_CENTER))
    figure.add(Line(x1=cx - radius, y1=cy, x2=cx + radius, y2=cy, layer=LAYER_CENTER),
               Line(x1=cx, y1=cy - radius, x2=cx, y2=cy + radius, layer=LAYER_CENTER))
    # 右上、左下两个象限的示意阴影（工程图惯例：对角象限填充）
    for sx, sy in ((1.0, 1.0), (-1.0, -1.0)):
        for step in (0.35, 0.62, 0.86):
            outer = radius * step
            figure.add(Line(x1=cx + sx * outer * 0.30, y1=cy + sy * outer,
                            x2=cx + sx * outer, y2=cy + sy * outer * 0.30,
                            layer=LAYER_CENTER))


def _draw_load(figure: Figure, paper: _Paper, model: ElevationModel) -> None:
    x, _ = model.load_center
    half = model.load_w / 2.0
    top, bottom = model.load_top, model.load_bottom

    box = (paper(x - half, top), paper(x + half, top),
           paper(x + half, bottom), paper(x - half, bottom))
    figure.add(Polyline(points=box, closed=True, layer=LAYER_OUTLINE))
    figure.add(Line(x1=box[0][0], y1=box[0][1], x2=box[2][0], y2=box[2][1],
                    layer=LAYER_THIN),
               Line(x1=box[1][0], y1=box[1][1], x2=box[3][0], y2=box[3][1],
                    layer=LAYER_THIN))

    # 吊索：吊钩中心 → 顶面两个吊点（粗红线），吊点画出小圆
    hook = paper(*model.hook_seat)
    for lug_x in (x - model.lug_x, x + model.lug_x):
        c = paper(lug_x, top)
        figure.add(Line(x1=hook[0], y1=hook[1], x2=c[0], y2=c[1], layer=LAYER_RIGGING),
                   Circle(cx=c[0], cy=c[1], r=0.85, layer=LAYER_RIGGING))

    # 重心：形心符号 + 偏心引线
    cx, cy = model.cg
    centroid_symbol(figure, paper, cx, cy)
    ccx, ccy = paper(*model.load_center)
    gx, gy = paper(cx, cy)
    if abs(model.cg_x) > 1e-6 or abs(model.cg_z) > 1e-6:
        figure.add(Line(x1=ccx, y1=ccy, x2=gx, y2=gy, layer=LAYER_CENTER))
    D.leader(figure, (gx, gy), (gx + 3.6, gy + 5.4), "重心G", height=2.5)


def _draw_dimensions(figure: Figure, paper: _Paper, model: ElevationModel,
                     *, derived_angle: bool) -> None:
    center_x, _ = model.load_center
    near_edge = center_x - model.load_w / 2.0
    x_left = paper(center_x + model.load_w / 2.0, 0.0)[0]   # 吊物远边（图左）
    ground = paper.oy
    hook_x, hook_y = paper(model.radius, model.hook_h)
    tip_x, tip_y = paper(*model.head_sheave)
    load_bottom_y = paper(0.0, model.load_bottom)[1]
    load_top_y = paper(0.0, model.load_top)[1]

    hz_x = x_left + CHAIN_HZ
    h_x = x_left + CHAIN_H
    hx_x = x_left + CHAIN_H123

    # Hz：地面 → 臂端滑轮中心
    D.dashed(figure, (hz_x + 1.0, tip_y), (tip_x, tip_y), layer=LAYER_THIN)
    D.v_dim(figure, ground, tip_y, hz_x,
            f"Hz={model.tip_height:.2f} m", ref_x=tip_x, side="left", ext_ends=("hi",))
    # H：地面 → 吊钩中心
    D.dashed(figure, (h_x + 1.0, hook_y), (hook_x, hook_y), layer=LAYER_THIN)
    D.v_dim(figure, ground, hook_y, h_x,
            f"H={model.hook_h:.2f} m", ref_x=hook_x, side="left", ext_ends=("hi",))
    # h1~h3：吊物底 / 吊物高 / 吊索高
    D.v_dim(figure, ground, load_bottom_y, hx_x,
            f"h1={model.load_bottom:.2f} m", ref_x=x_left + 2.0, side="left",
            ext_ends=("hi",))
    D.v_dim(figure, load_bottom_y, load_top_y, hx_x,
            f"h2={model.load_h:.2f} m", ref_x=x_left + 2.0, side="left")
    D.v_dim(figure, load_top_y, hook_y, hx_x,
            f"h3={model.sling_drop:.2f} m", ref_x=x_left + 2.0, side="left")
    # h0：吊钩中心 → 臂端
    h0_x = hook_x - 26.0
    D.dashed(figure, (h0_x + 1.0, hook_y), (hook_x, hook_y), layer=LAYER_THIN)
    D.dashed(figure, (h0_x + 1.0, tip_y), (tip_x, tip_y), layer=LAYER_THIN)
    D.v_dim(figure, hook_y, tip_y, h0_x,
            f"h0={model.tip_height - model.hook_h:.2f} m", side="left")

    # 吊索真实夹角含宽度方向分量，立面画不出来，数值统一放在「吊物与吊索」表里

    # R / f / g：地面以下
    axis_x = paper.ox
    near_x = paper(near_edge, 0.0)[0]
    far_x = x_left
    y_f = ground - 8.0
    y_r = ground - 16.0
    if near_edge > 0.05:
        D.h_dim(figure, axis_x, near_x, y_f, f"f={near_edge:.2f} m",
                ref_y=ground, above=True)
    D.h_dim(figure, near_x, far_x, y_f, f"g={model.load_w:.2f} m", ref_y=ground, above=True)
    D.h_dim(figure, axis_x, hook_x, y_r, f"R={model.radius:.2f} m", ref_y=ground, above=True)

    # L：沿臂长
    foot = paper(*model.hinge)
    tip_pt = paper(*model.tip)
    D.aligned_dim(figure, foot, tip_pt, -(_boom_half(0.5) * paper.s + 6.0),
                  f"L={model.boom_len:.2f} m", height=3.0)

    # 仰角：文字放在弧外靠近地面的那一侧，避开臂架
    arc_r = 13.0
    D.angle_dim(figure, foot[0], foot[1], arc_r, 180.0 - model.boom_angle, 180.0,
                ("≈" if derived_angle else "") + f"a={model.boom_angle:.1f}°",
                text_xy=(foot[0] - arc_r - 3.0, foot[1] + 1.4))

    # E：地面 → 臂架铰点
    front_x = paper(-BODY_FRONT, 0.0)[0]
    D.v_dim(figure, ground, foot[1], front_x + 4.0, f"E={HINGE_H:.2f} m",
            ref_x=front_x, side="right")


def _draw_markers(figure: Figure, paper: _Paper, model: ElevationModel) -> None:
    axis_x = paper.ox
    ground = paper.oy
    # 回转中心：点划线 + 标注
    D.dash_dot(figure, (axis_x, ground - 7.0), (axis_x, ground + 1.0),
               layer=LAYER_CENTER)
    figure.add(Text(x=axis_x + 2.0, y=ground - 2.6, content="回转中心", height=2.4,
                    layer=LAYER_NOTE))

    hook_x, hook_y = paper(model.radius, model.hook_h)
    # 吊钩中心：文字在钩左侧，引线指向吊钩组
    D.leader(figure, (hook_x, hook_y),
             (hook_x - 9.0, hook_y + 3.4), "吊钩中心", align=ALIGN_RIGHT)

    head_x, head_y = paper(*model.head_sheave)
    D.leader(figure, (head_x, head_y), (head_x - 7, head_y + 10), "臂头滑轮组",
             align=ALIGN_RIGHT, height=2.6)
    winch_x, winch_y = paper(*MAIN_WINCH)
    D.leader(figure, (winch_x, winch_y), (winch_x + 9, winch_y + 7), "主起升卷筒", height=2.6)

    # 主臂：文字在臂上侧，引线指向臂中段
    mid = 0.55
    rad = model.rad
    mx = model.hinge[0] + model.boom_len * mid * math.cos(rad) - math.sin(rad) * _boom_half(mid)
    my = HINGE_H + model.boom_len * mid * math.sin(rad) + math.cos(rad) * _boom_half(mid)
    target = paper(mx, my)
    D.leader(figure, target, (target[0] - 12.0, target[1] + 6.0), "主臂",
             align=ALIGN_RIGHT)

    # 吊索
    sling_mid = paper((model.radius + model.load_center[0] - model.lug_x) / 2.0,
                      (model.hook_h + model.load_top) / 2.0)
    D.leader(figure, sling_mid, (sling_mid[0] - 6.0, sling_mid[1] - 2.0), "吊索",
             align=ALIGN_RIGHT)

    # 吊物名牌等尺寸链排完再放置，短尺寸的数字可能伸到轮廓附近。
    x, _ = model.load_center
    left, bottom = paper(x+model.load_w/2,model.load_bottom)
    right, top = paper(x-model.load_w/2,model.load_top)
    label = Text(left+3,bottom+5,"吊物",height=2.6)
    above_ground = ground+1.5
    inside = (left+1,max(bottom+1,above_ground),right-1,top-1)
    outside = (left-70,above_ground,right+70,top+70)
    figure.add(place_label(figure,nearby_labels(label),bounds=inside)
               or place_label(figure,nearby_labels(label),bounds=outside) or label)


def _geometry(model: ElevationModel, scale: float, derived_angle: bool,
              axles: int | None, model_name: str) -> Figure:
    """只画立面几何（不含图框/标题栏/表格），用于按实际外包框排版。"""
    canvas = Figure(title="", width=0.0, height=0.0)
    paper = _Paper(scale=scale, ox=0.0, oy=0.0)
    draw_truck(canvas, paper, axles, model.hinge, model_name)
    _draw_boom(canvas, paper, model)
    _draw_luffing_cylinder(canvas, paper, model)
    _draw_hook_block(canvas, paper, model)
    _draw_rope(canvas, paper, model)
    _draw_load(canvas, paper, model)
    _draw_dimensions(canvas, paper, model, derived_angle=derived_angle)
    _draw_markers(canvas, paper, model)
    clear_annotation_lines(canvas)
    return canvas


def _shift(items: list[Any], dx: float, dy: float) -> list[Any]:
    from dataclasses import replace

    shifted: list[Any] = []
    for item in items:
        if isinstance(item, Line):
            shifted.append(replace(item, x1=item.x1 + dx, y1=item.y1 + dy,
                                   x2=item.x2 + dx, y2=item.y2 + dy))
        elif isinstance(item, Circle):
            shifted.append(replace(item, cx=item.cx + dx, cy=item.cy + dy))
        elif isinstance(item, Polyline):
            shifted.append(replace(item, points=tuple((x + dx, y + dy) for x, y in item.points)))
        elif isinstance(item, (Text, DrawingImage)):
            shifted.append(replace(item, x=item.x + dx, y=item.y + dy))
        else:  # pragma: no cover - 图元类型穷举
            shifted.append(item)
    return shifted


def _items_overlap(items: list[Any], rect: S.Rect) -> bool:
    """逐个图元判重叠（用实际外包框，不用整体包围盒）。"""
    from liftcalc.drawing.primitives import item_bbox

    for item in items:
        box = item_bbox(item)
        if box is not None and S.overlaps(box, rect):
            return True
    return False


def _load_table_rows(model: ElevationModel, load: dict[str, Any]) -> list[tuple[str, str]]:
    """吊物与吊索表：真实尺寸、重心、四索夹角与受力、推算的起升高度。"""
    rows: list[tuple[str, str]] = [
        ("吊物 L×B×H", f"{model.load_w:.2f}×{model.load_d:.2f}×{model.load_h:.2f} m"),
        ("吊物质量", f"{float(load.get('weight_t') or 0):.2f} t"),
        (
            "重心相对形心",
            f"({model.cg_x:+.2f}, {model.cg_y:+.2f}, {model.cg_z:+.2f}) m",
        ),
    ]
    slings = load.get("slings") or []
    if slings:
        for item in slings:
            rows.append(
                (
                    f"索{item['index']} {item['name']}",
                    f"{float(item['angle_deg']):.1f}°　{float(item['force_t'])*9.80665:.2f} kN",
                )
            )
    required_hook_h = float(load.get("hook_height_m") or model.hook_h)
    rows.append(("所需吊钩中心离地高度", f"{required_hook_h:.2f} m"))
    return rows


def _build_sheet_view(model: ElevationModel, model_notes: list[str],
                      cap: dict[str, Any], detail: dict[str, Any],
                      sheet: S.Sheet, orientation: str,
                      axles: int | None, load: dict[str, Any] | None = None) -> Figure | None:
    """在给定图幅上排一次版并出图。"""
    derived_angle = detail.get("boom_angle") is None
    load = load or {}
    model_name = str(detail.get("model") or cap.get("model") or "")

    # ---- 版面：家具位置固定，几何按实际外包框选比例并居中 -----------------
    x0, y0, x1, y1 = sheet.content
    # 标题栏贴图框右下角、说明贴左下角（都以图框线为基准，不是分区带内侧）
    _fx0, fy0, fx1, _fy1 = sheet.inner
    title_rect = (fx1 - 150.0, fy0, fx1, fy0 + 36.0)
    notes_rect = (x0, fy0, x0 + 130.0, fy0 + 38.0)
    # 预留区从图框左线起算，好让分区字母让位（draw_zones 会跳过被占用的段落）
    notes_reserve = (_fx0, fy0, x0 + 130.0, fy0 + 38.0)
    table_w = 84.0
    table_rows = 13 if cap.get("mode") == "dual" else 10
    perf_h = 5.2 + 1.2 + 5.2 * table_rows
    load_rows = _load_table_rows(model, load)
    load_h = 5.2 + 1.2 + 5.2 * len(load_rows)
    table_h = perf_h + load_h
    table_rect = (x1 - table_w, y1 - table_h, x1, y1)

    # 宽度方向用图框内侧（尺寸链可以靠近分区带，尺寸界线挤进 1 mm 以内不别扭），
    # 高度方向仍以内容区为准，给说明块留出位置。
    area = (_fx0 + 1.0, y0 + 39.0, fx1 - 1.0, y1 - 1.0)
    area_w = area[2] - area[0]
    area_h = area[3] - area[1]
    # 允许尺寸线探入分区带 2 mm（工程图允许尺寸界线靠近图框），避免为半毫米跳一档比例
    slack = 2.0

    chosen = None
    for denom_value in SCALE_LADDER:
        scale = 1000.0 / denom_value
        geometry = _geometry(model, scale, derived_angle, axles, model_name)
        bx0, by0, bx1, by1 = geometry.bbox()
        width, height = bx1 - bx0, by1 - by0
        if width > area_w + slack or height > area_h + slack:
            continue
        dx = area[0] + (area_w - width) / 2.0 - bx0
        dy = area[1] + (area_h - height) / 2.0 - by0
        rect = (bx0 + dx, by0 + dy, bx1 + dx, by1 + dy)
        if _items_overlap(_shift(geometry.primitives, dx, dy), table_rect):
            continue
        chosen = (denom_value, scale, geometry, dx, dy, rect)
        break
    if chosen is None:                                   # 最大一档也放不下：取最小比例
        denom_value = SCALE_LADDER[-1]
        scale = 1000.0 / denom_value
        geometry = _geometry(model, scale, derived_angle, axles, model_name)
        bx0, by0, bx1, by1 = geometry.bbox()
        dx = area[0] - bx0
        dy = area[1] - by0
        chosen = (denom_value, scale, geometry, dx, dy,
                  (bx0 + dx, by0 + dy, bx1 + dx, by1 + dy))

    denom_value, scale, geometry, dx, dy, content_rect = chosen

    figure = Figure(title="吊装立面图", width=sheet.width, height=sheet.height)
    S.draw_frame(figure, sheet)
    S.draw_zones(figure, sheet, [title_rect, notes_reserve, table_rect])
    S.draw_ground(figure, area[0], area[2], dy)   # 几何按 oy=0 建，平移 dy 后地面在 y=dy

    geometry_start = len(figure.primitives)
    figure.primitives.extend(_shift(geometry.primitives, dx, dy))
    geometry_end = len(figure.primitives)

    # ---- 性能表 ----------------------------------------------------------
    rated_lift = detail.get("lift_height")
    rows: list[tuple[str, str]] = [
        ("机型", model_name),
        ("起重臂长度 L", f"{model.boom_len:.2f} m"),
        ("工作幅度 R", f"{model.radius:g} m"),
        ("起重臂仰角 α", f"{model.boom_angle:.1f}°"),
        ("图示吊钩中心高度 H", f"{model.hook_h:.2f} m"),
        ("表列起升高度", "—" if rated_lift is None else f"{float(rated_lift):.2f} m"),
        ("表列额定总起重量", f"{float(detail.get('rated_load') or 0):g} t"),
        ("计算总起重量", f"{float(detail.get('required') or 0):.2f} t"),
        ("负荷率", f"{float(detail.get('utilization') or 0):.3f}"),
        ("负荷率上限", f"{float(cap.get('limit') or 0):.0%}"),
    ]
    if cap.get("mode") == "dual":
        right = cap.get("right") or {}
        rows.extend([
            ("辅吊机型", str(right.get("model") or "")),
            ("辅吊最大工作幅度", f"{float(right.get('max_radius') or 0):g} m"),
            ("辅吊负荷率", f"{float(right.get('utilization') or 0):.3f}"),
        ])
    perf_rect = S.perf_table(figure, table_rect[2], table_rect[3], rows, width=table_w)
    S.perf_table(figure, table_rect[2], perf_rect[1], load_rows, width=table_w,
                 title="吊物与吊索")

    # ---- 说明 ------------------------------------------------------------
    slings = load.get("slings") or []
    angles = [float(item["angle_deg"]) for item in slings]
    forces = [float(item["force_t"])*9.80665 for item in slings]
    notes = [
        f"比例 1:{denom_value}（A3 竖幅），单位 m；R 为回转中心至吊钩中心的水平距离。",
        f"吊物按真实尺寸 {model.load_w:.2f}×{model.load_d:.2f}×{model.load_h:.2f} m 绘制，"
        f"宽 {model.load_d:.2f} m 为出图面方向。",
        "H 为图示吊钩中心离地高度。",
    ]
    if slings:
        if max(angles) - min(angles) < 0.05:
            angle_text = f"四索与竖直夹角均为 {angles[0]:.1f}°"
        else:
            angle_text = f"四索与竖直夹角 {min(angles):.1f}°~{max(angles):.1f}°"
        if max(forces) - min(forces) < 0.005:
            force_text = f"名义吊索拉力均为 {forces[0]:.2f} kN"
        else:
            force_text = (
                f"名义吊索拉力 {min(forces):.2f}~{max(forces):.2f} kN（重心偏心使四索受力不均）"
            )
        notes.append(f"{angle_text}，{force_text}。")
    notes.append("圆加双弧为形心与重心的图示符号。本图用于起重能力校核。")
    notes.extend(model_notes)
    if cap.get("mode") == "dual":
        notes.append("双机抬吊：图示按主吊工况，辅吊见性能表。")
    notes_rect_used = S.notes_block(
        figure, notes_rect[0], notes_rect[3], notes_rect[2] - notes_rect[0] - 2.0, notes,
        height=2.3, leading=3.9,
    )

    S.title_block(
        figure, sheet,
        title="吊装立面图",
        subtitle=model_name,
        scale_text=f"1:{denom_value}",
        drawing_no="LC-01",
        project="起重能力校核",
        date="",
    )

    figure.meta = {
        "orientation": orientation,
        "scale_denom": denom_value,
        "axles": axles,
        "scale": scale,
        "paper": (sheet.width, sheet.height),
        "content_rect": content_rect,
        "geometry_span": (geometry_start, geometry_end),
        "reserved": [title_rect, notes_rect_used, table_rect],
        "derived_angle": derived_angle,
        "hook_h": model.hook_h,
        "load_bottom": model.load_bottom,
        "model": model,
    }
    return figure


def elevation_figure(result: ComputationResult) -> Figure | None:
    """吊装立面图：自动选图幅方向（竖幅/横幅）与标准比例，再排图框、标题栏、
    性能表、说明、尺寸链与引线。"""
    cap = result.aux.get("capability") or {}
    detail = _capability_detail(cap)
    if detail is None:
        return None
    load = result.aux.get("load") or {}
    model, model_notes = _elevation_model(cap, detail, load)
    brand = (result.aux.get('case', {}).get('crane') or {}).get('brand', '徐工')
    axles = drawing_axles(cap, detail, brand)

    candidates: list[Figure] = []
    for width, height, name in ((297.0, 420.0, "portrait"), (420.0, 297.0, "landscape")):
        view = _build_sheet_view(model, model_notes, cap, detail,
                                 S.Sheet(width=width, height=height), name, axles, load)
        if view is not None:
            candidates.append(view)
    if not candidates:
        return None
    # 比例更大者优先（1:n 的 n 更小），同比例时竖幅优先
    return min(candidates, key=lambda f: (f.meta["scale_denom"],
                                         0 if f.meta["orientation"] == "portrait" else 1))


def figure_for(result: ComputationResult) -> Figure | None:
    return (
        capability_figure(result)
        or elevation_figure(result)
        or eye_figure(result)
        or section_figure(result)
    )


def figures_for(result: ComputationResult) -> list[Figure]:
    """一次产出该结果支持的全部图（能力曲线 + 立面 + 吊物三维示意）。"""
    from liftcalc.drawing.load3d import load_figure

    figures: list[Figure] = []
    for builder in (capability_figure, eye_figure, section_figure):
        figure = builder(result)
        if figure is not None:
            figures.append(figure)
    elevation = elevation_figure(result)
    if elevation is not None:
        figures.insert(1 if figures else 0, elevation)
    load = load_figure(result)
    if load is not None:
        figures.append(load)
    return figures
