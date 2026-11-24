"""车身轴数：机型库真实轴数（厂商规格书提取），轴距不重叠，图上画的是真圆。"""

from __future__ import annotations

from itertools import pairwise

import pytest

from liftcalc.core.result import ComputationResult
from liftcalc.drawing.body import (
    TRACE_M,
    TRACE_PX,
    WHEEL_R,
    axle_stations,
    drawing_axles,
)
from liftcalc.drawing.figures import elevation_figure
from liftcalc.drawing.primitives import Circle, Image


@pytest.mark.parametrize(
    ("model", "brand", "expected"),
    [
        ("QY70K-1", "徐工", 4),
        ("QY100H-3", "徐工", 6),
        ("QY130H-1", "徐工", 6),
        ("QAY200", "徐工", 6),
        ("XCT25L5_Y", "徐工", 3),
        ("XCT60_Y", "徐工", 4),
        ("XCT100_1", "徐工", 5),
        ("STC500", "三一", 4),
        ("STC750", "三一", 4),
        ("STC1100T7", "三一", 5),
        ("STC1200T7", "三一", 4),
        ("STC1600T7", "三一", 5),
        ("STC2000C8-8", "三一", 5),
        ("STC2400C8PHEV", "三一", 5),
        ("STC3000C8-8", "三一", 5),
    ],
)
def test_real_axles_from_catalog(model: str, brand: str, expected: int) -> None:
    """机型库 axles 列是厂商规格书提取的真实轴数，不按吨级推算。"""
    assert drawing_axles({"model": model, "required": 1}, {}, brand) == expected


def test_unknown_model_has_no_axles() -> None:
    assert drawing_axles({"model": "未知型号", "required": 500}, {}, "徐工") is None
    assert drawing_axles({}, {}, "") is None
    assert axle_stations(None) == ()


def test_result_axles_field_takes_priority() -> None:
    """结果/机型信息里显式给出的 axles 优先于机型库。"""
    assert drawing_axles({"model": "QY70K-1", "axles": 7}, {}, "徐工") == 7
    assert drawing_axles({"model": "未知机型"}, {"model": "未知机型", "axles": 3}, "") == 3


@pytest.mark.parametrize("count", [3, 4, 5, 6, 7, 8])
def test_axle_spacing_keeps_tyres_apart(count: int) -> None:
    stations = axle_stations(count)
    gaps = [right - left for left, right in pairwise(stations)]
    smallest_gap_m = min(gaps) * TRACE_M / TRACE_PX
    assert smallest_gap_m >= 2 * WHEEL_R, f"{count} 轴：最小轴距 {smallest_gap_m:.2f} m 小于轮胎直径"


def test_legacy_result_falls_back_to_catalog() -> None:
    """老结果 JSON 里没有 axles 字段，按机型回查机型库 CSV 的真实轴数。"""
    assert drawing_axles({"model": "QY70K-1", "required": 300}, {}, "徐工") == 4
    assert drawing_axles({"model": "QAY200", "required": 1}, {}, "徐工") == 6
    assert drawing_axles({"model": "未知型号", "required": 500}, {}, "徐工") is None


def _synthetic_result(axles: int | None) -> ComputationResult:
    cap = {
        "ok": True,
        "mode": "single",
        "model": "示意机型",
        "axles": axles,
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
    """查不到真实轴数时记为 None，但车身仍按五轴示意描点，不留空底盘。"""
    figure = elevation_figure(_synthetic_result(None))
    assert figure is not None
    assert figure.meta["axles"] is None
    outer = [item for item in figure.primitives
             if isinstance(item, Circle)
             and abs(item.r - WHEEL_R * figure.meta["scale"]) < 1e-9]
    assert len({round(item.cx, 6) for item in outer}) == 5


def test_elevation_uses_vector_body_with_expected_axles() -> None:
    figure = elevation_figure(_synthetic_result(4))
    assert figure is not None
    assert figure.meta["axles"] == 4
    assert not any(isinstance(item, Image) for item in figure.primitives)

    outer = [item for item in figure.primitives
             if isinstance(item, Circle)
             and abs(item.r - WHEEL_R * figure.meta["scale"]) < 1e-9]
    assert len({round(item.cx, 6) for item in outer}) == 4
