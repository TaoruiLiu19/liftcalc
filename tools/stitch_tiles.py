"""把「幅度列 + 若干臂长列」拼成一张块，保证每块都自带行标签。"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
from PIL import Image

PDF = r"D:\学习日志\吊装\研究\徐工70~500吨汽车吊参数表.pdf"
OUT = Path(r"D:\学习日志\吊装\研究\_pdf_pages")


def render(page: pymupdf.Page, x0: float, x1: float, y0: float, y1: float, dpi: int) -> Image.Image:
    rect = page.rect
    clip = pymupdf.Rect(x0 * rect.width, y0 * rect.height, x1 * rect.width, y1 * rect.height)
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def stitch(
    page_index: int,
    page_no: int,
    band: str,
    y0: float,
    y1: float,
    groups: list[tuple[float, float, str]],
    dpi: int = 380,
) -> list[Path]:
    doc = pymupdf.open(PDF)
    page = doc[page_index]
    label_strip = render(page, 0.13, 0.205, y0, y1, dpi)
    outputs: list[Path] = []
    for x0, x1, name in groups:
        right = render(page, x0, x1, y0, y1, dpi)
        width = label_strip.width + 8 + right.width
        height = max(label_strip.height, right.height)
        canvas = Image.new("RGB", (width, height), "white")
        canvas.paste(label_strip, (0, 0))
        canvas.paste(right, (label_strip.width + 8, 0))
        path = OUT / f"p{page_no}" / f"{band}_{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path)
        outputs.append(path)
        print(path.name, canvas.width, "x", canvas.height)
    doc.close()
    return outputs


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: stitch_tiles.py <page_no 1-based>")
        raise SystemExit(2)
    page_no = int(sys.argv[1])
    page_index = page_no - 1
    if page_no == 2:
        for band, (y0, y1) in {"U": (0.315, 0.560), "L": (0.545, 0.790)}.items():
            stitch(
                page_index, page_no, band, y0, y1,
                [
                    (0.20, 0.42, "b1"),
                    (0.42, 0.62, "b2"),
                    (0.62, 0.86, "b3"),
                ],
            )
