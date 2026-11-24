"""External statics benchmarks and analytical controls. Sources and setup in cases/README.md."""
import json
import math
from pathlib import Path

import pytest

from liftcalc.core.units import Q
from liftcalc.crane.transfer import Transfer
from liftcalc.data.repo import Repo
from liftcalc.dusk import DesktopApi
from liftcalc.lifting.load_geometry import LoadShape, sling_report
from liftcalc.lifting.rigging import SlingArrangement, branch_force

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


@pytest.mark.parametrize("horizontal_deg,expected_lbf", [(90, 500), (60, 577), (45, 707), (30, 1000)])
def test_tr244c_figure_47_sling_tension(horizontal_deg, expected_lbf):
    arrangement = SlingArrangement(branches=2, angle_deg=90 - horizontal_deg)
    tension = branch_force(Q(1000, "lbf"), arrangement)
    assert tension.to("lbf").magnitude == pytest.approx(expected_lbf, abs=0.5)


@pytest.mark.parametrize("cg_from_left_ft,near_bounds,far_bounds", [
    (2, (2400, 4000), (0, 1600)),  # ITI Fig. 2 percentages, scaled to 8000 lbf
    (3, (1600, 4000), (0, 2400)),  # ITI Fig. 3, published absolute forces
])
def test_iti_eccentric_pick_point_bounds(cg_from_left_ft, near_bounds, far_bounds):
    ft = 0.3048
    shape = LoadShape(length=10*ft, width=4*ft, height=1, cg_x=(cg_from_left_ft-5)*ft,
                      sling_height=2)
    report = sling_report(shape, weight_t=Q(8000, "lb").to("metric_ton").magnitude)
    # Fig. 2/3 top view: A and B are on the left. Compare vertical reactions.
    expected = {(-1, 1): near_bounds, (-1, -1): near_bounds,
                (1, -1): far_bounds, (1, 1): far_bounds}
    actual = {}
    for leg in report.slings:
        run = math.hypot(leg.x - shape.cg_x, leg.y - shape.cg_y)
        vertical_factor = shape.sling_height / math.hypot(shape.sling_height, run)
        corner = (math.copysign(1, leg.x), math.copysign(1, leg.y))
        actual[corner] = tuple(Q(t * vertical_factor, "kN").to("lbf").magnitude
                               for t in (leg.equilibrium_min_kn, leg.equilibrium_max_kn))
    assert actual.keys() == expected.keys()
    for corner, bounds in expected.items():
        assert actual[corner] == pytest.approx(bounds)


# Transcribed from SANY STC1100T7, printed p. 10. Blank cells are omitted.
SANY_10_M = {13.9: 36, 18.5: 36, 23: 36.9, 27.6: 36.2, 32.1: 36.9,
             36.7: 39, 41.2: 37.5, 45.7: 26.8, 50.3: 24.9}
SANY_12_M = {18.5: 29.3, 23: 30, 27.6: 29.8, 32.1: 30.2, 36.7: 32,
             41.2: 32.3, 45.7: 22.7, 50.3: 21.1, 54.9: 19}


@pytest.mark.parametrize("radius,chart_radius,ratings,status", [
    (10, 10, SANY_10_M, "满足"),
    # 54.9 m boom coverage starts at 12 m, outside the requested radius.
    (10.01, 12, {boom: load for boom, load in SANY_12_M.items() if boom != 54.9}, "不满足"),
    (12, 12, SANY_12_M, "不满足"),
    (64.01, None, {}, "资料不足"),
])
def test_sany_published_rows_and_single_crane_verdict(api, radius, chart_radius, ratings, status):
    case = {"kind": "crane.capability", "crane": {"brand": "三一", "model": "STC1100T7"},
            "target_radius": radius, "payload": 33.265, "hook_mass": 0.735}
    cap = api.calculate(case)["cap"]
    assert cap["required"] == pytest.approx(34)
    assert cap["limit"] == 0.9
    assert cap["status"] == status
    assert cap["ok"] == (status == "满足")
    rows = cap["records"]
    assert len(rows) == len(ratings)
    assert {row["boom_len"]: row["rated_load"] for row in rows} == ratings
    assert all(row["radius"] == chart_radius for row in rows)
    if status == "满足":
        assert (cap["boom_len"], cap["rated_load"]) == (36.7, 39)
        assert cap["utilization"] == pytest.approx(34 / 39)
    elif status == "不满足":
        assert cap["closest_utilization"] == pytest.approx(34 / 32.3)


def test_dual_rotation_crosses_sany_chart_step(api, rotation):
    case = rotation["transfer"]
    case.update(mass=50, start=[0, 0, 60], end=[0, 0, 120], obstacles=[])
    for crane, center in zip(case["cranes"], ([-7, -6], [0, -8.1])):
        crane.update(brand="三一", model="STC1100T7", boom=36.7, center=center,
                     config="全配重38.5t·支腿全伸7.3×8.1m·侧方及后方·主臂36.7m", hook=0.735, hook_rating=75)
    result = api.calculate(rotation)
    assert result["loads"] == pytest.approx([28.565, 28.565])
    # B's lug starts and ends below 10 m, reaching 10.1 m at 90 degrees.
    # The 10/12 m ratings for this specific boom are 39/32 t on printed p. 10.
    segments = result["segments"]
    middle = [s for s in segments if s["start"] <= 0.5 <= s["end"]]
    assert middle
    for segment in (segments[0], segments[-1]):
        assert segment["radii"][1][1] < 10
        assert segment["ratios"][1] == pytest.approx(28.565 / 39)
        assert "B表档负荷率超限" not in segment["unsafe"]
    for segment in middle:
        low, high = segment["radii"][1]
        assert low <= 10.1 <= high
        assert segment["ratios"][1] == pytest.approx(28.565 / 32)
        assert "B表档负荷率超限" in segment["unsafe"]
