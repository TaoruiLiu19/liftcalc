"""SVG 渲染（设计 §11.5）。坐标 mm，y 轴向上。"""

from __future__ import annotations

from xml.sax.saxutils import escape

from liftcalc.drawing.primitives import Circle, Figure, Line, Polyline, Text
from liftcalc.drawing.primitives import Image as DrawingImage

_LAYER_STROKE = {
    "OUTLINE": "#222222",
    "HIDDEN": "#888888",
    "DIM": "#0a7ea4",
    "CENTER": "#c0392b",
    "TEXT": "#111111",
    "NOTE": "#777777",
}

_LAYER_WIDTH = {
    "OUTLINE": 0.6,
    "HIDDEN": 0.35,
    "DIM": 0.3,
    "CENTER": 0.25,
    "TEXT": 0.3,
    "NOTE": 0.3,
}


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
    parts.append('<g transform="translate(0,0)">')

    for item in figure.primitives:
        if isinstance(item, DrawingImage):
            import base64
            import pathlib as _pl
            data = base64.b64encode(_pl.Path(item.path).read_bytes()).decode()
            y = -item.y - item.h
            parts.append(
                f'<image x="{item.x:.3f}" y="{y:.3f}" width="{item.w:.3f}" '
                f'height="{item.h:.3f}" href="data:image/png;base64,{data}" />'
            )
            continue
        stroke = _LAYER_STROKE.get(item.layer, "#222222")
        stroke_width = _LAYER_WIDTH.get(item.layer, 0.4)
        if isinstance(item, Line):
            parts.append(
                f'<line x1="{item.x1:.3f}" y1="{-item.y1:.3f}" x2="{item.x2:.3f}" y2="{-item.y2:.3f}" '
                f'stroke="{stroke}" stroke-width="{stroke_width}" />'
            )
        elif isinstance(item, Circle):
            parts.append(
                f'<circle cx="{item.cx:.3f}" cy="{-item.cy:.3f}" r="{item.r:.3f}" fill="none" '
                f'stroke="{stroke}" stroke-width="{stroke_width}" />'
            )
        elif isinstance(item, Polyline):
            points = " ".join(f"{x:.3f},{-y:.3f}" for x, y in item.points)
            tag = "polygon" if item.closed else "polyline"
            parts.append(
                f'<{tag} points="{points}" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" />'
            )
        elif isinstance(item, Text):
            parts.append(
                f'<text x="{item.x:.3f}" y="{-item.y:.3f}" font-family="sans-serif" '
                f'font-size="{item.height:.2f}" fill="{stroke}" '
                f'dominant-baseline="text-before-edge">{escape(item.content)}</text>'
            )

    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)
