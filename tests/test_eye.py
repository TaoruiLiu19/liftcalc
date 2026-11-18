"""吊耳校核测试：手算样例 + 判定逻辑 + 定义域错误。"""

from __future__ import annotations

import pytest

from liftcalc.core.errors import InfeasibleSectionError
from liftcalc.core.result import Verdict
from liftcalc.core.tolerance import NUMERIC_REL_TOL, close
from liftcalc.core.units import Q
from liftcalc.lifting.eye import EyeGeometry, EyeLoad, EyeWeld, check_eye

FY = Q(355, "MPa")  # 设计强度 = 355 / 1.1 = 322.727 MPa


def _base_geometry() -> EyeGeometry:
    return EyeGeometry(
        plate_t=Q(30, "mm"),
        plate_b=Q(300, "mm"),
        plate_h=Q(400, "mm"),
        hole_d=Q(80, "mm"),
        hole_edge=Q(120, "mm"),
    )


def _by_id(outcome: object) -> dict[str, object]:
    return {check.id: check for check in outcome.checks}  # type: ignore[attr-defined]


def test_hand_calculation_three_checks() -> None:
    outcome = check_eye(geometry=_base_geometry(), load=EyeLoad(design=Q(500, "kN"), dynamic_factor=1.1), fy=FY)
    checks = _by_id(outcome)
    assert set(checks) == {"eye.hole_bearing", "eye.net_tension", "eye.end_shear"}

    # N_eff = 550 kN = 550 000 N
    assert close(checks["eye.hole_bearing"].value, 550_000 / (80 * 30), NUMERIC_REL_TOL)  # type: ignore[attr-defined]
    assert close(checks["eye.net_tension"].value, 550_000 / ((300 - 80) * 30), NUMERIC_REL_TOL)  # type: ignore[attr-defined]
    assert close(checks["eye.end_shear"].value, 550_000 / (2 * 120 * 30), NUMERIC_REL_TOL)  # type: ignore[attr-defined]


def test_all_pass_for_comfortable_design() -> None:
    outcome = check_eye(geometry=_base_geometry(), load=EyeLoad(design=Q(500, "kN"), dynamic_factor=1.1), fy=FY)
    assert all(check.verdict is Verdict.PASS for check in outcome.checks)


def test_overload_fails_and_governing_is_bearing() -> None:
    outcome = check_eye(geometry=_base_geometry(), load=EyeLoad(design=Q(1200, "kN"), dynamic_factor=1.1), fy=FY)
    verdicts = {check.id: check.verdict for check in outcome.checks}
    assert Verdict.FAIL in verdicts.values()
    bearing = next(check for check in outcome.checks if check.id == "eye.hole_bearing")
    assert bearing.ratio is not None and bearing.ratio > 1.0


def test_weld_and_pin_checks_added() -> None:
    outcome = check_eye(
        geometry=_base_geometry(),
        load=EyeLoad(design=Q(500, "kN"), dynamic_factor=1.1),
        fy=FY,
        weld=EyeWeld(leg=Q(12, "mm"), length=Q(600, "mm"), electrode="E43"),
        pin_diameter=Q(90, "mm"),
    )
    ids = {check.id for check in outcome.checks}
    assert {"eye.fillet_weld", "pin.shear", "pin.bending"} <= ids


def test_pin_shear_uses_double_shear() -> None:
    outcome = check_eye(
        geometry=_base_geometry(),
        load=EyeLoad(design=Q(500, "kN"), dynamic_factor=1.1),
        fy=FY,
        pin_diameter=Q(90, "mm"),
    )
    pin = next(check for check in outcome.checks if check.id == "pin.shear")
    expected = (550_000 / 2) / (3.141592653589793 * 90**2 / 4)
    assert close(pin.value, expected, 1e-6)


def test_warning_when_angle_exceeds_10_degrees() -> None:
    outcome = check_eye(
        geometry=_base_geometry(),
        load=EyeLoad(design=Q(500, "kN"), dynamic_factor=1.1, angle_deg=20.0),
        fy=FY,
    )
    assert any("平面外" in warning for warning in outcome.warnings)


def test_plate_too_narrow_raises() -> None:
    geometry = EyeGeometry(
        plate_t=Q(30, "mm"),
        plate_b=Q(70, "mm"),
        plate_h=Q(400, "mm"),
        hole_d=Q(80, "mm"),
        hole_edge=Q(120, "mm"),
    )
    with pytest.raises(InfeasibleSectionError):
        check_eye(geometry=geometry, load=EyeLoad(design=Q(500, "kN")), fy=FY)


def test_edge_distance_too_small_raises() -> None:
    geometry = EyeGeometry(
        plate_t=Q(30, "mm"),
        plate_b=Q(300, "mm"),
        plate_h=Q(400, "mm"),
        hole_d=Q(80, "mm"),
        hole_edge=Q(30, "mm"),
    )
    with pytest.raises(InfeasibleSectionError):
        check_eye(geometry=geometry, load=EyeLoad(design=Q(500, "kN")), fy=FY)


def test_limits_are_marked_provisional() -> None:
    """限值尚未核定时必须留下痕迹（设计 §17-R2）。"""
    outcome = check_eye(geometry=_base_geometry(), load=EyeLoad(design=Q(500, "kN")), fy=FY)
    assert any("占位系数" in note for check in outcome.checks for note in check.notes)
