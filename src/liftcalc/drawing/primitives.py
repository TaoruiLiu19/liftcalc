"""图元模型（设计 §11.2）。

内核不画图：绘图只消费 result.aux 里的图元描述。
坐标单位 mm，y 轴向上。

文字约定（三个渲染器必须一致）：
    (x, y) 是文字**锚点**；未旋转时 y 是字框**顶边**。
    align 只管水平方向：left / center / right。
    angle 是逆时针角度（度），绕锚点旋转。
    字框：x0 = x (left) / x - w/2 (center) / x - w (right)，y1 = y，y0 = y - height。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from liftcalc.drawing.style import (
    COLORS_ACI as LAYER_COLORS,
)
from liftcalc.drawing.style import (
    LAYER_CENTER,
    LAYER_DIM,
    LAYER_HIDDEN,
    LAYER_NOTE,
    LAYER_OUTLINE,
    LAYER_RIGGING,
    LAYER_TEXT,
    LAYER_THIN,
)

__all__ = [
    "LAYER_CENTER",
    "LAYER_COLORS",
    "LAYER_DIM",
    "LAYER_HIDDEN",
    "LAYER_NOTE",
    "LAYER_OUTLINE",
    "LAYER_RIGGING",
    "LAYER_TEXT",
    "LAYER_THIN",
    "Circle",
    "Figure",
    "Image",
    "Line",
    "Polyline",
    "Primitive",
    "Text",
    "text_width",
]

ALIGN_LEFT = "left"
ALIGN_CENTER = "center"
ALIGN_RIGHT = "right"
ALIGNMENTS = (ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT)

#: ASCII 字符宽度 / 字高（近似值，只用于排版估算，不参与最终定位）
_ASCII_WIDTH = 0.62
_CJK_WIDTH = 1.0


def text_width(content: str, height: float) -> float:
    """估算文字宽度（mm）。中文按全角 1.0×字高，西文按 0.62×字高。"""
    total = 0.0
    for char in content:
        if char == " ":
            total += 0.35
        elif ord(char) >= 0x2E80:
            total += _CJK_WIDTH
        else:
            total += _ASCII_WIDTH
    return total * height


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str = LAYER_OUTLINE


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    r: float
    layer: str = LAYER_OUTLINE


@dataclass(frozen=True)
class Polyline:
    points: tuple[tuple[float, float], ...]
    closed: bool = True
    layer: str = LAYER_OUTLINE


@dataclass(frozen=True)
class Image:
    """贴在图纸上的位图块（左下角 x,y，尺寸 w,h，单位 mm）。"""

    x: float
    y: float
    w: float
    h: float
    path: str


@dataclass(frozen=True)
class Text:
    x: float
    y: float
    content: str
    height: float = 4.0
    layer: str = LAYER_TEXT
    align: str = ALIGN_LEFT
    angle: float = 0.0

    def __post_init__(self) -> None:
        if self.align not in ALIGNMENTS:
            raise ValueError(f"不支持的对齐方式：{self.align}")
        if self.height <= 0:
            raise ValueError("字高必须为正")

    @property
    def width(self) -> float:
        return text_width(self.content, self.height)

    def bbox(self) -> tuple[float, float, float, float]:
        """字框外包 (x0, y0, x1, y1)，考虑 align 与 angle（绕锚点逆时针）。"""
        if self.align == ALIGN_CENTER:
            x0 = self.x - self.width / 2
        elif self.align == ALIGN_RIGHT:
            x0 = self.x - self.width
        else:
            x0 = self.x
        corners = ((x0, self.y), (x0 + self.width, self.y),
                   (x0 + self.width, self.y - self.height), (x0, self.y - self.height))
        if self.angle:
            rad = math.radians(self.angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            corners = tuple(
                (self.x + (px - self.x) * cos_a - (py - self.y) * sin_a,
                 self.y + (px - self.x) * sin_a + (py - self.y) * cos_a)
                for px, py in corners
            )
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        return min(xs), min(ys), max(xs), max(ys)


Primitive = Line | Circle | Polyline | Text | Image


def item_bbox(item: Primitive) -> tuple[float, float, float, float] | None:
    """单个图元的外包框 (x0, y0, x1, y1)；Image 取矩形，Text 考虑对齐与旋转。"""
    if isinstance(item, Line):
        return (min(item.x1, item.x2), min(item.y1, item.y2),
                max(item.x1, item.x2), max(item.y1, item.y2))
    if isinstance(item, Circle):
        return (item.cx - item.r, item.cy - item.r, item.cx + item.r, item.cy + item.r)
    if isinstance(item, Polyline):
        if not item.points:
            return None
        xs = [p[0] for p in item.points]
        ys = [p[1] for p in item.points]
        return (min(xs), min(ys), max(xs), max(ys))
    if isinstance(item, Image):
        return (item.x, item.y, item.x + item.w, item.y + item.h)
    if isinstance(item, Text):
        return item.bbox()
    return None


@dataclass
class Figure:
    title: str
    width: float
    height: float
    primitives: list[Primitive] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def add(self, *items: Primitive) -> None:
        self.primitives.extend(items)

    @property
    def caption(self) -> str:
        return " · ".join([self.title, *self.notes])

    def bbox(self, *, skip_layers: tuple[str, ...] = ()) -> tuple[float, float, float, float]:
        """全部图元的外包框（忽略指定图层，用于排除图框/标题栏）。"""
        xs: list[float] = []
        ys: list[float] = []
        for item in self.primitives:
            if getattr(item, "layer", None) in skip_layers:
                continue
            box = item_bbox(item)
            if box is None:
                continue
            xs.extend((box[0], box[2]))
            ys.extend((box[1], box[3]))
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs), max(ys)
