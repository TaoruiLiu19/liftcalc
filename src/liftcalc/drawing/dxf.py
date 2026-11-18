"""DXF 渲染（设计 §11.4）。

用 ezdxf 输出 R2010，单位毫米（$INSUNITS = 4）。
只用 LINE / CIRCLE / LWPOLYLINE / TEXT，保证通用性。
图层颜色与线宽取自 style，与 SVG/PNG 一致。
"""

from __future__ import annotations

from pathlib import Path

from liftcalc.drawing.primitives import (
    ALIGN_CENTER,
    ALIGN_RIGHT,
    Circle,
    Figure,
    Line,
    Polyline,
    Text,
)
from liftcalc.drawing.style import COLORS_ACI, LAYERS, dxf_lineweight


def _alignment(align: str):
    from ezdxf.enums import TextEntityAlignment

    if align == ALIGN_CENTER:
        return TextEntityAlignment.TOP_CENTER
    if align == ALIGN_RIGHT:
        return TextEntityAlignment.TOP_RIGHT
    return TextEntityAlignment.TOP_LEFT


def to_dxf(figure: Figure, out_path: Path) -> Path:
    import logging

    # 先降噪再导入：ezdxf 在 Windows 上找不到字体缓存目录时会刷警告，与输出无关
    logging.getLogger("ezdxf").setLevel(logging.ERROR)
    logging.getLogger("fontTools").setLevel(logging.ERROR)

    import ezdxf

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # 毫米
    doc.header["$MEASUREMENT"] = 1  # 公制

    for layer in LAYERS:
        if layer not in doc.layers:
            doc.layers.add(name=layer, color=COLORS_ACI.get(layer, 7),
                           lineweight=dxf_lineweight(layer))

    modelspace = doc.modelspace()
    for item in figure.primitives:
        layer = getattr(item, "layer", "OUTLINE")
        attribs = {"layer": layer, "lineweight": dxf_lineweight(layer)}
        if isinstance(item, Line):
            modelspace.add_line((item.x1, item.y1), (item.x2, item.y2), dxfattribs=attribs)
        elif isinstance(item, Circle):
            modelspace.add_circle((item.cx, item.cy), item.r, dxfattribs=attribs)
        elif isinstance(item, Polyline):
            points = list(item.points)
            if len(points) < 2:
                continue
            modelspace.add_lwpolyline(points, dxfattribs=attribs, close=item.closed)
        elif isinstance(item, Text):
            text = modelspace.add_text(
                item.content,
                dxfattribs={**attribs, "rotation": item.angle, "height": item.height},
            )
            text.set_placement((item.x, item.y), align=_alignment(item.align))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    return out_path
