"""几何体测试：解析解 + 组合形心 + Pappus。"""

from __future__ import annotations

import math

import pytest

from liftcalc.core.errors import NonPositiveDimensionError
from liftcalc.core.tolerance import ANALYTIC_REL_TOL, close
from liftcalc.core.units import Q
from liftcalc.geometry import solids
from liftcalc.geometry.centroid import AssemblyItem, assembly_centroid
from liftcalc.geometry.revolve import pappus_volume


def _v(solid: object) -> float:
    return float(solid.volume.to("m**3").magnitude)  # type: ignore[attr-defined]


def _cz(solid: object) -> float:
    return float(solid.centroid[2].to("m").magnitude)  # type: ignore[attr-defined]


def test_box_volume_and_centroid() -> None:
    solid = solids.box(Q(2, "m"), Q(3, "m"), Q(4, "m"))
    assert close(_v(solid), 24.0, ANALYTIC_REL_TOL)
    assert close(_cz(solid), 2.0, ANALYTIC_REL_TOL)


def test_cylinder() -> None:
    solid = solids.cylinder(Q(2, "m"), Q(5, "m"))
    assert close(_v(solid), math.pi * 1.0**2 * 5, ANALYTIC_REL_TOL)
    assert close(_cz(solid), 2.5, ANALYTIC_REL_TOL)


def test_sphere_volume() -> None:
    solid = solids.sphere(Q(2, "m"))
    assert close(_v(solid), 4 / 3 * math.pi, ANALYTIC_REL_TOL)


def test_hemisphere_centroid() -> None:
    """半球：形心应在 3R/8 处。"""
    solid = solids.spherical_cap(Q(2, "m"), Q(1, "m"))
    assert close(_cz(solid), 3 * 1.0 / 8, ANALYTIC_REL_TOL)


def test_ellipsoid_head_volume_and_centroid() -> None:
    d = 2.0
    solid = solids.ellipsoid_head(Q(d, "m"))
    assert close(_v(solid), math.pi * d**3 / 24, ANALYTIC_REL_TOL)
    assert close(_cz(solid), 3 * d / 32, ANALYTIC_REL_TOL)


def test_cone_frustum_reduces_to_cone() -> None:
    """顶径为 0 时应退化为圆锥，形心在 h/4。"""
    solid = solids.cone_frustum(Q(2, "m"), Q(0.0, "m"), Q(4, "m"))
    assert close(_cz(solid), 1.0, ANALYTIC_REL_TOL)
    assert close(_v(solid), math.pi * 1.0**2 * 4 / 3, ANALYTIC_REL_TOL)


def test_elbow_volume_and_centroid() -> None:
    do, di, radius = 0.2, 0.16, 1.0
    solid = solids.elbow(Q(do, "m"), Q(di, "m"), Q(radius, "m"), 90.0)
    area = math.pi * (do**2 - di**2) / 4
    assert close(_v(solid), area * radius * math.pi / 2, ANALYTIC_REL_TOL)
    expected = radius * math.cos(math.pi / 4)
    assert close(float(solid.centroid[0].to("m").magnitude), expected, ANALYTIC_REL_TOL)


def test_assembly_centroid_two_boxes() -> None:
    """两个等体积立方体上下叠放：形心应在中间。"""
    cube = solids.box(Q(1, "m"), Q(1, "m"), Q(1, "m"))
    items = [
        AssemblyItem(cube, (Q(0, "m"), Q(0, "m"), Q(0, "m"))),
        AssemblyItem(cube, (Q(0, "m"), Q(0, "m"), Q(1, "m"))),
    ]
    result = assembly_centroid(items)
    assert close(float(result.volume.to("m**3").magnitude), 2.0, 1e-12)
    assert close(float(result.centroid[2].to("m").magnitude), 1.0, 1e-12)


def test_assembly_mass_centroid() -> None:
    cube = solids.box(Q(1, "m"), Q(1, "m"), Q(1, "m"))
    items = [
        AssemblyItem(cube, (Q(0, "m"), Q(0, "m"), Q(0, "m")), Q(7850, "kg/m**3")),
        AssemblyItem(cube, (Q(0, "m"), Q(0, "m"), Q(1, "m")), Q(2700, "kg/m**3")),
    ]
    result = assembly_centroid(items)
    assert result.mass is not None
    # 两件形心分别在 0.5 m 与 1.5 m，按质量加权
    expected = (0.5 * 7850 + 1.5 * 2700) / (7850 + 2700)
    assert close(float(result.centroid[2].to("m").magnitude), expected, 1e-12)


def test_pappus_volume_matches_cylinder() -> None:
    """矩形绕轴回转 360° 应得到圆柱。"""
    volume = pappus_volume(Q(0.5, "m**2"), Q(2.0, "m"), 360.0)
    assert close(float(volume.to("m**3").magnitude), 2 * math.pi * 2.0 * 0.5, ANALYTIC_REL_TOL)


def test_negative_dimension_rejected() -> None:
    with pytest.raises(NonPositiveDimensionError):
        solids.box(Q(-1, "m"), Q(1, "m"), Q(1, "m"))
