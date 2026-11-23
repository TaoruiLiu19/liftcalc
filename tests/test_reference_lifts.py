"""External statics benchmarks and analytical controls. Sources and setup in cases/README.md."""
import json
import math
from pathlib import Path

import pytest

from liftcalc.crane.transfer import Transfer
from liftcalc.data.repo import Repo
from liftcalc.dusk import DesktopApi
from liftcalc.lifting.load_geometry import LoadShape, sling_report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rotation():
    return json.loads((ROOT / "cases/rail-transfer-rotation-check.json").read_text("utf8"))


@pytest.fixture
def api():
    return DesktopApi(Repo(ROOT / "data/liftcalc.sqlite"))


@pytest.mark.parametrize("mass, cg_x, expected", [
    (200, 0, (100, 100)),  # ICSA N002 Annex 2, freely suspended
    (40, -5, (30, 10)),    # Texas DWC p. 46, scaled horizontal lever arms
])
def test_published_vertical_shares(rotation, mass, cg_x, expected):
    data = rotation["transfer"]
    # Only the free-body calculation is under test; no crane selection is inferred.
    data.update(mass=mass, length=40, cg=[cg_x,0,0], lugs=[[-10,0],[10,0]])
    transfer = Transfer.model_validate(data)
    assert tuple(mass*s for s in transfer.shares()) == pytest.approx(expected)


def test_duerr_table_one_diagonal_envelope():
    # Only normalized V/W is compared. The symmetric test dimensions are arbitrary.
    weight = 98.0665  # kN for the 10 t normalization
    report = sling_report(LoadShape(length=6, width=2, height=1, sling_height=3), 10)
    for leg in report.slings:
        vertical = math.cos(math.radians(leg.angle_deg)) / weight
        assert leg.force_t * 9.80665 * vertical == pytest.approx(.25)
        assert leg.equilibrium_min_kn * vertical == pytest.approx(0)
        assert leg.equilibrium_max_kn * vertical == pytest.approx(.5)
    # Equal members of each diagonal pair in the symmetric idealization.
    for heavy_fraction in (.943, 1.0, .502):  # Duerr Table 1, cases 1, 2, 18
        for leg, share in zip(report.slings,
                              (heavy_fraction,1-heavy_fraction,1-heavy_fraction,heavy_fraction)):
            tension = weight * share / 2 / math.cos(math.radians(leg.angle_deg))
            assert leg.equilibrium_min_kn - 1e-10 <= tension <= leg.equilibrium_max_kn + 1e-10


@pytest.mark.parametrize("threshold,status", [(.30,"pass"), (.36,"unknown"), (.40,"fail")])
def test_exact_mid_swing_clearance(api, rotation, threshold, status):
    rotation["transfer"]["plan_clearance"] = threshold
    r = api.calculate(rotation)
    # A rectangle corner points at the disk twice during the quarter turn.
    exact = 5 - math.sqrt(17) - .5
    info = r["clearance"]
    half_step_sweep = math.sqrt(17)*math.radians(.5)
    assert exact - half_step_sweep <= info["lower_m"] <= exact + 1e-12
    assert info["pair"] == "吊物 / 障碍1"
    offset = math.degrees(math.atan2(1,4))
    assert any(info["start"]*90 <= yaw <= info["end"]*90 for yaw in (45-offset,45+offset))
    unsafe = {m for segment in r["segments"] for m in segment["unsafe"]}
    unknown = {m for segment in r["segments"] for m in segment["unknown"]}
    assert ("吊物 / 障碍1 平面净距不足" in unsafe) == (status == "fail")
    if status != "fail":
        assert ("吊物 / 障碍1 未证实达到要求的平面净距" in unknown) == (status == "unknown")
    assert all("A全段可用钩高待核" in s["unknown"] for s in r["segments"])


@pytest.mark.parametrize("mass,gross,fails", [(20,11.946,False), (21,12.496,True)])
def test_qy70_exact_chart_boundary(api, rotation, mass, gross, fails):
    case = rotation["transfer"]
    case.update(mass=mass, length=12, start=[0,0,0], end=[0,0,0],
                lugs=[[-5,0],[5,0]], obstacles=[])
    for crane,x in zip(case["cranes"],(-15,15)):
        crane.update(center=[x,0], footprint_length=10, footprint_width=5)
    r = api.calculate(rotation)
    assert r["loads"] == pytest.approx([gross,gross])
    segment, = r["segments"]
    assert segment["ratios"] == pytest.approx([gross/15.5]*2)
    assert set(segment["unsafe"]) == ({"A表档负荷率超限","B表档负荷率超限"} if fails else set())
    assert not segment["unknown"]
