"""把 Figure 基元直接画成 PNG（用于人工查看，不影响 SVG/DXF 输出）。"""

from __future__ import annotations

import json
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from liftcalc.core.result import ComputationResult  # noqa: E402
from liftcalc.drawing.figures import figures_for  # noqa: E402
from liftcalc.drawing.primitives import Circle, Line, Polyline, Text
from liftcalc.drawing.primitives import Image as DrawingImage  # noqa: E402

PX_PER_MM = 10
FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"

COLORS = {
    "DIM": (0, 128, 0),
    "CENTER": (200, 30, 30),
    "TEXT": (20, 20, 20),
    "NOTE": (60, 60, 60),
    "HIDDEN": (140, 140, 140),
    "THIN": (170, 170, 170),
    "RIGGING": (200, 20, 20),
}


def _width(item: object) -> int:
    return 3 if "RIGGING" in str(getattr(item, "layer", "")) else 1


def _color(item: object) -> tuple[int, int, int]:
    layer = str(getattr(item, "layer", "") or "")
    for key, value in COLORS.items():
        if key in layer:
            return value
    return (0, 0, 0)


def render(figure: object, out: pathlib.Path) -> None:
    width = int(figure.width * PX_PER_MM) + 40
    height = int(figure.height * PX_PER_MM) + 40
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    margin = 20

    def point(x: float, y: float) -> tuple[float, float]:
        return margin + x * PX_PER_MM, margin + (figure.height - y) * PX_PER_MM

    for item in figure.primitives:
        color = _color(item)
        if isinstance(item, Line):
            draw.line([point(item.x1, item.y1), point(item.x2, item.y2)], fill=color, width=_width(item) + 1)
        elif isinstance(item, Circle):
            cx, cy = point(item.cx, item.cy)
            r = item.r * PX_PER_MM
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
        elif isinstance(item, Polyline):
            pts = [point(x, y) for x, y in item.points]
            if len(pts) > 1:
                draw.line(pts + ([pts[0]] if getattr(item, "closed", False) else []),
                          fill=color, width=_width(item) + 1)
        elif isinstance(item, DrawingImage):
            from PIL import Image as PILImage
            try:
                stamp = PILImage.open(item.path).convert("RGBA")
            except OSError:
                continue
            tw = max(1, int(item.w * PX_PER_MM))
            th = max(1, int(item.h * PX_PER_MM))
            stamp = stamp.resize((tw, th), PILImage.LANCZOS)
            px, py = point(item.x, item.y + item.h)
            image.paste(stamp, (int(px), int(py)), stamp)
        elif isinstance(item, Text):
            size = max(10, int(getattr(item, "height", 3.0) * PX_PER_MM * 1.4))
            try:
                font = ImageFont.truetype(FONT_PATH, size)
            except OSError:
                font = ImageFont.load_default()
            x, y = point(item.x, item.y)
            draw.text((x, y - size), str(item.content), fill=color, font=font)

    image.save(out)
    print("已渲染", out, image.size)


def main() -> None:
    result_path = pathlib.Path(sys.argv[1])
    result = ComputationResult.model_validate(json.loads(result_path.read_text(encoding="utf-8")))
    out_dir = pathlib.Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, figure in enumerate(figures_for(result), start=1):
        render(figure, out_dir / f"{result_path.stem}-{index}.png")


if __name__ == "__main__":
    main()
