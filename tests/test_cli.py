"""端到端：case → calc → report → draw。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from liftcalc.cli.main import app

PACK = Path(__file__).resolve().parents[1] / "src" / "liftcalc" / "data" / "pack"
runner = CliRunner()

EYE_CASE = {
    "kind": "lifting_eye.check",
    "units": {"length": "mm", "force": "kN", "stress": "MPa"},
    "meta": {"project": "示例工程", "part": "顶部吊耳", "author": "self", "date": "2026-11-18"},
    "geometry": {"plate_t": 30, "plate_b": 300, "plate_h": 400, "hole_d": 80, "hole_edge": 120},
    "material": {"grade": "Q355B", "fy": 355},
    "load": {"design": 500, "dynamic_factor": 1.1, "angle_deg": 5},
    "weld": {"leg": 12, "length": 600, "electrode": "E43"},
    "pin": {"diameter": 90},
}


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(EYE_CASE, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_calc_writes_result(workdir: Path) -> None:
    result_path = workdir / "result.json"
    outcome = runner.invoke(app, ["calc", "--in", str(workdir / "case.json"), "--out", str(result_path)])
    assert outcome.exit_code == 0, outcome.stdout
    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["verdict"] == "PASS"
    assert len(data["checks"]) == 6


def test_fail_verdict_exits_one(workdir: Path) -> None:
    overloaded = dict(EYE_CASE)
    overloaded["load"] = {"design": 2000, "dynamic_factor": 1.1, "angle_deg": 5}
    case_path = workdir / "over.json"
    case_path.write_text(json.dumps(overloaded, ensure_ascii=False), encoding="utf-8")
    outcome = runner.invoke(app, ["calc", "--in", str(case_path), "--out", str(workdir / "over_result.json")])
    assert outcome.exit_code == 1


def test_report_and_draw(workdir: Path) -> None:
    result_path = workdir / "result.json"
    runner.invoke(app, ["calc", "--in", str(workdir / "case.json"), "--out", str(result_path)])

    docx_path = workdir / "计算书.docx"
    outcome = runner.invoke(
        app,
        [
            "report",
            "--in", str(result_path),
            "--out", str(docx_path),
            "--case", str(workdir / "case.json"),
        ],
    )
    assert outcome.exit_code == 0, outcome.stdout
    assert docx_path.exists() and docx_path.stat().st_size > 5000

    svg_path = workdir / "eye.svg"
    outcome = runner.invoke(app, ["draw", "--in", str(result_path), "--out", str(svg_path), "--format", "svg"])
    assert outcome.exit_code == 0, outcome.stdout
    text = svg_path.read_text(encoding="utf-8")
    assert "<svg" in text and "不按比例" in text

    dxf_path = workdir / "eye.dxf"
    outcome = runner.invoke(app, ["draw", "--in", str(result_path), "--out", str(dxf_path), "--format", "dxf"])
    assert outcome.exit_code == 0, outcome.stdout
    assert dxf_path.exists() and dxf_path.stat().st_size > 1000


def test_data_build_validate_and_schema(tmp_path: Path) -> None:
    db = tmp_path / "calc.sqlite"
    outcome = runner.invoke(app, ["data", "build", "--pack", str(PACK), "--out", str(db)])
    assert outcome.exit_code == 0, outcome.stdout
    assert db.exists()

    outcome = runner.invoke(app, ["data", "validate", "--db", str(db)])
    assert outcome.exit_code == 0, outcome.stdout

    schema_dir = tmp_path / "schemas"
    outcome = runner.invoke(app, ["schema", "--out", str(schema_dir)])
    assert outcome.exit_code == 0, outcome.stdout
    assert len(list(schema_dir.glob("*.schema.json"))) == 8


def test_steel_section_needs_database(tmp_path: Path) -> None:
    case = {
        "kind": "section.props",
        "units": {"length": "mm"},
        "section": {"type": "steel", "family": "H", "designation": "DEMO-HW300x300"},
    }
    case_path = tmp_path / "steel.json"
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    outcome = runner.invoke(app, ["calc", "--in", str(case_path)])
    assert outcome.exit_code in (3, 4, 5)
    assert "数据库" in (outcome.stderr or outcome.stdout)


def test_selftest_runs(tmp_path: Path) -> None:
    outcome = runner.invoke(app, ["selftest"])
    assert outcome.exit_code == 0
    payload = json.loads(outcome.stdout.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["checks"] == 3
