"""反查的边界与配置选择。"""

from __future__ import annotations

from pathlib import Path

import pytest

from liftcalc.core.errors import LiftcalcError
from liftcalc.core.result import Verdict
from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.services.calc import run_case

PACK = Path(__file__).resolve().parents[1] / "src" / "liftcalc" / "data" / "pack"


def test_requested_height_and_radius_use_the_same_chart_cell():
    from liftcalc.crane.capability import Point, assess_single

    points = [
        Point(20, 8, 14, lift_height=15, config="A"),
        Point(20, 10, 13, lift_height=12, config="A"),
        Point(30, 10, 14, lift_height=24, config="B"),
    ]
    conditions = dict(required=10, limit=.9, height=14, radius=None, config="A", hook_known=True)
    best, rows, status, _ = assess_single(points, **conditions)
    assert status == "满足" and best.max_radius == 8
    assert [row["reason"] for row in rows] == ["满足", "钩高不足"]
    assert assess_single(points, **{**conditions, "radius": 9})[2] == "资料不足"
    assert assess_single(points, **{**conditions, "hook_known": False})[2] == "资料不足"
    best, _, status, _ = assess_single(points, **{**conditions, "radius": 9, "height": None})
    assert status == "满足" and best.max_radius == 10


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Repo:
    path = tmp_path_factory.mktemp("db2") / "calc.sqlite"
    build_db(PACK, path, "test")
    return Repo(path)


def _case(model: str, **overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "kind": "crane.capability",
        "mode": "single",
        "payload": 10.0,
        "crane": {"brand": "徐工", "model": model},
    }
    case.update(overrides)
    return case


def test_model_without_table_is_refused(repo: Repo) -> None:
    """未录入性能表的机型必须明确报错，不能返回半截答案。
    QAY300 已有表，改用库中不存在的 QAY999。"""
    with pytest.raises(LiftcalcError):
        run_case(_case("QAY999"), repo)


def test_full_counterweight_chart_cells_keep_units_and_extension_codes(repo: Repo) -> None:
    def cells(model, boom, radius):
        return {row["config_name"]: row["rated_load"] for row in repo.model_capacity("徐工", model)
                if row["boom_len"] == boom and row["radius"] == radius}

    assert cells("XCT25L5_Y", 40.5, 32) == {
        "全配重5.8t·支腿全伸5.23×6.4m·第五支腿支好·360°·主臂40.5m": 0.6,
    }
    assert cells("XCT60_Y", 44, 32) == {
        "全配重6.5t·支腿全伸6.1×7.1m·第五支腿支好·360°·主臂44m": 1.1,
    }
    prefix = "全配重45t·支腿全伸8.45×7.9m·360°·伸缩码"
    assert cells("XCT100_1", 18.3, 3) == {
        f"{prefix}00100·主臂18.3m": 100.0,
        f"{prefix}00010·主臂18.3m": 98.0,
        f"{prefix}00001·主臂18.3m": 70.3,
    }


@pytest.mark.parametrize(("model", "boom", "radius", "expected"), [
    ("STC500", 19.38, 3, [21.5, 32.0]),
    ("STC550C5", 45, 34, [0.9]),
    ("STC550C5", 45, 36, []),
    ("STC750", 11.8, 6, [43.0]),
    ("STC750", 20.1, 6, [20.0, 33.1]),
    ("STC1100T7", 13.9, 3, []),
    ("STC1100T7", 73.2, 64, [1.1]),
    ("STC1200T7", 12.9, 2.5, []),
    ("STC1200T7", 21.5, 3, [72.0]),
    ("STC1600T7", 75.5, 64, [1.7, 2.0]),
    ("STC2000C8-8", 15.1, 3.5, [150.0]),
    ("STC2000C8-8", 59.4, 16, []),
    ("STC2400C8PHEV", 15.1, 3, [240.0]),
    ("STC3000C8-8", 15.1, 2.5, []),
    ("STC3000C8-8", 25.1, 5, [124.8]),
    ("STC3000C8-8", 40, 6.5, []),
])
def test_sany_full_counterweight_chart(repo, model, boom, radius, expected):
    cells = {row["config_name"]: row["rated_load"]
             for row in repo.model_capacity("三一", model)
             if row["boom_len"] == boom and row["radius"] == radius}
    assert sorted(cells.values()) == expected


@pytest.mark.parametrize(("brand", "model"), [
    ("三一", None), (None, "STC750"), ("徐工", "XCT100_1"), ("徐工", "STC750"),
])
def test_main_hook_filters_are_independent(repo: Repo, brand: str | None, model: str | None) -> None:
    all_hooks = repo.main_hooks()
    assert {row["brand"] for row in all_hooks} >= {"三一", "徐工"}
    expected = [row for row in all_hooks if (brand is None or row["brand"] == brand)
                and (model is None or row["model"] == model)]
    assert repo.main_hooks(brand=brand, model=model) == expected


