"""离线保证（ADR-008）：断网也必须能算。

这是一条"可验证的属性"，不是口头承诺。
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from liftcalc.core.result import Verdict
from liftcalc.services.calc import run_case

EYE_CASE = {
    "kind": "lifting_eye.check",
    "units": {"length": "mm", "force": "kN", "stress": "MPa"},
    "meta": {"project": "offline", "part": "eye"},
    "geometry": {"plate_t": 30, "plate_b": 300, "plate_h": 400, "hole_d": 80, "hole_edge": 120},
    "material": {"grade": "Q355B", "fy": 355},
    "load": {"design": 500, "dynamic_factor": 1.1, "angle_deg": 5},
}


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError("测试中禁止联网")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield


def test_eye_calc_runs_without_network(no_network: None) -> None:
    result = run_case(EYE_CASE)
    assert result.verdict is Verdict.PASS
    assert len(result.checks) == 3


def test_section_calc_runs_without_network(no_network: None) -> None:
    result = run_case(
        {
            "kind": "section.props",
            "units": {"length": "mm", "force": "kN"},
            "section": {"type": "rect", "b": 300, "h": 500},
        }
    )
    assert result.checks[0].value > 0


def test_centroid_calc_runs_without_network(no_network: None) -> None:
    result = run_case(
        {
            "kind": "geometry.centroid",
            "units": {"length": "mm"},
            "solids": [{"type": "box", "dims": {"a": 100, "b": 100, "c": 200}}],
        }
    )
    assert result.checks[0].value > 0
