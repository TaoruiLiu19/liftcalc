import json
import math
from pathlib import Path

import ezdxf
import pytest

from liftcalc.crane.transfer import (Box, Transfer, analyze, candidate_rank, clearance, interpolate_hook,
                                     plan_transfer, segment_gap, world)
from liftcalc.data.repo import Repo
from liftcalc.dusk import DesktopApi

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data():
    data = json.loads((ROOT/"cases/rail-transfer-demo.json").read_text(encoding="utf-8"))
    case = data["transfer"]
    case.update(auto_route=False, auto_stations=False, waypoints=[[-10,-.3,6],[0,0,3],[10,0,0]])
    for crane,y in zip(case["cranes"],(-5.5,5.5)):
        crane.update(center=[0,y],footprint_length=6,footprint_width=6)
    return data


def test_split_and_transverse_equilibrium(data):
    case = Transfer.model_validate(data["transfer"])
    assert case.shares() == pytest.approx((.4,.6))
    case.cg = (1,.2,0)
    with pytest.raises(ValueError,match="偏离"):
        case.shares()
    case.cg = (5,0,0)
    with pytest.raises(ValueError,match="之间"):
        case.shares()


def test_mid_transfer_collision_and_exports(data, tmp_path):
    api = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite"))
    data["transfer"]["obstacles"] = [[0, 0, .6]]
    case = Transfer.model_validate(data["transfer"])
    assert all(clearance(case,case.pose(t),case.obstacles[0]) > 0 for t in (0,1))
    result = api.calculate(data)
    segments = result["segments"]
    assert any("障碍1禁入区相交" in s["unsafe"] for s in segments)
    assert any("A全段可用钩高待核" in s["unknown"] for s in segments)
    assert segments[0]["start"] == 0 and segments[-1]["end"] == 1
    assert all(a["end"] == b["start"] for a,b in zip(segments,segments[1:]))
    for index,drawing in enumerate(result["drawings"]):
        payload, name = api.render(drawing["id"], "dxf")
        path = tmp_path/name
        path.write_bytes(payload)
        doc = ezdxf.readfile(path)
        texts = [t.dxf.text for t in doc.modelspace().query("TEXT")]
        assert not any(word in t for t in texts for word in ("区间", "负荷率", "计算", "超限"))
        if index == 0:
            assert {"AG  6.00 m","BG  4.00 m","AB  10.00 m","A 钩高 6.00 m","B 钩高 6.00 m",
                    "车底离地  1.00 m","L  12.00 m","B=3.00 m","点位坐标 / m"} <= set(texts)
        assert doc.header["$INSUNITS"] == 4 and len(doc.modelspace().query("TEXT")) >= 6


def test_no_chart_cannot_pass_and_hook_overload_is_visible(data):
    case = Transfer.model_validate(data["transfer"])
    case.cranes[0].hook_rating = 1
    case.cranes[1].boom = 123
    result = analyze(case, Repo(ROOT/"data/liftcalc.sqlite"))
    assert all("A钩载超限" in s["unsafe"] and "B幅度无表档" in s["unknown"]
               for s in result["segments"])


def test_projected_boom_gap():
    assert segment_gap((0,0),(2,2),(0,2),(2,0)) == 0
    assert segment_gap((0,0),(1,0),(2,0),(4,0)) == 1

def test_waypoints_turn_car_through_short_gap(data):
    case = Transfer.model_validate(data["transfer"])
    repo = Repo(ROOT/"data/liftcalc.sqlite")
    assert abs(case.cranes[1].center[1]-case.cranes[0].center[1]) < case.length
    segments = analyze(case,repo)["segments"]
    assert {s["leg"] for s in segments} == {1,2,3,4}
    assert not any(msg.startswith(("A机禁入区", "B机禁入区"))
                   for s in segments for msg in s["unsafe"]+s["unknown"])
    case.waypoints = []
    assert any("A机禁入区相交" in s["unsafe"] for s in analyze(case,repo)["segments"])


def test_rotation_in_place_and_signed_turn(data):
    case = Transfer.model_validate(data["transfer"])
    case.start = case.end = (0,0,0)
    case.waypoints = [(0,0,-270)]
    assert case.pose(.25)[2:] == pytest.approx((-.70710678,-.70710678))
    assert case.pose(.5)[:2] == (0,0)

def test_oriented_footprint_and_boom():
    box = Box((0,0),8,2,90)
    assert box.segment_distance((-1,3),(2,3)) == 0
    assert box.segment_distance((3,-1),(3,1)) == pytest.approx(2)
    assert box.distance(Box((3,0),2,2,0)) == pytest.approx(1)
    assert box.separation((0,3,1,0),.5,.5) < 0


def test_plan_without_stations_or_waypoints():
    data = json.loads((ROOT/"cases/rail-transfer-demo.json").read_text("utf8"))
    case = Transfer.model_validate(data["transfer"])
    result = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite")).calculate(data)
    assert result["poses"][0] == case.start and result["poses"][-1] == case.end
    assert len(result["poses"]) > 2 and result["stations"][0] != result["stations"][1]
    # The solver may straighten in the throat; check passage and peak radii.
    assert any(abs(p[2]-case.start[2]) > 30 for p in result["poses"])
    for i in (0, 1):
        assert max(s["radii"][i][1] for s in result["segments"]) < 13
    assert not any("相交" in m or "净距" in m for s in result["segments"] for m in s["unsafe"]+s["unknown"])
    assert any(s["unsafe"] for s in result["segments"])  # demo overload must remain visible