def test_main_hook_options_follow_model_and_limit_suspended_load(repo: Repo) -> None:
    crane = {"brand": "三一", "model": "STC2000C8-8"}
    case = {"kind": "crane.capability", "crane": crane, "payload": 10}
    cap = run_case(case, repo).aux["capability"]
    assert cap["ok"] and cap["hook_from_db"]
    assert (cap["hook_mass"], cap["hook_rated_t"]) == (.735, 75)
    assert cap["hook_source_ref"].endswith("#page=4")
    overloaded = run_case({**case, "payload": 74, "rigging": 1}, repo).aux["capability"]
    assert overloaded["status"] == "不满足" and "主钩额载" in overloaded["explanation"]

    case["crane"] = {"brand": "三一", "model": "STC750"}
    assert run_case(case, repo).aux["capability"]["status"] == "资料不足"
    selected = run_case({**case, "hook_mass": .320}, repo).aux["capability"]
    assert selected["ok"] and selected["hook_rated_t"] == 30
    assert selected["required"] == pytest.approx(10.320)
    manual = run_case({**case, "hook_mass": .735}, repo).aux["capability"]
    assert manual["ok"] and manual["hook_rated_t"] is None


def test_four_models_ranking(repo: Repo) -> None:
    """吨位越大，10 t 货能吊得越远。"""
    radii = {}
    for model in ("QY70K-1", "QY100H-3", "QY130H-1", "QAY200"):
        result = run_case(_case(model, hook_mass=1.0), repo)
        radii[model] = result.aux["capability"]["max_radius"]
    assert radii["QY70K-1"] < radii["QY100H-3"] < radii["QY130H-1"] < radii["QAY200"]


def test_counterweight_config_is_reported(repo: Repo) -> None:
    """同一机型有多个配重时，结论要说明用的是哪一套。"""
    result = run_case(_case("QY130H-1", hook_mass=1.0), repo)
    config = result.aux["capability"]["config"]
    assert config is not None
    assert "配重" in config


def test_heavy_load_is_narrower(repo: Repo) -> None:
    """同一台车，货越重，最远幅度越小。"""
    light = run_case(_case("QY70K-1", payload=10.0), repo).aux["capability"]["max_radius"]
    heavy = run_case(_case("QY70K-1", payload=30.0), repo).aux["capability"]["max_radius"]
    assert heavy < light


def test_overload_reports_shortfall(repo: Repo) -> None:
    """超出全表能力时，要给出最接近的格点和缺口，而不是只说不行。"""
    result = run_case(_case("QY70K-1", payload=80.0), repo)
    assert result.verdict is Verdict.FAIL
    cap = result.aux["capability"]
    assert cap["ok"] is False
    assert cap["shortfall_t"] > 0


def test_dual_asynchronism_increases_demand(repo: Repo) -> None:
    """计入不同步系数后，每台的计算荷载要变大。"""
    base = dict(mode="dual", crane={"brand": "徐工", "model": "QY70K-1"},
                second={"brand": "徐工", "model": "QY70K-1"})
    plain = run_case(_case("QY70K-1", **base), repo).aux["capability"]
    with_k = run_case(_case("QY70K-1", **base, asynchronism=1.2), repo).aux["capability"]
    assert with_k["left"]["required"] > plain["left"]["required"]
    assert with_k["left"]["required"] == pytest.approx(plain["left"]["required"] * 1.2, rel=1e-9)

def test_missing_hook_defaults_from_model(repo: Repo) -> None:
    """没给吊钩重量时，必须自动取机型库的主钩自重，不能当 0 处理。"""
    result = run_case(
        {"kind": "crane.capability", "mode": "single", "payload": 10.0,
         "crane": {"brand": "徐工", "model": "QAY200"}},
        repo,
    )
    cap = result.aux["capability"]
    assert cap["hook_from_db"] is True
    assert cap["hook_mass"] == pytest.approx(2.41)
    assert any("吊钩" in w for w in result.warnings)
    # 计入 2.41 t 钩重后，最远幅度应小于按 0 钩重算出的值
    light = run_case(
        {"kind": "crane.capability", "mode": "single", "payload": 10.0,
         "hook_mass": 0.001, "crane": {"brand": "徐工", "model": "QAY200"}},
        repo,
    ).aux["capability"]["max_radius"]
    assert cap["max_radius"] < light
