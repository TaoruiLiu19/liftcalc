"""能力反查端到端：单机 / 双机 / 制图。"""

from __future__ import annotations

from pathlib import Path

import pytest

from liftcalc.core.result import Verdict
from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.drawing.figures import figures_for
from liftcalc.services.calc import run_case

PACK = Path(__file__).resolve().parents[1] / "src" / "liftcalc" / "data" / "pack"


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Repo:
    path = tmp_path_factory.mktemp("db") / "calc.sqlite"
    build_db(PACK, path, "test")
    return Repo(path)


def _single(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "kind": "crane.capability",
        "mode": "single",
        "payload": 10.0,
        "hook_mass": 0.616,
        "rigging": 0.3,
        "dynamic_factor": 1.1,
        "crane": {"brand": "徐工", "model": "QY70K-1"},
    }
    case.update(overrides)
    return case


def test_single_reverse_lookup(repo: Repo) -> None:
    result = run_case(_single(), repo)
    assert result.verdict is Verdict.PASS
    cap = result.aux["capability"]
    assert cap["max_radius"] == 10.0
    assert cap["boom_len"] == 25.98
    assert cap["lift_height"] == 24.43
    assert abs(float(cap["utilization"]) - 0.706, ) < 0.01


def test_single_fails_with_shortfall(repo: Repo) -> None:
    result = run_case(_single(payload=65.0), repo)
    assert result.verdict is Verdict.FAIL
    cap = result.aux["capability"]
    assert cap["ok"] is False
    assert cap["shortfall_t"] and cap["shortfall_t"] > 0


def test_dual_mode_both_sides(repo: Repo) -> None:
    result = run_case(
        _single(
            mode="dual",
            crane={"brand": "徐工", "model": "QY70K-1"},
            second={"brand": "徐工", "model": "QY70K-1"},
            left_share=0.6,
            asynchronism=1.1,
        ),
        repo,
    )
    cap = result.aux["capability"]
    assert cap["mode"] == "dual"
    assert cap["left"]["required"] > cap["right"]["required"]
    assert result.verdict is Verdict.PASS


def test_dual_default_limit_is_eighty_percent(repo: Repo) -> None:
    result = run_case(
        _single(
            mode="dual",
            crane={"brand": "徐工", "model": "QY70K-1"},
            second={"brand": "徐工", "model": "QY70K-1"},
        ),
        repo,
    )
    assert result.aux["capability"]["limit"] == 0.8


def test_lift_height_check(repo: Repo) -> None:
    ok = run_case(_single(required_lift_height=20.0), repo)
    assert any(check.id == "capability.lift_height" for check in ok.checks)
    bad = run_case(_single(required_lift_height=40.0), repo)
    assert bad.verdict is Verdict.FAIL


def test_figures_generated(repo: Repo) -> None:
    result = run_case(_single(), repo)
    figures = figures_for(result)
    titles = [figure.title for figure in figures]
    assert "幅度—起重量能力曲线" in titles
    assert "吊装立面图" in titles
