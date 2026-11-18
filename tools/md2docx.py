"""把 Markdown 转成 Word（给不写代码的审阅人）。

只支持本项目说明书用到的语法：标题、表格、项目符号、代码块、段落、粗体。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

BOLD = re.compile(r"\*\*(.+?)\*\*")
IMAGE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")


def _set_fonts(document: Document) -> None:
    for name in ("Normal", "Heading 1", "Heading 2", "Heading 3"):
        style = document.styles[name]
        style.font.name = "Times New Roman"
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            from docx.oxml import OxmlElement

            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), "宋体")
    document.styles["Normal"].font.size = Pt(10.5)


def _add_rich(paragraph, text: str) -> None:
    position = 0
    for match in BOLD.finditer(text):
        if match.start() > position:
            paragraph.add_run(text[position : match.start()])
        run = paragraph.add_run(match.group(1))
        run.bold = True
        position = match.end()
    if position < len(text):
        paragraph.add_run(text[position:])


def _flush_table(document: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    header, body = rows[0], rows[1:]
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for index, cell in enumerate(header):
        table.rows[0].cells[index].text = ""
        _add_rich(table.rows[0].cells[index].paragraphs[0], cell)
        for run in table.rows[0].cells[index].paragraphs[0].runs:
            run.bold = True
    for row in body:
        cells = table.add_row().cells
        for index, cell in enumerate(row[: len(header)]):
            cells[index].text = ""
            _add_rich(cells[index].paragraphs[0], cell)


def convert(source: Path, target: Path) -> None:
    document = Document()
    _set_fonts(document)

    table_rows: list[list[str]] = []
    code_lines: list[str] = []
    in_code = False

    def close_table() -> None:
        nonlocal table_rows
        if table_rows:
            _flush_table(document, table_rows)
            document.add_paragraph()
            table_rows = []

    def close_code() -> None:
        nonlocal code_lines
        if code_lines:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.space_after = Pt(6)
            run = paragraph.add_run("\n".join(code_lines))
            run.font.name = "Consolas"
            run.font.size = Pt(8)
            code_lines = []

    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()

        image_match = IMAGE.match(line.strip())
        if image_match:
            close_table()
            close_code()
            alt, src = image_match.group(1), image_match.group(2)
            candidate = (source.parent / src).resolve()
            if candidate.exists():
                document.add_picture(str(candidate), width=Inches(5.9))
                if alt:
                    caption = document.add_paragraph(alt)
                    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                document.add_paragraph(f"（缺图：{src}）")
            continue

        if line.startswith("```"):
            close_table()
            if in_code:
                close_code()
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(raw)
            continue

        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
                continue
            table_rows.append(cells)
            continue
        close_table()

        if not line.strip():
            continue
        if line.startswith("---"):
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 1:
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = paragraph.add_run(text)
                run.bold = True
                run.font.size = Pt(20)
            else:
                document.add_heading(text, level=min(level - 1, 3))
            continue

        if line.startswith(("- ", "* ")):
            paragraph = document.add_paragraph(style="List Bullet")
            _add_rich(paragraph, line[2:])
            continue

        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Pt(18)
            _add_rich(paragraph, f"{numbered.group(1)}. {numbered.group(2)}")
            continue

        paragraph = document.add_paragraph()
        _add_rich(paragraph, line.strip())

    close_table()
    close_code()

    # 页脚提示
    footer = document.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run("本文件为工程计算说明，供专业审阅。")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

    target.parent.mkdir(parents=True, exist_ok=True)
    document.save(target)


if __name__ == "__main__":  # pragma: no cover
    if len(sys.argv) != 3:
        print("用法: python md2docx.py <源.md> <目标.docx>")
        raise SystemExit(2)
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"已生成 {sys.argv[2]}")
