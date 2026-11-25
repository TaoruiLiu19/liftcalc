"""Render the same engineering report as standalone HTML or editable Word."""

import base64
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

from liftcalc.drawing.primitives import Figure
from liftcalc.drawing.svg import to_svg
from liftcalc.report.content import Report, Table, design_report


HTML_STYLE = """
:root{font-family:"Microsoft YaHei UI","Noto Sans CJK SC",sans-serif;color:#1a2730;background:#edf1f3;line-height:1.7}
*{box-sizing:border-box}
body{margin:0;padding:22px}
main{max-width:930px;margin:auto;padding:clamp(18px,4vw,48px);background:white;border:1px solid #d6dfe3}
h1,h2{line-height:1.38;color:#111c22}
h1{margin:0 0 20px;font-size:clamp(23px,3vw,34px)}
h2{margin:26px 0 10px;font-size:1.22rem}
p{margin:9px 0}
.conclusion{border-inline-start:4px solid #426470;background:#eff4f5;padding:10px 14px;margin:0 0 17px}
.conclusion p{margin:3px 0}
.table-wrap{overflow-x:auto;margin:10px 0 14px}
table{width:100%;border-collapse:collapse;font-size:.9rem;font-variant-numeric:tabular-nums}
th,td{padding:6px 9px;border:1px solid #bdcbd1;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#e8eef0;font-weight:650}
figure{margin:16px 0;text-align:center;break-inside:avoid}
figure img{display:block;width:100%;height:auto;max-height:92vh;object-fit:contain;margin:auto;border:1px solid #d6dfe3}
figcaption{margin-top:5px;font-size:.88rem}
p,figcaption{overflow-wrap:anywhere}
@media(max-width:520px){body{padding:0}main{border:0}th,td{padding:5px}}
@media print{
 @page{size:A4;margin:16mm}
 :root{background:white;color:black}body,main{padding:0;border:0}
 h2{break-after:avoid}tr{break-inside:avoid}thead{display:table-header-group}
 .table-wrap{overflow:visible}figure img{max-height:225mm}
}
"""


def _html_table(table: Table) -> str:
    columns = ("<colgroup>" + "".join(f'<col style="width:{width:.0%}">' for width in table.widths) + "</colgroup>"
               if table.widths else "")
    headers = "".join(f'<th scope="col">{escape(value)}</th>' for value in table.headers)
    rows = "".join("<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
                   for row in table.rows)
    return f'<div class="table-wrap"><table>{columns}<thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>'


def report_html(report: Report) -> str:
    title = escape(report.title)
    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title><style>{HTML_STYLE}</style></head><body><main>",
        f'<h1>{title}</h1><div class="conclusion"><strong>{escape(report.status)}</strong>'
        f"<p>{escape(report.overview)}</p></div>",
    ]
    if report.information:
        parts.append(_html_table(Table(("项目", "工程信息"), report.information, (.28, .72))))
    for index, section in enumerate(report.sections, 1):
        parts.append(f"<section><h2>{index} {escape(section.title)}</h2>")
        for block in section.blocks:
            if isinstance(block, Table):
                parts.append(_html_table(block))
            elif isinstance(block, Figure):
                source = base64.b64encode(to_svg(block, margin=0).encode("utf-8")).decode("ascii")
                label = escape(block.title)
                parts.append(f'<figure><img src="data:image/svg+xml;base64,{source}" alt="{label}">'
                             f"<figcaption>{label}</figcaption></figure>")
            else:
                parts.append(f"<p>{escape(block)}</p>")
        parts.append("</section>")
    return "\n".join([*parts, "</main></body></html>"])


