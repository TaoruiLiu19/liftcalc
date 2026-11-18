"""图元模型（设计 §11.2）。

内核不画图：绘图只消费 result.aux 里的图元描述。
坐标单位 mm，y 轴向上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

LAYER_OUTLINE = "OUTLINE"
LAYER_HIDDEN = "HIDDEN"
LAYER_DIM = "DIM"
LAYER_THIN = "THIN"
LAYER_RIGGING = "RIGGING"
LAYER_CENTER = "CENTER"
LAYER_TEXT = "TEXT"
LAYER_NOTE = "NOTE"

LAYER_COLORS = {
    LAYER_OUTLINE: 7,
    LAYER_HIDDEN: 8,
    LAYER_DIM: 4,
    LAYER_CENTER: 1,
    LAYER_TEXT: 2,
    LAYER_NOTE: 8,
    LAYER_RIGGING: 1,
}


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


Primitive = Union[Line, Circle, Polyline, Text]


@dataclass
class Figure:
    title: str
    width: float
    height: float
    primitives: list[Primitive] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, *items: Primitive) -> None:
        self.primitives.extend(items)

    @property
    def caption(self) -> str:
        return " · ".join([self.title, *self.notes])
