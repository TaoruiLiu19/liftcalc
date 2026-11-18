"""对拍：以原程序为探针发现差异（设计 §12）。

原则：**原程序用于发现差异，规范用于裁决**。
本模块只负责比对与分级，不做裁决。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from liftcalc.core.result import ComputationResult, Verdict
from liftcalc.core.tolerance import ORACLE_PASS_TOL, ORACLE_WARN_TOL, rel_diff

GRADE_PASS = "PASS"
GRADE_WARN = "WARN"
GRADE_HIGH = "HIGH"
GRADE_BLOCKING = "BLOCKING"
GRADE_UNMATCHED = "UNMATCHED"


@dataclass
class ComparisonRow:
    title: str
    new_value: float | None
    ref_value: float | None
    new_verdict: str
    ref_verdict: str
    diff: float | None
    grade: str
    note: str = ""


@dataclass
class ComparisonReport:
    rows: list[ComparisonRow] = field(default_factory=list)

    @property
    def worst(self) -> str:
        order = [GRADE_BLOCKING, GRADE_HIGH, GRADE_UNMATCHED, GRADE_WARN, GRADE_PASS]
        for grade in order:
            if any(row.grade == grade for row in self.rows):
                return grade
        return GRADE_PASS

    @property
    def blocking(self) -> int:
        return sum(1 for row in self.rows if row.grade == GRADE_BLOCKING)

    def as_markdown(self, *, case_name: str = "", source: str = "") -> str:
        lines: list[str] = []
        lines.append(f"# 对拍报告 {case_name}".strip())
        lines.append("")
        if source:
            lines.append(f"- 基准来源：{source}")
        lines.append(f"- 总体结论：**{self.worst}**")
        lines.append(f"- 阻断项：{self.blocking}")
        lines.append("")
        lines.append("| 项目 | 新内核 | 原程序 | 相对偏差 | 判定 | 分级 |")
        lines.append("|---|---:|---:|---:|---|---|")
        for row in self.rows:
            new_value = "—" if row.new_value is None else f"{row.new_value:g}"
            ref_value = "—" if row.ref_value is None else f"{row.ref_value:g}"
            diff = "—" if row.diff is None else f"{row.diff * 100:.2f}%"
            lines.append(
                f"| {row.title} | {new_value} | {ref_value} | {diff} | "
                f"{row.new_verdict}/{row.ref_verdict} | {row.grade} |"
            )
        if any(row.note for row in self.rows):
            lines.append("")
            lines.append("## 备注")
            for row in self.rows:
                if row.note:
                    lines.append(f"- {row.title}：{row.note}")
        lines.append("")
        lines.append(
            f"> 分级口径：verdict 不一致 = BLOCKING；偏差 > {ORACLE_WARN_TOL:.0%} = HIGH；"
            f"> {ORACLE_PASS_TOL:.0%} = WARN；其余 PASS。差异裁决以规范为准。"
        )
        return "\n".join(lines)


def _normalize_title(text: str) -> str:
    return text.replace(" ", "").replace("　", "").strip()


def compare(result: ComputationResult, oracle: dict[str, Any]) -> ComparisonReport:
    entries = oracle.get("checks") or []
    by_title = {_normalize_title(str(item.get("title", ""))): item for item in entries}
    report = ComparisonReport()

    for check in result.checks:
        key = _normalize_title(check.title)
        entry = by_title.pop(key, None)
        if entry is None:
            report.rows.append(
                ComparisonRow(
                    title=check.title,
                    new_value=check.value,
                    ref_value=None,
                    new_verdict=check.verdict.value,
                    ref_verdict="—",
                    diff=None,
                    grade=GRADE_UNMATCHED,
                    note="原程序结果中未找到同名项，需人工确认对应关系",
                )
            )
            continue

        ref_value = entry.get("value")
        ref_verdict = str(entry.get("verdict") or "—")
        diff = None if ref_value is None else rel_diff(check.value, float(ref_value))

        if ref_verdict in {Verdict.PASS.value, Verdict.FAIL.value} and ref_verdict != check.verdict.value:
            grade = GRADE_BLOCKING
        elif diff is None:
            grade = GRADE_WARN
        elif diff > ORACLE_WARN_TOL:
            grade = GRADE_HIGH
        elif diff > ORACLE_PASS_TOL:
            grade = GRADE_WARN
        else:
            grade = GRADE_PASS

        report.rows.append(
            ComparisonRow(
                title=check.title,
                new_value=check.value,
                ref_value=None if ref_value is None else float(ref_value),
                new_verdict=check.verdict.value,
                ref_verdict=ref_verdict,
                diff=diff,
                grade=grade,
            )
        )

    for title, entry in by_title.items():
        report.rows.append(
            ComparisonRow(
                title=title,
                new_value=None,
                ref_value=None if entry.get("value") is None else float(entry["value"]),
                new_verdict="—",
                ref_verdict=str(entry.get("verdict") or "—"),
                diff=None,
                grade=GRADE_UNMATCHED,
                note="新内核未产出该项",
            )
        )
    return report
