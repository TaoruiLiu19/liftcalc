"""能力反查测试：能吊/不能吊、最远幅度、双机上限。"""

from __future__ import annotations

import pytest

from liftcalc.core.errors import InfeasibleSectionError, OutOfTableError
from liftcalc.core.tolerance import close
from liftcalc.crane.capability import (
    Point,
    find_capability,
    find_dual,
    required_load,
    split_by_ratio,
)

# 简化表：两个臂长
POINTS = [
    Point(11.6, 3.0, 70.0, 71.5, 11.81),
    Point(11.6, 6.0, 38.5, 54.1, 9.94),
    Point(11.6, 9.0, 17.8, 29.8, 5.93),
    Point(25.98, 5.0, 27.6, 79.4, 26.31),
    Point(25.98, 10.0, 15.5, 67.6, 24.43),
    Point(25.98, 14.0, 7.8, 57.2, 21.96),
]


def test_required_load_includes_hook_and_dynamic() -> None:
    assert close(required_load(payload=10, hook_mass=0.616, rigging=0.3, dynamic_factor=1.1), 10.946, 1e-12)


def test_finds_farthest_radius() -> None:
    verdict = find_capability(POINTS, required=10.946, ratio_limit=0.9)
    assert verdict.ok is True
    assert verdict.max_radius == 10.0  # 14 m 处只有 7.8 t，不够
    assert verdict.rated_load == 15.5
    assert verdict.boom_len == 25.98


def test_fails_when_nothing_meets_limit() -> None:
    verdict = find_capability(POINTS, required=65.0, ratio_limit=0.9)
    assert verdict.ok is False
    assert verdict.max_radius is None
    assert verdict.closest_radius == 3.0
    assert verdict.shortfall_t is not None and verdict.shortfall_t > 0


def test_dual_uses_eighty_percent() -> None:
    left, right = find_dual(POINTS, POINTS, required_left=20.0, required_right=20.0)
    # 单机 90% 时 20 t 在 10 m 可用（15.5/20=0.775），80% 时需要 25 t，下降到 6 m
    assert left.ok and right.ok
    assert left.max_radius == 6.0


def test_split_ratio() -> None:
    a, b = split_by_ratio(30.0, 0.6)
    assert close(a, 18.0, 1e-12)
    assert close(b, 12.0, 1e-12)


def test_rejects_bad_inputs() -> None:
    with pytest.raises(OutOfTableError):
        find_capability([], required=10.0, ratio_limit=0.9)
    with pytest.raises(InfeasibleSectionError):
        find_capability(POINTS, required=-1.0, ratio_limit=0.9)
    with pytest.raises(InfeasibleSectionError):
        find_capability(POINTS, required=10.0, ratio_limit=1.5)