def test_blocked_endpoint_and_fixed_stations(data):
    case = Transfer.model_validate(data["transfer"])
    case.auto_route = True
    case.waypoints = []
    repo = Repo(ROOT/"data/liftcalc.sqlite")
    path,_ = plan_transfer(case,repo)
    assert path.cranes == case.cranes and path.waypoints
    case.obstacles = [(*case.start[:2],1)]
    with pytest.raises(ValueError,match="未找到"):
        plan_transfer(case,repo)


def test_legacy_exclusion_becomes_enclosing_square(data):
    for cr in data["transfer"]["cranes"]:
        del cr["footprint_length"],cr["footprint_width"]
        cr["exclusion"] = 3
    case = Transfer.model_validate(data["transfer"])
    assert case.cranes[0].footprint_length == case.cranes[0].footprint_width == 6

def test_master_hook_crosses_bearing_wrap_without_full_turn(data):
    case = Transfer.model_validate(data["transfer"])
    crane = case.cranes[0]
    lug = case.lugs[0]
    def body_pose(radius,azimuth,yaw):
        angle = math.radians(azimuth)
        rad = math.radians(yaw)
        dx,dy = world((0,0,math.cos(rad),math.sin(rad)),lug)
        return (crane.center[0]+radius*math.cos(angle)-dx,
                crane.center[1]+radius*math.sin(angle)-dy,yaw)
    start,end = body_pose(8,175,38),body_pose(12,-175,15)
    mid = interpolate_hook(crane,lug,start,end,.5)
    assert mid == pytest.approx(body_pose(10,180,26.5))
    assert interpolate_hook(crane,lug,start,end,1) == pytest.approx(end)

def test_unequal_measured_rises_reach_each_hook_check_and_sheet(data):
    a,b = data["transfer"]["cranes"]
    a.update(sling_height=1.75, verified_height=6.0)
    b.update(sling_height=3.0, verified_height=6.0)
    result = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite")).calculate(data)
    assert all("B全段可用钩高待核" in s["unknown"] and "A全段可用钩高待核" not in s["unknown"]
               for s in result["segments"])
    sheet = result["drawings"][0]["svg"]
    assert "A 钩高 5.75 m" in sheet and "B 钩高 7.00 m" in sheet

def test_clearance_threshold_uses_station_edges(data):
    case = Transfer.model_validate(data["transfer"])
    case.start = case.end = (0,0,90)
    case.waypoints = []
    for c,y in zip(case.cranes,(-12,12)):
        c.center = (0,y)
        c.footprint_length,c.footprint_width = 4,2
    case.obstacles = [(2.75,-12,.5)]
    case.plan_clearance = .3
    repo = Repo(ROOT/"data/liftcalc.sqlite")
    info = analyze(case,repo)
    assert info["clearance"] == dict(lower_m=.25,pair="A 机占地 / 障碍 1",leg=1,start=0,end=1)
    assert "A 机占地 / 障碍 1 平面净距不足" in info["segments"][0]["unsafe"]
    case.auto_route = True
    with pytest.raises(ValueError,match="净距"):
        plan_transfer(case,repo)
    case.plan_clearance = .25
    path,info = plan_transfer(case,repo)
    assert info["clearance"]["lower_m"] >= case.plan_clearance


def test_planner_prefers_verified_then_pending_then_known_failure():
    def rank(unsafe,unknown,ratio):
        return candidate_rank([dict(unsafe=unsafe,unknown=unknown,ratios=[ratio],
                                    radii=[(5,6),(5,6)])],1,5)
    assert rank([],[],.75) < rank([],["缺表"],None) < rank(["超限"],[],.85)


def test_lattice_certifies_two_radius_caps_and_rejects_unreachable_endpoint():
    data = json.loads((ROOT/"cases/rail-transfer-demo.json").read_text("utf8"))["transfer"]
    case = Transfer.model_validate(data)
    case.auto_stations = False
    case.mass, case.cg = 6, (0,0,0)
    for crane,y in zip(case.cranes,(-5.5,5.5)):
        crane.center, crane.radius_limit, crane.verified_height = (0,y), 13, 6
    repo = Repo(ROOT/"data/liftcalc.sqlite")
    path, info = plan_transfer(case, repo)
    assert path.cranes == case.cranes
    for s in info["segments"]:
        assert all(upper <= 13 for _, upper in s["radii"])
        assert not s["unknown"] and not s["unsafe"]
    case.cranes[1].radius_limit = 10
    with pytest.raises(ValueError, match="幅度上限"):
        plan_transfer(case, repo)


def test_one_metre_gap_with_locked_stations():
    data = json.loads((ROOT/"cases/rail-transfer-1m-clearance.json").read_text("utf8"))
    result = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite")).calculate(data)
    assert [tuple(s["center"]) for s in result["stations"]] == [(0,-5.5), (0,5.5)]
    # Before adjusting turns the same stations gave 1.010722 m and 20 legs.
    assert result["clearance"]["lower_m"] >= 1.15
    assert len(result["poses"])-1 < 20
    assert result["poses"][0] == (-11,0,90) and result["poses"][-1] == (11,0,90)
    for s in result["segments"]:
        assert not s["unknown"] and not s["unsafe"]
        assert all(ratio <= 4.246/5.8 + 1e-12 for ratio in s["ratios"])
        assert all(upper <= 15.06 for _,upper in s["radii"])


def test_clearance_adjustment_preserves_pending_or_failed_result(data):
    from liftcalc.crane.transfer_search import improve_clearance

    case = Transfer.model_validate(data["transfer"])
    repo = Repo(ROOT/"data/liftcalc.sqlite")
    for mass in (2, 60):
        case.mass = mass
        result = analyze(case, repo)
        assert any(s["unknown"] for s in result["segments"])
        if mass == 60:
            assert any(s["unsafe"] for s in result["segments"])
        path, checked = improve_clearance(case, result, repo, {})
        assert path is case and checked is result
