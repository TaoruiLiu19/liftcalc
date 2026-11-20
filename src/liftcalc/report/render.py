"""计算书渲染（设计 §10）。

铁律 ADR-004：渲染器**不做任何计算**，只把 checks[] 与公式登记表填进文档。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from liftcalc.core.formula import Formula, get_formulas
from liftcalc.core.result import CheckResult, ComputationResult, Verdict

DISCLAIMER = "本计算由个人自研工具生成，仅供学习与复核参考，不作为工程实施依据。"

_VERDICT_TEXT = {Verdict.PASS: "满足", Verdict.FAIL: "不满足", Verdict.NA: "—"}

_CHECK_TITLES = {
    "capability.result": "反查结论",
    "capability.critical": "临界工况",
    "capability.lift_height": "起升高度（净空）",
    "capability.left": "主吊（左机）",
    "capability.right": "辅吊（右机）",
    "capability.shortfall": "最接近工况与缺口",
}


def _set_default_font(document: Document) -> None:
    style = document.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(10.5)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:  # pragma: no cover - 正常模板都有
        from docx.oxml import OxmlElement

        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), "宋体")


def _flatten(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            label = f"{prefix}{key}"
            if isinstance(value, dict):
                rows.extend(_flatten(value, f"{label}."))
            elif isinstance(value, list):
                rows.append((label, json.dumps(value, ensure_ascii=False)))
            else:
                rows.append((label, str(value)))
    else:
        rows.append((prefix or "value", str(data)))
    return rows


def _formula_text(formula_id: str, formulas: dict[str, Formula]) -> str:
    formula = formulas.get(formula_id)
    return formula.expression if formula else "—"


def _source_text(check: CheckResult, formulas: dict[str, Formula]) -> str:
    if check.source:
        return check.source
    formula = formulas.get(check.formula_id)
    return formula.source if formula else "—"


def _add_table(document: Document, header: list[str], rows: list[list[str]]) -> None:
    table = document.add_table(rows=1, cols=len(header))
    table.style = "Table Grid"
    for index, text in enumerate(header):
        table.rows[0].cells[index].text = text
    for row in rows:
        cells = table.add_row().cells
        for index, text in enumerate(row):
            cells[index].text = text


_PARAM_LABELS = {
    "kind": "计算类型",
    "mode": "计算方式",
    "payload": "吊件重量 (t)",
    "hook_mass": "吊钩重量 (t)",
    "rigging": "索具重量 (t)",
    "dynamic_factor": "动载系数",
    "limit": "负荷率上限",
    "crane.brand": "品牌",
    "crane.model": "机型",
    "second.brand": "第二台品牌",
    "second.model": "第二台机型",
    "left_share": "主吊承担比例",
    "asynchronism": "不同步系数",
    "required_lift_height": "所需起升高度 (m)",
    "load_width_m": "图示吊物宽 (m)",
    "load_height_m": "图示吊物高 (m)",
    "clearance_m": "图示吊物底净空 (m)",
    "boom_len": "臂长 (m)",
    "radius": "幅度 (m)",
    "tonnage": "额定起重量 (t)",
}

_PARAM_VALUES = {
    "crane.capability": "吊装能力反查",
    "crane.select": "吊车选型校核",
    "single": "单机",
    "dual": "双机抬吊",
}

_SKIP_PREFIX = ("units.", "meta.")


_DUAL_ONLY = ("left_share", "asynchronism", "second.brand", "second.model")


def _param_rows(payload: dict) -> list[list[str]]:
    rows: list[list[str]] = []
    is_dual = payload.get("mode") == "dual"
    for key, value in _flatten(payload):
        if key in _DUAL_ONLY and not is_dual:
            continue
        if key.startswith(_SKIP_PREFIX):
            continue
        if value is None or value == "" or value == "None":
            continue
        label = _PARAM_LABELS.get(key, key)
        text_value = str(value)
        text_value = _PARAM_VALUES.get(text_value, text_value)
        if isinstance(value, float) and value == int(value):
            text_value = f"{int(value)}"
        rows.append([label, text_value])
    return rows


def render_report(
    result: ComputationResult,
    out_path: Path,
    *,
    title: str = "吊装计算书",
    case_payload: dict[str, Any] | None = None,
) -> Path:
    formulas = get_formulas()
    document = Document()
    _set_default_font(document)

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    run.bold = True
    run.font.size = Pt(18)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kind_titles = {
        "crane.capability": "吊装能力反查",
        "crane.select": "吊车选型校核",
        "lifting_eye.check": "吊耳强度校核",
        "lifting_beam.check": "平衡梁校核",
        "lifting_rigging.check": "索具校核",
        "section.props": "截面特性",
        "geometry.centroid": "重心计算",
        "fea.frame2d": "平面框架分析",
    }
    kind_text = kind_titles.get(result.kind, result.kind)
    _mode = (result.aux.get("capability") or {}).get("mode")
    if result.kind == "crane.capability" and _mode:
        kind_text += "（双机抬吊）" if _mode == "dual" else "（单机）"
    subtitle.add_run(f"计算类型：{kind_text}").italic = True

    meta_rows = [
        ["引擎版本", result.engine_version],
        ["数据版本", result.data_version or "（未使用数据库）"],
        ["计算编号", result.input_digest[:8].upper()],
        ["总体判定", (result.aux.get('capability') or {}).get('status') or _VERDICT_TEXT.get(result.verdict, "—")],
        ["最大利用率", f"{result.utilization:.3f}"],
        ["控制项", _CHECK_TITLES.get(result.governing or "", "—")],
    ]
    _add_table(document, ["项目", "内容"], meta_rows)

    # 1 计算依据
    document.add_heading("1 计算依据", level=1)
    sources: list[str] = []
    for check in result.checks:
        source = _source_text(check, formulas)
        if source and source != "—" and source not in sources:
            sources.append(source)
    if not sources:
        sources = ["（本次计算未引用外部规范条文）"]
    for index, source in enumerate(sources, start=1):
        document.add_paragraph(f"1.{index} {source}", style="List Number")

    # 2 设计参数
    document.add_heading("2 设计参数", level=1)
    if case_payload is None:
        case_payload = result.aux.get("case")
    if case_payload:
        rows = _param_rows(case_payload)
        if rows:
            _add_table(document, ["参数", "取值"], rows)
    else:
        document.add_paragraph("（未提供 case 快照，参数见结果中的 inputs）")

    # 3 计算过程
    document.add_heading("3 计算过程", level=1)
    for index, check in enumerate(result.checks, start=1):
        document.add_heading(f"3.{index} {check.title}", level=2)
        document.add_paragraph(f"公式：{_formula_text(check.formula_id, formulas)}")
        if check.substituted:
            document.add_paragraph(f"代入：{check.substituted}")
        limit_text = "—" if check.limit is None else f"{check.limit:g} {check.unit}"
        document.add_paragraph(
            f"结果：{check.value:g} {check.unit}　　限值：{limit_text}　　"
            f"判定：{_VERDICT_TEXT.get(check.verdict, '—')}"
            + ("" if check.ratio is None else f"（利用率 {check.ratio:.3f}）")
        )
        document.add_paragraph(f"依据：{_source_text(check, formulas)}")
        for note in check.notes:
            document.add_paragraph(f"说明：{note}")

    cap = result.aux.get("capability")
    if cap:
        case = result.aux.get("case") or {}
        document.add_heading("3.3 反查详细计算过程", level=2)

        # 6.1 荷载组成
        payload = float(case.get("payload") or 0.0)
        hook = float(cap.get("hook_mass") or case.get("hook_mass") or 0.0)
        rigging = float(case.get("rigging") or 0.0)
        factor = float(case.get("dynamic_factor") or 1.1)
        rigging_design = rigging * factor
        total = float(cap.get('required', payload + hook + rigging_design))
        document.add_heading("3.3.1 计算荷载的组成", level=3)
        _add_table(
            document,
            ["项目", "计算式", "数值 (t)"],
            [
                ["吊件重量", "G", f"{payload:.3f}"],
                ["吊钩重量", "g_h", f"{hook:.3f}"],
                ["索具重量 × 动载系数", f"g_r × k = {rigging:.3f} × {factor:g}", f"{rigging_design:.3f}"],
                ["计算荷载", "G + g_h + g_r·k", f"{total:.3f}"],
            ],
        )

        points = cap.get("points") or []
        limit = float(cap.get("limit") or 0.9)
        if 'records' in cap:
            document.add_heading('3.3.2 原厂表候选工况', level=3)
            document.add_paragraph(cap['status'] + '：' + cap['explanation'])
            grouped = {}
            for record in cap['records']:
                grouped.setdefault((record['config'], record['boom_len']), []).append(record)
            rows = []
            for (config, boom), records in grouped.items():
                passed = [record for record in records if record['reason'] == '满足']
                last = max((record['radius'] for record in passed), default=None)
                following = next((record for record in records if last is None or record['radius'] > last), None)
                rows.append([config or '默认', f'{boom:g}', '—' if last is None else f'{last:g}',
                             (f"{following['radius']:g} m：{following['reason']}" if following else '本次候选中无更远档')])
            if rows:
                _add_table(document, ['配置', '臂长 (m)', '满足的最大表档 (m)', '下一候选及原因'], rows)
        elif points:
            # 6.2 逐臂扫描
            document.add_heading("3.3.2 逐臂长扫描结果", level=3)
            by_boom: dict[float, list[tuple[float, float]]] = {}
            for boom, radius, rated in points:
                by_boom.setdefault(float(boom), []).append((float(radius), float(rated)))
            rows = []
            for boom in sorted(by_boom):
                series = sorted(by_boom[boom])
                feasible = [(r, q) for r, q in series if total <= q * limit + 1e-9]
                if feasible:
                    best_r, best_q = feasible[-1]
                    after = [(r, q) for r, q in series if r > best_r]
                    if after:
                        next_r, next_q = after[0]
                        why = f"下一档 {next_r:g} m 额定 {next_q:g} t，η = {total / next_q:.2f} > {limit:.0%}，不可用"
                    else:
                        why = "已到该臂长最大幅度"
                    rows.append([f"{boom:g}", f"{len(feasible)}", f"{best_r:g}",
                                 f"{best_q:g}", f"{total / best_q:.3f}", why])
                else:
                    rows.append([f"{boom:g}", "0", "—", "—", "—", "全表超限，该臂长不可用"])
            _add_table(
                document,
                ["臂长 (m)", "可用格点数", "该臂最远幅度 (m)", "该格额定 (t)", "负荷率", "再远一档为什么不行"],
                rows,
            )
            document.add_paragraph(
                "反查取所有臂长中最远的那个可用格点，即为结论中的最远工作幅度。"
            )

        # 6.3 临界格算术
        if cap.get("ok") and cap.get("rated_load"):
            document.add_heading("3.3.3 临界格点的判定算术", level=3)
            rated = float(cap["rated_load"])
            radius = float(cap["max_radius"])
            ratio = total / rated
            _add_table(
                document,
                ["步骤", "计算", "结果"],
                [
                    ["临界格", f"臂长 {float(cap['boom_len']):g} m、幅度 {radius:g} m", f"额定 {rated:g} t"],
                    ["负荷率", f"{total:.3f} ÷ {rated:g}", f"{ratio:.3f}"],
                    ["判据", f"{ratio:.3f} ≤ {limit:.0%}", "按当前假设满足"],
                ],
            )
        elif not cap.get("ok") and cap.get('shortfall_t') is not None:
            document.add_heading("3.3.3 不能吊时的缺口", level=3)
            document.add_paragraph(
                f"全部格点均超限。最有利的一格在幅度 {float(cap.get('closest_radius') or 0):g} m，"
                f"负荷率 {float(cap.get('closest_utilization') or 0):.3f}，"
                f"仍超出上限 {float(cap.get('shortfall_t') or 0):.2f} t。"
            )

        document.add_paragraph(
            "说明：以上结论均取自原厂性能表格点，按原厂说明第 7 条取下一档，未做插值。"
        )

    # 4 结果汇总
    document.add_heading("4 结果汇总", level=1)
    summary_rows = [
        [
            str(index),
            check.title,
            f"{check.value:g}",
            "—" if check.limit is None else f"{check.limit:g}",
            "—" if check.ratio is None else f"{check.ratio:.3f}",
            _VERDICT_TEXT.get(check.verdict, "—"),
        ]
        for index, check in enumerate(result.checks, start=1)
    ]
    _add_table(document, ["序号", "项目", "计算值", "限值", "利用率", "判定"], summary_rows)

    # 5 结论
    document.add_heading("5 结论", level=1)
    if cap and 'status' in cap:
        document.add_paragraph(f"按当前输入及假设：{cap['status']}。{cap['explanation']}。仅供复核，不作为施工依据。")
    elif result.verdict is Verdict.PASS:
        document.add_paragraph(
            f"各项校核均满足要求，最大利用率 {result.utilization:.3f}"
            + (f"，控制项为「{_CHECK_TITLES.get(result.governing, "见结果汇总")}」。" if result.governing else "。")
        )
    elif result.verdict is Verdict.FAIL:
        failed = "、".join(check.title for check in result.checks if check.verdict is Verdict.FAIL)
        document.add_paragraph(f"存在不满足项：{failed}。建议调整几何或降低计算荷载后复算。")
    else:
        document.add_paragraph("本次计算为参数统计，无通过/不通过判定。")

    if result.warnings:
        document.add_heading("7 提示与未覆盖项", level=1)
        for warning in result.warnings:
            document.add_paragraph(warning, style="List Bullet")

    # 附录
    document.add_heading("附录 A 计算输入一览", level=1)
    snapshot = case_payload or {}
    rows: list[list[str]] = []
    mode = (result.aux.get("capability") or {}).get("mode")
    if mode:
        rows.append(["计算方式", "双机抬吊" if mode == "dual" else "单机", ""])
    crane = snapshot.get("crane") or {}
    if crane.get("model"):
        rows.append(["机型", f"{crane.get('brand', '')}　{crane['model']}", ""])
    for label, key, unit in (
        ("吊件重量", "payload", "t"),
        ("吊钩重量", "hook_mass", "t"),
        ("索具重量", "rigging", "t"),
        ("动载系数", "dynamic_factor", ""),
        ("负荷率上限", "limit", ""),
        ("所需起升高度", "required_lift_height", "m"),
        ("主吊承担比例", "left_share", ""),
        ("不同步系数", "asynchronism", ""),
    ):
        if mode != "dual" and key in ("left_share", "asynchronism"):
            continue
        value = snapshot.get(key)
        if value in (None, "", 0, 0.0):
            continue
        rows.append([label, f"{float(value):g}", unit])
    if rows:
        _add_table(document, ["项目", "取值", "单位"], rows)

    footer = document.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run(DISCLAIMER)
    footer_run.font.size = Pt(8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return out_path
