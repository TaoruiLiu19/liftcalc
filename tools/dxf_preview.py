"""DXF -> PNG 预览（支持块嵌套的平移/旋转/缩放），用于无 CAD 环境验收。"""

from __future__ import annotations

import math
import pathlib
import re

import ezdxf
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"

_UNI = re.compile(r"\\U\+([0-9A-Fa-f]{4})")


def _decode(text: str) -> str:
    """把 DXF 里的 \\U+XXXX 转成真实汉字。"""
    return _UNI.sub(lambda m: chr(int(m.group(1), 16)), text)

ACI = {
    1: (200, 0, 0), 2: (200, 150, 0), 3: (0, 130, 0), 4: (0, 140, 150),
    5: (0, 0, 200), 6: (150, 0, 150), 7: (25, 25, 25), 8: (110, 110, 110), 9: (150, 150, 150),
}


class Xf:
    """二维仿射：X' = a*x + b*y + c, Y' = d*x + e*y + f"""

    def __init__(self, a=1.0, b=0.0, c=0.0, d=0.0, e=1.0, f=0.0):
        self.a, self.b, self.c, self.d, self.e, self.f = a, b, c, d, e, f

    def __call__(self, x: float, y: float) -> tuple[float, float]:
        return self.a * x + self.b * y + self.c, self.d * x + self.e * y + self.f

    def then(self, other: "Xf") -> "Xf":
        """先做 self，再做 other。"""
        return Xf(
            other.a * self.a + other.b * self.d,
            other.a * self.b + other.b * self.e,
            other.a * self.c + other.b * self.f + other.c,
            other.d * self.a + other.e * self.d,
            other.d * self.b + other.e * self.e,
            other.d * self.c + other.e * self.f + other.f,
        )

    @property
    def scale(self) -> float:
        return math.hypot(self.a, self.d)


def _entity_color(entity) -> tuple[int, int, int]:
    try:
        aci = int(entity.dxf.color)
        if aci in ACI:
            return ACI[aci]
    except Exception:
        pass
    try:
        layer = entity.doc.layers.get(entity.dxf.layer)
        aci = int(layer.dxf.color)
        if aci in ACI:
            return ACI[aci]
    except Exception:
        pass
    return ACI[7]


def collect(doc, layout):
    items: list[tuple] = []
    xs: list[float] = []
    ys: list[float] = []

    def note(p):
        xs.append(p[0])
        ys.append(p[1])

    def walk(entities, xf: Xf, depth: int = 0) -> None:
        if depth > 6:
            return
        for entity in entities:
            kind = entity.dxftype()
            color = _entity_color(entity)
            if kind == "LINE":
                p1 = xf(entity.dxf.start[0], entity.dxf.start[1])
                p2 = xf(entity.dxf.end[0], entity.dxf.end[1])
                items.append(("line", p1, p2, color))
                note(p1)
                note(p2)
            elif kind == "LWPOLYLINE":
                pts = [xf(p[0], p[1]) for p in entity.get_points("xy")]
                if len(pts) > 1:
                    items.append(("poly", pts, entity.closed, color))
                    for p in pts:
                        note(p)
            elif kind == "POLYLINE":
                pts = [xf(v.dxf.location[0], v.dxf.location[1]) for v in entity.vertices]
                if len(pts) > 1:
                    items.append(("poly", pts, entity.is_closed, color))
                    for p in pts:
                        note(p)
            elif kind == "CIRCLE":
                c = xf(entity.dxf.center[0], entity.dxf.center[1])
                r = entity.dxf.radius * xf.scale
                items.append(("circle", c, r, color))
                note((c[0] - r, c[1] - r))
                note((c[0] + r, c[1] + r))
            elif kind == "ARC":
                c = entity.dxf.center
                r = entity.dxf.radius
                a0 = math.radians(entity.dxf.start_angle)
                a1 = math.radians(entity.dxf.end_angle)
                pts = []
                steps = 18
                for k in range(steps + 1):
                    ang = a0 + (a1 - a0) * k / steps
                    pts.append(xf(c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)))
                items.append(("poly", pts, False, color))
                for p in pts:
                    note(p)
            elif kind in ("TEXT", "MTEXT", "ATTDEF"):
                text = entity.dxf.text if kind != "MTEXT" else entity.text
                try:
                    pos = xf(entity.dxf.insert[0], entity.dxf.insert[1])
                    height = float(entity.dxf.height) * xf.scale
                except Exception:
                    continue
                if text and str(text).strip():
                    items.append(("text", pos, _decode(str(text)), max(height, 1.0), color))
                    note(pos)
            elif kind == "INSERT":
                block = doc.blocks.get(entity.dxf.name)
                base = block.block.dxf.base_point
                rot = math.radians(float(getattr(entity.dxf, "rotation", 0.0) or 0.0))
                sx = float(getattr(entity.dxf, "xscale", 1) or 1)
                sy = float(getattr(entity.dxf, "yscale", 1) or 1)
                ins = entity.dxf.insert
                local = Xf(1, 0, -base[0], 0, 1, -base[1]).then(
                    Xf(sx * math.cos(rot), -sy * math.sin(rot), 0,
                       sx * math.sin(rot), sy * math.cos(rot), 0)
                ).then(Xf(1, 0, ins[0], 0, 1, ins[1]))
                walk(block, local.then(xf), depth + 1)

    walk(layout, Xf())
    if not xs:
        return items, (0.0, 0.0, 1.0, 1.0)
    return items, (min(xs), min(ys), max(xs), max(ys))


def render(dxf_path: pathlib.Path, png_path: pathlib.Path, target_px: float = 2400.0) -> None:
    doc = ezdxf.readfile(str(dxf_path))
    items, (x0, y0, x1, y1) = collect(doc, doc.modelspace())

    span = max(x1 - x0, y1 - y0, 1e-6)
    s = target_px / span
    margin = 30
    width = int((x1 - x0) * s) + 2 * margin
    height = int((y1 - y0) * s) + 2 * margin
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def P(p) -> tuple[float, float]:
        return margin + (p[0] - x0) * s, height - margin - (p[1] - y0) * s

    for item in items:
        if item[0] == "line":
            draw.line([P(item[1]), P(item[2])], fill=item[3], width=1)
        elif item[0] == "poly":
            pts = [P(p) for p in item[1]]
            if item[2]:
                pts = pts + [pts[0]]
            draw.line(pts, fill=item[3], width=1)
        elif item[0] == "circle":
            c, r = item[1], item[2] * s
            cx, cy = P(c)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=item[3], width=1)
        elif item[0] == "text":
            _, pos, text, h, color = item
            size = max(5, int(h * s * 1.3))
            try:
                font = ImageFont.truetype(FONT_PATH, size)
            except OSError:
                font = ImageFont.load_default()
            draw.text(P(pos), text, fill=color, font=font)

    png_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(png_path)
    print(f"已渲染 {png_path} {image.size}")


if __name__ == "__main__":
    import sys

    render(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]),
           float(sys.argv[3]) if len(sys.argv) > 3 else 2400.0)
