import json
from pathlib import Path

import ezdxf
import pytest

from liftcalc.crane.transfer import Box, Transfer, analyze, clearance, plan_transfer, segment_gap
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
    for drawing in result["drawings"]:
        payload, name = api.render(drawing["id"], "dxf")
        path = tmp_path/name
        path.write_bytes(payload)
        doc = ezdxf.readfile(path)
        texts = [t.dxf.text for t in doc.modelspace().query("TEXT")]
        assert not any(word in t for t in texts for word in ("区间", "负荷率", "计算", "超限"))
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
