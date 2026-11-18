"""对拍分级测试。"""

from __future__ import annotations

from liftcalc.core.result import ComputationResult, CheckResult, Verdict
from liftcalc.services.calc import run_case
from liftcalc.services.compare import GRADE_BLOCKING, GRADE_PASS, GRADE_UNMATCHED, compare

CASE = {
    "kind": "lifting_eye.check",
    "units": {"length": "mm", "force": "kN", "stress": "MPa"},
    "geometry": {"plate_t": 30, "plate_b": 300, "plate_h": 400, "hole_d": 80, "hole_edge": 120},
    "material": {"grade": "Q355B", "fy": 355},
    "load": {"design": 500, "dynamic_factor": 1.1, "angle_deg": 5},
}


def test_matching_within_one_percent_is_pass() -> None:
    result = run_case(CASE)
    oracle = {
        "source": "吊装助理 v1.1.3.8",
        "checks": [
            {"title": "孔壁承压", "value": result.checks[0].value * 1.004, "verdict": "PASS"},
            {"title": "净截面抗拉", "value": result.checks[1].value, "verdict": "PASS"},
            {"title": "端部抗剪", "value": result.checks[2].value, "verdict": "PASS"},
        ],
    }
    report = compare(result, oracle)
    assert report.worst == GRADE_PASS
    assert report.blocking == 0


def test_verdict_mismatch_is_blocking() -> None:
    result = run_case(CASE)
    oracle = {
        "checks": [
            {"title": "孔壁承压", "value": result.checks[0].value, "verdict": "FAIL"},
            {"title": "净截面抗拉", "value": result.checks[1].value, "verdict": "PASS"},
            {"title": "端部抗剪", "value": result.checks[2].value, "verdict": "PASS"},
        ]
    }
    report = compare(result, oracle)
    assert report.worst == GRADE_BLOCKING
    assert report.blocking == 1


def test_missing_entry_is_unmatched() -> None:
    result = run_case(CASE)
    oracle = {"checks": [{"title": "孔壁承压", "value": result.checks[0].value, "verdict": "PASS"}]}
    report = compare(result, oracle)
    assert any(row.grade == GRADE_UNMATCHED for row in report.rows)
    assert "UNMATCHED" in report.as_markdown(case_name="t")


def test_markdown_contains_table_and_policy() -> None:
    result = ComputationResult(
        kind="demo",
        engine_version="0.1.0",
        checks=[CheckResult(id="a", title="项目A", value=1.0, unit="MPa", verdict=Verdict.PASS)],
    )
    markdown = compare(result, {"checks": [{"title": "项目A", "value": 1.0, "verdict": "PASS"}]}).as_markdown()
    assert "| 项目 |" in markdown
    assert "差异裁决以规范为准" in markdown
