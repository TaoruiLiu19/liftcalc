"""图面样式：图层、颜色、线宽、图幅、比例梯——**唯一来源**。

三个渲染器（SVG / DXF / PNG）都从这里取样式，避免同一图元在三份产物里
颜色和线宽不一致（历史上 SVG 的 DIM 是蓝色、PNG 是绿色）。

颜色约定（与 README 一致）：
    OUTLINE / TEXT  黑        实体轮廓、文字
    DIM             绿        尺寸线、尺寸文字
    CENTER          红        中心线
    RIGGING         深红加粗   索具、吊索
    THIN            浅灰      辅助线、伸缩节分界线
    HIDDEN          灰        虚线、参考线
    NOTE            灰        引线标注文字
"""

from __future__ import annotations

LAYER_OUTLINE = "OUTLINE"
LAYER_HIDDEN = "HIDDEN"
LAYER_DIM = "DIM"
LAYER_THIN = "THIN"
LAYER_RIGGING = "RIGGING"
LAYER_CENTER = "CENTER"
LAYER_TEXT = "TEXT"
LAYER_NOTE = "NOTE"
LAYER_TRACE_CENTER = "TRACE_CENTER"
LAYER_TRACE_A = "TRACE_A"
LAYER_TRACE_B = "TRACE_B"
LAYER_TRACE_GATE = "TRACE_GATE"

LAYERS = (
    LAYER_OUTLINE,
    LAYER_HIDDEN,
    LAYER_DIM,
    LAYER_THIN,
    LAYER_RIGGING,
    LAYER_CENTER,
    LAYER_TEXT,
    LAYER_NOTE,
    LAYER_TRACE_CENTER,
    LAYER_TRACE_A,
    LAYER_TRACE_B,
    LAYER_TRACE_GATE,
)

#: 屏幕/位图颜色（RGB）
COLORS_RGB: dict[str, tuple[int, int, int]] = {
    LAYER_OUTLINE: (32, 32, 32),
    LAYER_HIDDEN: (140, 140, 140),
    LAYER_DIM: (0, 140, 60),        # 绿
    LAYER_THIN: (150, 150, 150),
    LAYER_RIGGING: (170, 20, 20),   # 深红
    LAYER_CENTER: (200, 30, 30),    # 红
    LAYER_TEXT: (17, 17, 17),
    LAYER_NOTE: (105, 105, 105),
    LAYER_TRACE_CENTER: (0, 97, 87),
    LAYER_TRACE_A: (38, 80, 166),
    LAYER_TRACE_B: (164, 74, 14),
    LAYER_TRACE_GATE: (115, 55, 132),
}

#: CAD 索引色（ACI）
COLORS_ACI: dict[str, int] = {
    LAYER_OUTLINE: 7,
    LAYER_HIDDEN: 8,
    LAYER_DIM: 3,
    LAYER_THIN: 9,
    LAYER_RIGGING: 1,
    LAYER_CENTER: 1,
    LAYER_TEXT: 7,
    LAYER_NOTE: 8,
    LAYER_TRACE_CENTER: 4,
    LAYER_TRACE_A: 5,
    LAYER_TRACE_B: 30,
    LAYER_TRACE_GATE: 6,
}

#: 线宽（mm）——同时用于 SVG / PNG / DXF(线宽表取最近档)
LINEWEIGHT_MM: dict[str, float] = {
    LAYER_OUTLINE: 0.35,
    LAYER_HIDDEN: 0.18,
    LAYER_DIM: 0.18,
    LAYER_THIN: 0.13,
    LAYER_RIGGING: 0.50,
    LAYER_CENTER: 0.18,
    LAYER_TEXT: 0.25,
    LAYER_NOTE: 0.18,
    LAYER_TRACE_CENTER: 0.75,
    LAYER_TRACE_A: 0.42,
    LAYER_TRACE_B: 0.42,
    LAYER_TRACE_GATE: 0.45,
}

#: DXF 允许的线宽档位（1/100 mm）
DXF_LINEWEIGHTS = (13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200)

#: 图幅（mm），(宽, 高)
PAPER = {
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
}

#: 标准比例梯（1:n），从大到小
SCALE_LADDER = (50, 100, 150, 200, 250, 300, 400, 500)


def dxf_lineweight(layer: str) -> int:
    """把 mm 线宽取到 DXF 允许的档位。"""
    target = int(round(LINEWEIGHT_MM.get(layer, 0.25) * 100))
    return min(DXF_LINEWEIGHTS, key=lambda value: abs(value - target))
