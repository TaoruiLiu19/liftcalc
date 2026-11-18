"""SVG 渲染（设计 §11.5）。坐标 mm，y 轴向上；输出时 y 取反。"""

from __future__ import annotations

import base64
import pathlib
from xml.sax.saxutils import escape

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
from liftcalc.drawing.style import COLORS_RGB, LINEWEIGHT_MM

_FONT_STACK = "Microsoft YaHei, SimHei, Noto Sans CJK SC, Source Han Sans SC, sans-serif"

_TEXT_ANCHOR = {ALIGN_CENTER: "middle", ALIGN_RIGHT: "end"}


def _rgb(layer: str) -> str:
    red, green, blue = COLORS_RGB.get(layer, (32, 32, 32))
    return f"#{red:02x}{green:02x}{blue:02x}"


def to_svg(figure: Figure, margin: float = 8.0) -> str:
    width = figure.width + 2 * margin
    height = figure.height + 2 * margin
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}mm" height="{height:.2f}mm" '
        f'viewBox="{-margin:.2f} {-margin:.2f} {width:.2f} {height:.2f}">'
    )
    parts.append(f"<title>{escape(figure.title)}</title>")
    parts.append(f"<desc>{escape(figure.caption)}</desc>")

    for item in figure.primitives:
        layer = getattr(item, "layer", "OUTLINE")
        stroke = _rgb(layer)
        line_width = LINEWEIGHT_MM.get(layer, 0.25)

        if isinstance(item, DrawingImage):
            data = base64.b64encode(pathlib.Path(item.path).read_bytes()).decode()
            y = -item.y - item.h
            parts.append(
                f'<image x="{item.x:.3f}" y="{y:.3f}" width="{item.w:.3f}" '
                f'height="{item.h:.3f}" href="data:image/png;base64,{data}" />'
            )
        elif isinstance(item, Line):
            parts.append(
                f'<line x1="{item.x1:.3f}" y1="{-item.y1:.3f}" x2="{item.x2:.3f}" '
                f'y2="{-item.y2:.3f}" stroke="{stroke}" stroke-width="{line_width:.2f}" '
                f'stroke-linecap="round" />'
            )
        elif isinstance(item, Circle):
            parts.append(
                f'<circle cx="{item.cx:.3f}" cy="{-item.cy:.3f}" r="{item.r:.3f}" fill="none" '
                f'stroke="{stroke}" stroke-width="{line_width:.2f}" />'
            )
        elif isinstance(item, Polyline):
            points = " ".join(f"{x:.3f},{-y:.3f}" for x, y in item.points)
            tag = "polygon" if item.closed else "polyline"
            parts.append(
                f'<{tag} points="{points}" fill="none" stroke="{stroke}" '
                f'stroke-width="{line_width:.2f}" stroke-linejoin="round" />'
            )
        elif isinstance(item, Text):
            anchor = _TEXT_ANCHOR.get(item.align, "start")
            transform = ""
            if item.angle:
                transform = (f' transform="rotate({-item.angle:.3f} '
                             f'{item.x:.3f} {-item.y:.3f})"')
            parts.append(
                f'<text x="{item.x:.3f}" y="{-item.y:.3f}" font-family="{_FONT_STACK}" '
                f'font-size="{item.height:.2f}" fill="{stroke}" text-anchor="{anchor}" '
                f'dominant-baseline="text-before-edge"{transform}>{escape(item.content)}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)
