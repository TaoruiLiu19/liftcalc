"""车身轴数示意：吨级 → 轴数，轴距不重叠，图上画的是真圆。"""

from __future__ import annotations

from itertools import pairwise

import pytest

from liftcalc.core.result import ComputationResult
from liftcalc.drawing.body import (
    TRACE_M,
    TRACE_PX,
    WHEEL_R,
    axle_count,
    axle_stations,
    drawing_axles,
)
from liftcalc.drawing.figures import elevation_figure
from liftcalc.drawing.primitives import Circle, Image


@pytest.mark.parametrize(
    ("tonnage", "expected"),
    [(70, 5), (100, 5), (101, 6), (130, 6), (200, 6), (299, 6), (300, 8), (500, 8)],
)
def test_axle_count_by_tonnage(tonnage: float, expected: int) -> None:
    assert axle_count(tonnage) == expected


def test_unknown_tonnage_has_no_axles() -> None:
    assert axle_count(None) is None
    assert axle_count(0) is None
    assert axle_stations(None) == ()


@pytest.mark.parametrize("count", [5, 6, 8])
def test_axle_spacing_keeps_tyres_apart(count: int) -> None:
    stations = axle_stations(count)
    gaps = [right - left for left, right in pairwise(stations)]
    smallest_gap_m = min(gaps) * TRACE_M / TRACE_PX
    assert smallest_gap_m >= 2 * WHEEL_R, f"{count} 轴：最小轴距 {smallest_gap_m:.2f} m 小于轮胎直径"


def test_legacy_result_falls_back_to_catalog() -> None:
    """老结果 JSON 里没有 tonnage_class，按机型回查机型库 CSV。"""
    assert drawing_axles({"model": "QY70K-1", "required": 300}, {}, "徐工") == 5
    assert drawing_axles({"model": "QAY200", "required": 1}, {}, "徐工") == 6
    assert drawing_axles({"model": "未知型号", "required": 500}, {}, "徐工") is None


def _synthetic_result(tonnage: float | None) -> ComputationResult:
    cap = {
        "ok": True,
        "mode": "single",
        "model": "示意机型",
        "tonnage_class": tonnage,
        "required": 10.0,
        "limit": 0.9,
        "max_radius": 10.0,
        "boom_len": 25.98,
        "boom_angle": 67.6,
        "lift_height": 24.43,
        "rated_load": 15.5,
        "utilization": 0.7,
    }
    return ComputationResult(kind="crane.capability", engine_version="test",
                             aux={"capability": cap})


def test_unknown_model_still_draws_a_truck() -> None:
    """吨级查不到时，轴数记为 None，但车身仍按五轴描点画，不留空底盘。"""
    figure = elevation_figure(_synthetic_result(None))
    assert figure is not None
    assert figure.meta["axles"] is None
    outer = [item for item in figure.primitives
             if isinstance(item, Circle)
             and abs(item.r - WHEEL_R * figure.meta["scale"]) < 1e-9]
    assert len({round(item.cx, 6) for item in outer}) == 5


def test_elevation_uses_vector_body_with_expected_axles() -> None:
    figure = elevation_figure(_synthetic_result(70))
    assert figure is not None
    assert figure.meta["axles"] == 5
    assert not any(isinstance(item, Image) for item in figure.primitives)

    outer = [item for item in figure.primitives
             if isinstance(item, Circle)
             and abs(item.r - WHEEL_R * figure.meta["scale"]) < 1e-9]
    assert len({round(item.cx, 6) for item in outer}) == 5
