"""PNG 位图渲染（无 CAD 时看图用）。

与 SVG / DXF 共用同一套图元与样式：
    * 文字锚点 y = 字框顶边；
    * align 控制水平对齐，angle 为逆时针角度（绕锚点）；
    * 颜色、线宽取自 style。

中文字体按 LIFTCALC_FONT → 微软雅黑 → 黑体 → Noto/思源 → DejaVu 的顺序查找。
"""

from __future__ import annotations

import functools
import os
import pathlib

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

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

PX_PER_MM = 10          # 约 254 dpi
MARGIN_MM = 2.0

_FONT_CANDIDATES = (
    os.environ.get("LIFTCALC_FONT", ""),
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/PingFang.ttc",
)


@functools.lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in _FONT_CANDIDATES:
        if candidate and os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _color(layer: str) -> tuple[int, int, int]:
    return COLORS_RGB.get(layer, (32, 32, 32))


def _width(layer: str, px_per_mm: float) -> int:
    return max(1, int(round(LINEWEIGHT_MM.get(layer, 0.25) * px_per_mm)))


def _anchor(align: str) -> str:
    if align == ALIGN_CENTER:
        return "ma"
    if align == ALIGN_RIGHT:
        return "ra"
    return "la"


def _draw_text(background: PILImage.Image, draw: ImageDraw.ImageDraw, item: Text,
               point, px_per_mm: float) -> None:
    size = max(6, int(round(item.height * px_per_mm)))
    font = _font(size)
    fill = _color(item.layer)
    x, y = point(item.x, item.y)          # y = 字框顶边（像素）

    if not item.angle:
        draw.text((x, y), item.content, font=font, fill=fill, anchor=_anchor(item.align))
        return

    # 旋转文字：先画到临时图，绕自身中心旋转，再按字框中心贴回（与 SVG/DXF 同一约定：
    # angle 为模型坐标下的逆时针，字框见 Text.bbox）
    probe = ImageDraw.Draw(PILImage.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), item.content, font=font,
                                              anchor=_anchor(item.align))
    pad = size
    temp_w = int(abs(right - left) + 2 * pad)
    temp_h = int(abs(bottom - top) + 2 * pad)
    temp = PILImage.new("RGBA", (temp_w, temp_h), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp)
    temp_draw.text((pad - left, pad - top), item.content, font=font, fill=fill,
                   anchor=_anchor(item.align))
    rotated = temp.rotate(item.angle, resample=PILImage.BICUBIC, expand=True)

    ink = rotated.getbbox()
    if ink is None:
        return
    box = item.bbox()
    center_x = (box[0] + box[2]) / 2.0
    center_y = (box[1] + box[3]) / 2.0
    target = point(center_x, center_y)
    paste_x = target[0] - (ink[0] + ink[2]) / 2.0
    paste_y = target[1] - (ink[1] + ink[3]) / 2.0
    background.paste(rotated, (int(round(paste_x)), int(round(paste_y))), rotated)


def to_png(figure: Figure, out_path: pathlib.Path, *, px_per_mm: float = PX_PER_MM) -> pathlib.Path:
    margin = int(round(MARGIN_MM * px_per_mm))
    width = int(round(figure.width * px_per_mm)) + 2 * margin
    height = int(round(figure.height * px_per_mm)) + 2 * margin
    image = PILImage.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def point(x: float, y: float) -> tuple[float, float]:
        return margin + x * px_per_mm, margin + (figure.height - y) * px_per_mm

    for item in figure.primitives:
        layer = getattr(item, "layer", "OUTLINE")
        color = _color(layer)
        if isinstance(item, Line):
            draw.line([point(item.x1, item.y1), point(item.x2, item.y2)],
                      fill=color, width=_width(layer, px_per_mm))
        elif isinstance(item, Circle):
            if item.r <= 0:
                continue
            cx, cy = point(item.cx, item.cy)
            radius = item.r * px_per_mm
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                         outline=color, width=_width(layer, px_per_mm))
        elif isinstance(item, Polyline):
            if len(item.points) < 2:
                continue
            pts = [point(x, y) for x, y in item.points]
            if item.closed:
                pts.append(pts[0])
            draw.line(pts, fill=color, width=_width(layer, px_per_mm), joint="curve")
        elif isinstance(item, DrawingImage):
            try:
                stamp = PILImage.open(item.path).convert("RGBA")
            except OSError:
                continue
            target_w = max(1, int(round(item.w * px_per_mm)))
            target_h = max(1, int(round(item.h * px_per_mm)))
            stamp = stamp.resize((target_w, target_h), PILImage.LANCZOS)
            px, py = point(item.x, item.y + item.h)
            image.paste(stamp, (int(round(px)), int(round(py))), stamp)
        elif isinstance(item, Text):
            _draw_text(image, draw, item, point, px_per_mm)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path
