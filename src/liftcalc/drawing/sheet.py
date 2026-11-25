"""图幅与图面组成：图框、分区、标题栏、说明、性能表、地面线。

全部坐标为图面 mm（y 向上）。文字锚点 y 是**字框顶边**，与 primitives.Text 一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from liftcalc.drawing.primitives import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    Figure,
    Line,
    Polyline,
    Text,
    text_width,
)
from liftcalc.drawing.style import LAYER_DIM, LAYER_NOTE, LAYER_TEXT, LAYER_THIN

Rect = tuple[float, float, float, float]


def overlaps(a: Rect, b: Rect, *, margin: float = 0.0) -> bool:
    return not (
        a[2] + margin <= b[0]
        or b[2] + margin <= a[0]
        or a[3] + margin <= b[1]
        or b[3] + margin <= a[1]
    )


def text_in_band(figure: Figure, x: float, y_bottom: float, band_h: float,
                 content: str, height: float, *, align: str = ALIGN_LEFT,
                 layer: str = LAYER_TEXT, max_width: float | None = None) -> None:
    """在高度 band_h 的横带内把文字竖直居中（y = 字框顶边）。"""
    if not content:
        return
    if max_width is not None:
        # Leave room for differences between the SVG, PNG and CAD fonts.
        height = min(height, max_width / text_width(content, 1.0) / 1.12)
    figure.add(
        Text(x=x, y=y_bottom + (band_h + height) / 2.0, content=content,
             height=height, align=align, layer=layer)
    )


@dataclass(frozen=True)
class Sheet:
    """图幅与图框（GB 常用：装订边 25，其余 5）。"""

    width: float
    height: float
    left: float = 25.0
    bottom: float = 5.0
    right: float = 5.0
    top: float = 5.0
    zone: float = 8.0            # 分区编号带宽度

    @property
    def inner(self) -> Rect:
        return (self.left, self.bottom, self.width - self.right, self.height - self.top)

    @property
    def content(self) -> Rect:
        """扣掉分区带之后的可用区域。"""
        x0, y0, x1, y1 = self.inner
        return (x0 + self.zone, y0 + self.zone, x1 - self.zone, y1 - self.zone)


def draw_frame(figure: Figure, sheet: Sheet) -> None:
    # 纸边细线 + 图框粗线
    figure.add(
        Polyline(
            points=((0.5, 0.5), (sheet.width - 0.5, 0.5),
                    (sheet.width - 0.5, sheet.height - 0.5), (0.5, sheet.height - 0.5)),
            closed=True,
            layer=LAYER_THIN,
        )
    )
    x0, y0, x1, y1 = sheet.inner
    figure.add(
        Polyline(points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)), closed=True,
                 layer=LAYER_TEXT)
    )


def draw_zones(figure: Figure, sheet: Sheet, reserved: list[Rect]) -> None:
    """分区编号：1–8 / A–H，刻线在分区带内，编号在带中；被标题栏/表格占用的段落不画。"""
    x0, y0, x1, y1 = sheet.inner
    band = sheet.zone

    columns = 8
    step = (x1 - x0) / columns
    for index in range(columns + 1):
        x = x0 + step * index
        if index < columns:
            center = x + step / 2.0
            if not any(overlaps((center - 1.2, y1 - band, center + 1.2, y1), rect)
                       for rect in reserved):
                text_in_band(figure, center, y1 - band, band, str(index + 1), 2.5,
                             align=ALIGN_CENTER, layer=LAYER_DIM)
            if not any(overlaps((center - 1.2, y0, center + 1.2, y0 + band), rect)
                       for rect in reserved):
                text_in_band(figure, center, y0, band, str(index + 1), 2.5,
                             align=ALIGN_CENTER, layer=LAYER_DIM)
        if index in (0, columns):
            continue
        for tick in ((x, y1 - band, x, y1), (x, y0, x, y0 + band)):
            if not any(overlaps(tick, rect) for rect in reserved):
                figure.add(Line(x1=tick[0], y1=tick[1], x2=tick[2], y2=tick[3],
                                layer=LAYER_THIN))

    rows = 8
    step = (y1 - y0) / rows
    for index in range(rows + 1):
        y = y0 + step * index
        if index < rows:
            center = y + step / 2.0
            if not any(overlaps((x0, center - 1.2, x0 + band, center + 1.2), rect)
                       for rect in reserved):
                figure.add(Text(x=x0 + 2.6, y=center + 0.9, content=chr(ord("A") + index),
                                height=2.5, layer=LAYER_DIM))
            if not any(overlaps((x1 - band, center - 1.2, x1, center + 1.2), rect)
                       for rect in reserved):
                figure.add(Text(x=x1 - 2.6, y=center + 0.9, content=chr(ord("A") + index),
                                height=2.5, align=ALIGN_RIGHT, layer=LAYER_DIM))
        if index in (0, rows):
            continue
        for tick in ((x0, y, x0 + band, y), (x1 - band, y, x1, y)):
            if not any(overlaps(tick, rect) for rect in reserved):
                figure.add(Line(x1=tick[0], y1=tick[1], x2=tick[2], y2=tick[3],
                                layer=LAYER_THIN))


def draw_ground(figure: Figure, x0: float, x1: float, y: float) -> None:
    figure.add(Line(x1=x0, y1=y, x2=x1, y2=y, layer=LAYER_TEXT))
    pos = x0 + 2.0
    while pos < x1 - 1.0:
        figure.add(Line(x1=pos, y1=y, x2=pos - 2.2, y2=y - 2.2, layer=LAYER_THIN))
        pos += 4.0


def title_block(figure: Figure, sheet: Sheet, *, title: str, subtitle: str,
                scale_text: str, drawing_no: str, project: str, date: str,
                sheet_no: str = "1/1", designer: str = "") -> Rect:
    """标题栏（150 × 36），贴图框右下角。"""
    x1 = sheet.width - sheet.right
    x0 = x1 - 150.0
    y0 = sheet.bottom
    y1 = y0 + 36.0

    figure.add(Polyline(points=((x0, y0), (x1, y0), (x1, y1), (x0, y1)), closed=True,
                        layer=LAYER_TEXT))
    row_a, row_b, row_c = y1 - 14.0, y1 - 22.0, y1 - 29.0
    for y in (row_a, row_b, row_c):
        figure.add(Line(x1=x0, y1=y, x2=x1, y2=y, layer=LAYER_TEXT))

    text_in_band(figure, x0 + 3.0, row_a, y1 - row_a, title, 4.2, max_width=98.0)
    text_in_band(figure, x1 - 3.0, row_a, y1 - row_a, subtitle, 3.4, align=ALIGN_RIGHT, max_width=43.0)

    # 第二行：工程名称 | 图号 | 比例
    cols = (x0 + 80.0, x0 + 116.0)
    for x in cols:
        figure.add(Line(x1=x, y1=row_b, x2=x, y2=row_a, layer=LAYER_TEXT))
    label_h = 3.4
    for left, right, label, value in (
        (x0, cols[0], "工程名称", project),
        (cols[0], cols[1], "图号", drawing_no),
        (cols[1], x1, "比例", scale_text),
    ):
        text_in_band(figure, left + 2.5, row_a - label_h, label_h, label, 2.0,
                     layer=LAYER_NOTE)
        text_in_band(figure, left + 2.5, row_b, row_a - row_b - label_h, value, 2.5,
                     max_width=right - left - 5)

    # 第三行：设计/校核/审核/批准
    sign_cols = (x0 + 38.0, x0 + 76.0, x0 + 114.0)
    for x in sign_cols:
        figure.add(Line(x1=x, y1=row_c, x2=x, y2=row_b, layer=LAYER_TEXT))
    for x, label in zip((x0, *sign_cols), ("设计", "校核", "审核", "批准"), strict=False):
        text_in_band(figure, x + 2.5, row_c, row_b - row_c, label, 2.2,
                     layer=LAYER_NOTE)
        if x == x0 and designer:
            text_in_band(figure, x + 12.0, row_c, row_b - row_c, designer, 2.5, max_width=22.0)
        else:
            figure.add(Line(x1=x + 12.0, y1=row_c + 2.4, x2=x + 34.0, y2=row_c + 2.4,
                            layer=LAYER_THIN))

    # 第四行：日期/版本/页次/编号
    foot_cols = (x0 + 38.0, x0 + 80.0, x0 + 116.0)
    for x in foot_cols:
        figure.add(Line(x1=x, y1=y0, x2=x, y2=row_c, layer=LAYER_TEXT))
    band = row_c - y0
    for left, right, label, value in zip(
        (x0, *foot_cols), (*foot_cols, x1), ("日期", "版本", "页次", "编号"),
        (date, "v0.1", sheet_no, drawing_no), strict=True,
    ):
        text_in_band(figure, left + 2.5, y0 + 3.6, band - 3.6, label, 2.0,
                     layer=LAYER_NOTE)
        text_in_band(figure, left + 2.5, y0, 3.6, value, 2.2, max_width=right - left - 5)

    return (x0, y0, x1, y1)


def perf_table(figure: Figure, x_right: float, y_top: float, rows: list[tuple[str, str]],
               *, width: float = 78.0, row_h: float = 5.2,
               title: str = "采用的起重性能表数据") -> Rect:
    """右上角性能表：一行标题 + 若干"项目/数值"行。"""
    head_h = row_h + 1.2
    height = head_h + row_h * len(rows)
    x0 = x_right - width
    y0 = y_top - height
    divider = x0 + min(30.0, width * .4)
    pad = 2.0

    figure.add(Polyline(points=((x0, y0), (x_right, y0), (x_right, y_top), (x0, y_top)),
                        closed=True, layer=LAYER_TEXT))
    figure.add(Line(x1=x0, y1=y_top - head_h, x2=x_right, y2=y_top - head_h,
                    layer=LAYER_TEXT))
    text_in_band(figure, x0 + pad, y_top - head_h, head_h, title, 2.8, max_width=width - 2*pad)
    figure.add(Line(x1=divider, y1=y0, x2=divider, y2=y_top - head_h,
                    layer=LAYER_THIN))

    for index, (label, value) in enumerate(rows):
        band_bottom = y_top - head_h - row_h * (index + 1)
        text_in_band(figure, x0 + pad, band_bottom, row_h, label, 2.3, layer=LAYER_NOTE,
                     max_width=divider - x0 - 2*pad)
        text_in_band(figure, divider + pad, band_bottom, row_h, value, 2.4,
                     max_width=x_right - divider - 2*pad)
        if index < len(rows) - 1:
            figure.add(Line(x1=x0, y1=band_bottom, x2=x_right, y2=band_bottom,
                            layer=LAYER_THIN))
    return (x0, y0, x_right, y_top)


def wrap_text(content: str, width: float, height: float) -> list[str]:
    """按估算字宽折行（中文按字断，西文尽量在空格处断）。"""
    lines: list[str] = []
    current = ""
    for char in content:
        candidate = current + char
        if text_width(candidate, height) > width and current:
            cut = current.rfind(" ")
            if cut > len(current) // 2:
                lines.append(current[:cut])
                current = current[cut + 1:] + char
            else:
                lines.append(current)
                current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def notes_block(figure: Figure, x: float, y_top: float, width: float,
                notes: list[str], *, height: float = 2.4,
                leading: float = 4.2) -> Rect:
    """左下角"说明"：标题 + 编号条目，自动折行。返回占用矩形。"""
    text_in_band(figure, x, y_top - 5.0, 5.0, "说明：", 2.8)
    y = y_top - 6.6
    for index, note in enumerate(notes, start=1):
        prefix = f"{index}. "
        indent = text_width(prefix, height)
        lines = wrap_text(note, width - indent, height)
        for line_index, line in enumerate(lines):
            figure.add(Text(x=x if line_index == 0 else x + indent, y=y,
                            content=prefix + line if line_index == 0 else line,
                            height=height))
            y -= leading
        y -= 0.9
    return (x, y, x + width, y_top)
