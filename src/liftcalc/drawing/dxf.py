"""DXF 渲染（设计 §11.4）。

用 ezdxf 输出 R2010，单位设为毫米（$INSUNITS = 4）。
只用 LINE / CIRCLE / LWPOLYLINE / TEXT，保证通用性。
"""

from __future__ import annotations

from pathlib import Path

from liftcalc.drawing.primitives import (
    LAYER_COLORS,
    Circle,
    Figure,
    Line,
    Polyline,
    Text,
)


def to_dxf(figure: Figure, out_path: Path) -> Path:
    import logging

    # 先降噪再导入：ezdxf 在 Windows 上找不到字体缓存目录时会刷警告，与输出无关
    logging.getLogger("ezdxf").setLevel(logging.ERROR)
    logging.getLogger("fontTools").setLevel(logging.ERROR)

    import ezdxf  # 延迟导入：避免 calc/report 也被字体缓存拖慢

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4  # 毫米
    doc.header["$MEASUREMENT"] = 1  # 公制

    for layer, color in LAYER_COLORS.items():
        if layer not in doc.layers:
            doc.layers.add(name=layer, color=color)

    modelspace = doc.modelspace()
    for item in figure.primitives:
        attribs = {"layer": item.layer}
        if isinstance(item, Line):
            modelspace.add_line((item.x1, item.y1), (item.x2, item.y2), dxfattribs=attribs)
        elif isinstance(item, Circle):
            modelspace.add_circle((item.cx, item.cy), item.r, dxfattribs=attribs)
        elif isinstance(item, Polyline):
            points = list(item.points)
            if item.closed and points[0] != points[-1]:
                points.append(points[0])
            modelspace.add_lwpolyline(points, dxfattribs=attribs, close=item.closed)
        elif isinstance(item, Text):
            modelspace.add_text(
                item.content,
                dxfattribs={**attribs, "height": item.height},
            ).set_placement((item.x, item.y))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    return out_path