def _word_table(document, model: Table, width):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt

    table = document.add_table(rows=1, cols=len(model.headers))
    table.style = "Table Grid"
    table.autofit = False
    fractions = model.widths or (1/len(model.headers),) * len(model.headers)
    for column, fraction in zip(table.columns, fractions, strict=True):
        column.width = int(width * fraction)
    for index, values in enumerate([model.headers, *model.rows]):
        row = table.rows[0] if index == 0 else table.add_row()
        properties = row._tr.get_or_add_trPr()
        properties.append(OxmlElement("w:cantSplit"))
        if index == 0:
            properties.append(OxmlElement("w:tblHeader"))
        for cell, value, column in zip(row.cells, values, table.columns, strict=True):
            cell.width = column.width
            if index == 0:
                shading = OxmlElement("w:shd")
                shading.set(qn("w:fill"), "E8EEF0")
                cell._tc.get_or_add_tcPr().append(shading)
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_before = Pt(2)
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.keep_with_next = index == 0 or index < len(model.rows) <= 3
            font = paragraph.add_run(value).font
            font.bold = index == 0
            font.size = Pt(9.5)


def _word_document(report: Report, path: Path) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT, WD_SECTION_START
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Mm, Pt, RGBColor

    document = Document()
    document.core_properties.title = report.title
    document.core_properties.author = dict(report.information).get("设计人", "")
    page = document.sections[0]
    page.page_width, page.page_height = Mm(210), Mm(297)
    page.left_margin = page.right_margin = Mm(19)
    page.top_margin = page.bottom_margin = Mm(16)
    footer = page.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    page_number = OxmlElement("w:fldSimple")
    page_number.set(qn("w:instr"), "PAGE")
    footer._p.append(page_number)
    width = page.page_width - page.left_margin - page.right_margin
    for name, size in (("Normal", 10.5), ("Title", 21), ("Heading 1", 14), ("Caption", 9)):
        style = document.styles[name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.size = Pt(size)
        style.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "宋体")
        border = style.element.find(".//" + qn("w:pBdr"))
        if border is not None:
            border.getparent().remove(border)
    normal = document.styles["Normal"].paragraph_format
    normal.space_after = Pt(5)
    normal.line_spacing = 1.22
    document.add_paragraph(report.title, style="Title")
    document.add_paragraph().add_run(report.status).bold = True
    document.add_paragraph(report.overview)
    if report.information:
        _word_table(document, Table(("项目", "工程信息"), report.information, (.28, .72)), width)
    with TemporaryDirectory() as temp:
        for index, section in enumerate(report.sections, 1):
            figures = [block for block in section.blocks if isinstance(block, Figure)]
            landscape = bool(figures) and all(block.width > block.height for block in figures)
            if landscape:
                page = document.add_section(WD_SECTION_START.NEW_PAGE)
                page.orientation = WD_ORIENT.LANDSCAPE
                page.page_width, page.page_height = Mm(297), Mm(210)
                width = page.page_width - page.left_margin - page.right_margin
            heading = document.add_heading(f"{index} {section.title}", level=1)
            heading.paragraph_format.page_break_before = bool(figures) and not landscape
            for j, block in enumerate(section.blocks):
                if isinstance(block, Table):
                    _word_table(document, block, width)
                elif isinstance(block, Figure):
                    from liftcalc.drawing.png import to_png

                    image = to_png(block, Path(temp) / f"{index}-{j}.png", px_per_mm=5)
                    caption = document.add_paragraph(block.title, style="Caption")
                    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    caption.paragraph_format.keep_with_next = True
                    caption.paragraph_format.page_break_before = j > 0
                    picture = document.add_paragraph()
                    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    available = page.page_height - page.top_margin - page.bottom_margin - Mm(25)
                    picture.add_run().add_picture(str(image), width=min(width, int(available * block.width / block.height)))
                else:
                    paragraph = document.add_paragraph(block)
                    paragraph.paragraph_format.keep_with_next = (
                        j+1 < len(section.blocks) and isinstance(section.blocks[j+1], Table)
                    )
    document.save(path)


def write_report(report: Report, out_path: Path) -> Path:
    suffix = out_path.suffix.lower()
    if suffix not in (".html", ".docx"):
        raise ValueError("计算书格式须为 HTML 或 DOCX。")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".html":
        out_path.write_text(report_html(report), encoding="utf-8")
    else:
        _word_document(report, out_path)
    return out_path


def render_report(result, out_path: Path, *, title=None, case_payload=None) -> Path:
    return write_report(design_report(result, title=title, case_payload=case_payload), out_path)
