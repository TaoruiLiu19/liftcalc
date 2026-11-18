"""截面特性测试：解析解 + 型钢构造 + 组合。"""

from __future__ import annotations

import math

import pytest

from liftcalc.core.errors import NonPositiveAreaError
from liftcalc.core.tolerance import ANALYTIC_REL_TOL, close
from liftcalc.core.units import Q
from liftcalc.sections import custom
from liftcalc.sections.props import section_from_polygons
from liftcalc.sections.steel import composite


def _mm2(props: object) -> float:
    return float(props.area.to("mm**2").magnitude)  # type: ignore[attr-defined]


def _ix(props: object) -> float:
    return float(props.ix.to("mm**4").magnitude)  # type: ignore[attr-defined]


def _iy(props: object) -> float:
    return float(props.iy.to("mm**4").magnitude)  # type: ignore[attr-defined]


def test_rect_matches_analytic() -> None:
    b, h = 300.0, 500.0
    props = custom.rect(Q(b, "mm"), Q(h, "mm"))
    assert close(_mm2(props), b * h, ANALYTIC_REL_TOL)
    assert close(_ix(props), b * h**3 / 12, ANALYTIC_REL_TOL)
    assert close(_iy(props), h * b**3 / 12, ANALYTIC_REL_TOL)


def test_box_matches_analytic() -> None:
    outer_b, outer_h, t = 300.0, 500.0, 12.0
    props = custom.box(Q(outer_b, "mm"), Q(outer_h, "mm"), Q(t, "mm"))
    inner_b, inner_h = outer_b - 2 * t, outer_h - 2 * t
    expected_area = outer_b * outer_h - inner_b * inner_h
    expected_ix = (outer_b * outer_h**3 - inner_b * inner_h**3) / 12
    assert close(_mm2(props), expected_area, ANALYTIC_REL_TOL)
    assert close(_ix(props), expected_ix, ANALYTIC_REL_TOL)


def test_pipe_matches_analytic() -> None:
    do, di = 219.0, 207.0
    props = custom.pipe(Q(do, "mm"), Q(di, "mm"))
    assert close(_mm2(props), math.pi * (do**2 - di**2) / 4, ANALYTIC_REL_TOL)
    assert close(_ix(props), math.pi * (do**4 - di**4) / 64, ANALYTIC_REL_TOL)


def test_round_bar_radius_of_gyration() -> None:
    d = 80.0
    props = custom.round_bar(Q(d, "mm"))
    assert close(float(props.rx.to("mm").magnitude), d / 4, 1e-12)


def test_i_section_area_by_hand() -> None:
    """工字形面积手算：2·b·tf + (h − 2tf)·tw。"""
    h, b, tw, tf = 300.0, 300.0, 10.0, 15.0
    props = custom.i_section(Q(h, "mm"), Q(b, "mm"), Q(tw, "mm"), Q(tf, "mm"))
    assert close(_mm2(props), 2 * b * tf + (h - 2 * tf) * tw, ANALYTIC_REL_TOL)


def test_symmetric_section_has_zero_principal_angle() -> None:
    props = custom.rect(Q(200, "mm"), Q(400, "mm"))
    assert abs(props.principal_angle_deg) < 1e-9
    assert props.i1 >= props.i2


def test_section_modulus_of_rect() -> None:
    b, h = 200.0, 400.0
    props = custom.rect(Q(b, "mm"), Q(h, "mm"))
    assert close(float(props.wx.to("mm**3").magnitude), b * h**2 / 6, ANALYTIC_REL_TOL)


def test_parallel_axis_two_rects() -> None:
    """两块相同矩形并排：Iy 应为单块的两倍加平移项。"""
    single = custom.rect(Q(100, "mm"), Q(200, "mm"))
    d = Q(100, "mm")  # 形心相距 100mm
    combined = composite([(single, Q(0, "mm"), Q(0, "mm")), (single, d, Q(0, "mm"))])
    offset = 50.0
    expected_iy = 2 * (_iy(single) + _mm2(single) * offset**2)
    assert close(_iy(combined), expected_iy, 1e-9)


def test_composite_centroid_shifts() -> None:
    single = custom.rect(Q(100, "mm"), Q(100, "mm"))
    combined = composite([(single, Q(0, "mm"), Q(0, "mm")), (single, Q(200, "mm"), Q(0, "mm"))])
    assert close(float(combined.cx.to("mm").magnitude), 100.0, 1e-9)


def test_polygon_with_hole_matches_subtraction() -> None:
    # 注意：section_from_polygons 的坐标单位是米
    outer = [(-0.05, -0.05), (0.05, -0.05), (0.05, 0.05), (-0.05, 0.05)]
    hole = [(-0.02, -0.02), (0.02, -0.02), (0.02, 0.02), (-0.02, 0.02)]
    props = section_from_polygons([outer], [hole])
    # 0.1×0.1 米 − 0.04×0.04 米 = 8400 mm²
    assert close(float(props.area.to("mm**2").magnitude), 8400.0, 1e-12)


def test_degenerate_polygon_raises() -> None:
    with pytest.raises(NonPositiveAreaError):
        section_from_polygons([[(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)]])
