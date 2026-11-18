"""从原厂规格书 PDF 直接提取起重性能表（XCT130L8_1 第 17 页试点）。

不扫描、不 OCR：PDF 自带文字层，按表格结构取值。
"""

from __future__ import annotations

import csv
import pathlib

import pymupdf

SRC = pathlib.Path(r"D:\学习日志\吊装\liftcalc\out\bz\q130T_XCT130L8_1.pdf")
OUT = pathlib.Path(r"D:\学习日志\吊装\liftcalc\out\bz\xct130_page17.csv")


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    cleaned = str(text).strip().replace("\n", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_page(page: pymupdf.Page) -> list[dict[str, object]]:
    table = max(page.find_tables().tables, key=lambda t: t.row_count * t.col_count)
    rows = table.extract()

    # 表头行：数据区里数字最多的那一行
    header_index = max(
        range(min(6, len(rows))),
        key=lambda i: sum(1 for cell in rows[i] if _num(cell) is not None),
    )
    header = rows[header_index]

    # 数据列：表头有数值、且不是两侧的幅度列
    data_cols = [c for c, cell in enumerate(header) if _num(cell) is not None]

    # 幅度列：最左侧、数值递增的那一列
    radius_col = 0
    for c in range(len(header)):
        values = [_num(r[c]) for r in rows[header_index + 1 :] if c < len(r)]
        numbers = [v for v in values if v is not None]
        if len(numbers) > 5 and numbers == sorted(numbers):
            radius_col = c
            break

    # 组合代码行：含"组合"或 Code 的那一行
    code_row = None
    for row in rows[header_index + 1 :]:
        joined = " ".join("" if c is None else str(c) for c in row)
        if "组合" in joined or "Code" in joined:
            code_row = row
            break

    out: list[dict[str, object]] = []
    for row in rows[header_index + 1 :]:
        if code_row is not None and row is code_row:
            continue
        radius = _num(row[radius_col]) if radius_col < len(row) else None
        if radius is None:
            continue
        for c in data_cols:
            if c >= len(row):
                continue
            load = _num(row[c])
            if load is None:
                continue
            boom = _num(header[c])
            code = ""
            if code_row is not None and c < len(code_row) and code_row[c]:
                code = str(code_row[c]).strip().replace("\n", "")
            out.append(
                {"boom_len": boom, "code": code, "radius": radius, "load": load}
            )
    return out


def main() -> None:
    doc = pymupdf.open(SRC)
    records = extract_page(doc[16])
    doc.close()

    keys = sorted({(r["boom_len"], r["code"]) for r in records})
    print(f"提取 {len(records)} 格，{len(keys)} 个组合")
    for boom, code in keys:
        series = [r for r in records if (r["boom_len"], r["code"]) == (boom, code)]
        loads = [r["load"] for r in series]
        ok = loads == sorted(loads, reverse=True)
        print(f"  {boom:>5g} m  代码 {code:<8s} {len(series):>2} 格  单调不增: {ok}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["boom_len", "code", "radius", "load"])
        writer.writeheader()
        writer.writerows(records)
    print("已写入", OUT)


if __name__ == "__main__":
    main()
