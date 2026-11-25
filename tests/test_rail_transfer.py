import json
import math
from itertools import combinations
from pathlib import Path

import ezdxf
import pytest

from liftcalc.crane.transfer import (Box, Transfer, analyze, candidate_rank, candidate_routes, clearance, interpolate_hook,
                                     plan_transfer, segment_gap, station_shift, world)
from liftcalc.data.repo import Repo
from liftcalc.dusk import DesktopApi
from liftcalc.drawing.annotation import _edges, stroke_text_interval
from liftcalc.drawing.body import MAIN_WINCH, MAIN_WINCH_RADIUS, WHEEL_R
from liftcalc.drawing.figures import HINGE_H, LIFT_SHEAVE_RADIUS
from liftcalc.drawing.primitives import Circle, Line, Polyline, Text, item_bbox
from liftcalc.drawing.style import LAYER_OUTLINE, LAYER_RIGGING, LAYER_TRACE_A, LAYER_TRACE_B
from liftcalc.drawing.sheet import overlaps
from liftcalc.drawing.transfer import crane_elevation, first_gate_crossing, sheets, statics

ROOT = Path(__file__).resolve().parents[1]


def test_automatic_stagger_around_opposing_obstacles():
    data = json.loads((ROOT/"cases/rail-transfer-auto-stagger.json").read_text("utf8"))
    assert all("center" not in c for c in data["transfer"]["cranes"])
    result = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite")).calculate(data)
    a,b = (c["center"] for c in result["stations"])
    assert a[0] > b[0] and math.dist(a,b) < data["transfer"]["length"]
    assert result["clearance"]["lower_m"] >= data["transfer"]["plan_clearance"]
    for segment in result["segments"]:
        assert not segment["unsafe"] and not segment["unknown"]
        assert all(upper < 12 for _,upper in segment["radii"])
        assert max(segment["ratios"]) < .4


def test_obstacle_shift_merges_overlaps_and_respects_corridor(data):
    crane = Transfer.model_validate(data["transfer"]).cranes[0].model_copy(
        update={"center":(0,0),"footprint_length":10,"footprint_width":5})
    # Rotated longitudinal axis: the two disks exclude overlapping stations.
    obstacles = [(0,0,1),(0,6,1)]
    assert station_shift(crane,obstacles,math.pi/2,.5,-13,13) == pytest.approx(-6.5)
    assert station_shift(crane,obstacles,math.pi/2,.5,-6,13) == pytest.approx(12.5)
    assert station_shift(crane,obstacles,math.pi/2,.5,-6,12) is None
    assert station_shift(crane,[(0,3.4,1)],0,.5,-10,10) == pytest.approx(-6.2)


def test_staggered_cranes_allow_oblique_passage():
    data = json.loads((ROOT/"cases/rail-transfer-oblique.json").read_text("utf8"))
    result = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite")).calculate(data)
    assert result["clearance"]["lower_m"] >= .5
    assert all(not s["unsafe"] and not s["unknown"] for s in result["segments"])
    path = Transfer.model_validate(data["transfer"]).model_copy(update={"waypoints":result["poses"][1:-1]})
    pose, yaw, travel = first_gate_crossing(path)
    assert 11*pose[0]-3*pose[1] == pytest.approx(0, abs=1e-8)
    assert 5 < yaw < travel < 45
    svg = result["drawings"][1]["svg"]
    assert f"吊物纵轴 {yaw:.1f}°" in svg and f"形心移动方向 {travel:.1f}°" in svg


def test_gate_touch_and_crossing_beyond_centres_are_not_transits(data):
    case = Transfer.model_validate(data["transfer"])
    case.start = (-2,0,30)
    case.waypoints = [(0,0,30)]
    case.end = (-1,0,30)
    assert first_gate_crossing(case) is None
    case.end = (1,0,30)
    _, yaw, travel = first_gate_crossing(case)
    assert (yaw,travel) == pytest.approx((30,0))
    case.start,case.end,case.waypoints = (-2,20,0),(1,20,0),[]
    assert first_gate_crossing(case) is None


def test_skew_candidates_preserve_projected_body_clearance():
    data = json.loads((ROOT/"cases/rail-transfer-1m-clearance.json").read_text("utf8"))
    case = Transfer.model_validate(data["transfer"])
    signs = set()
    for route in candidate_routes(case):
        if len(route) != 2:
            continue
        entry, departure = route
        angle = math.radians(entry[2])
        width = case.length*abs(math.sin(angle)) + case.width*abs(math.cos(angle))
        # The inner faces are at y = +/-3 m. Centre drift uses the residual width.
        assert max(abs(entry[1]),abs(departure[1])) + width/2 + case.plan_clearance <= 3+1e-9
        signs.add((math.copysign(1,math.tan(angle)),math.copysign(1,departure[1]-entry[1])))
    assert len(signs) == 4


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
    assert result["status"] == "planned"
    collision = "吊物与障碍物 1 禁入区接触或相交"
    blocked = next(s for s in segments if collision in s["unsafe"])
    witness = blocked["evidence"][collision]
    assert 0 < witness["progress"] < 1
    assert blocked["start"] <= witness["progress"] <= blocked["end"]
    assert clearance(case, case.pose(witness["progress"]), case.obstacles[0]) <= 0
    assert segments[0]["start"] == 0 and segments[-1]["end"] == 1
    assert all(a["end"] == b["start"] for a,b in zip(segments,segments[1:]))
    assert [drawing["kind"] for drawing in result["drawings"]] == [
        "statics", "trajectory", "elevation-a", "elevation-b",
    ]
    for index,(drawing,figure) in enumerate(zip(result["drawings"],sheets(case,result),strict=True)):
        captions = [item for item in figure.primitives if isinstance(item, Text) and item.content]
        assert not any(overlaps(a.bbox(),b.bbox()) for a,b in combinations(captions,2))
        for item in figure.primitives:
            if isinstance(item,(Line,Polyline)):
                for a,b in _edges(item):
                    assert not any(stroke_text_interval(a,b,caption,gap=.15) for caption in captions), item
        payload, name = api.render(drawing["id"], "dxf")
        path = tmp_path/name
        path.write_bytes(payload)
        doc = ezdxf.readfile(path)
        texts = [t.dxf.text for t in doc.modelspace().query("TEXT")]
        assert not any(word in t for t in texts for word in ("区间", "负荷率", "待核", "超限"))
        if index == 0:
            assert {"AG  6.00 m","BG  4.00 m","AB  10.00 m","A 吊钩中心离地高度 6.00 m","B 吊钩中心离地高度 6.00 m",
                    "吊物底面离地  1.00 m","L  12.00 m","B=3.00 m","主视图","俯视图","左视图 · 吊物端面"} <= set(texts)
            assert "点位坐标 / m" not in texts
        if index == 1:
            assert {"P0 起吊", "吊点 A 轨迹", "吊点 B 轨迹", "吊物形心轨迹"} <= set(texts)
            assert len({doc.layers.get(layer).rgb for layer in ("TRACE_CENTER", "TRACE_A", "TRACE_B")}) == 3
        assert doc.header["$INSUNITS"] == 4 and len(doc.modelspace().query("TEXT")) >= 6


def test_transfer_overload_reports_first_witness_and_chart(data):
    data["transfer"]["mass"] = 8
    api = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite"))
    result = api.calculate(data)
    reason = "B 机起重性能表负荷率超限"
    first = next(s for s in result["segments"] if reason in s["unsafe"])
    witness = first["evidence"][reason]
    assert 0.65 < witness["progress"] < 0.75
    assert first["start"] <= witness["progress"] <= first["end"]
    assert all(detail in witness["text"] for detail in ("表列工作幅度 16 m", "6.23 t", "5.80 t", "107.3%", "80%"))


def test_unplanned_transfer_reports_blocked_pickup(data):
    case = data["transfer"]
    case.update(auto_route=True, obstacles=[[*case["start"][:2], .6]])
    result = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite")).calculate(data)
    assert result["status"] == "unplanned"
    assert any("起吊" in reason and "障碍物 1 禁入区" in reason for reason in result["reasons"])
    assert "poses" not in result and "drawings" not in result


def test_no_chart_cannot_pass_and_hook_overload_is_visible(data):
    case = Transfer.model_validate(data["transfer"])
    case.cranes[0].hook_rating = 1
    case.cranes[1].boom = 123
    result = analyze(case, Repo(ROOT/"data/liftcalc.sqlite"))
    assert all("A 机主吊钩组承载超限" in s["unsafe"] and "B 机工作幅度无性能表数据" in s["unknown"]
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
    assert not any(msg.startswith(("吊物与A 机占地包络", "吊物与B 机占地包络"))
                   for s in segments for msg in s["unsafe"]+s["unknown"])
    case.waypoints = []
    assert any("吊物与A 机占地包络接触或相交" in s["unsafe"] for s in analyze(case,repo)["segments"])


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

def test_optional_drawing_heights_change_sheets_without_affecting_transfer_checks(data):
    api = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite"))
    data["transfer"].pop("bottom")
    for crane in data["transfer"]["cranes"]:
        crane.pop("sling_height")
    baseline = api.calculate(data)
    assert baseline["status"] == "planned"
    assert "A 吊钩中心离地高度 6.00 m" in baseline["drawings"][0]["svg"]
    a,b = data["transfer"]["cranes"]
    a.update(sling_height=1.75, verified_height=6.0)
    b.update(sling_height=3.0, verified_height=6.0)
    result = api.calculate(data)
    for key in ("shares", "loads", "segments", "stations", "poses", "clearance"):
        assert result[key] == baseline[key]
    sheet = result["drawings"][0]["svg"]
    assert "A 吊钩中心离地高度 5.75 m" in sheet and "B 吊钩中心离地高度 7.00 m" in sheet
    _, _, left, right = result["drawings"]
    assert "A 吊钩中心  H=5.75 m" in left["svg"] and "B 吊钩中心" not in left["svg"]
    assert "B 吊钩中心  H=7.00 m" in right["svg"] and "A 吊钩中心" not in right["svg"]
    assert "A 机分担的吊物质量 6.40 t" in left["svg"] and "B 机分担的吊物质量 9.60 t" in right["svg"]


def test_statics_aligns_three_load_projections_with_diagonal_lugs(data):
    case = Transfer.model_validate(data["transfer"])
    case.width,case.height = 3.4,2.6
    case.lugs = ((-5, -.7), (5, .7))
    case.cg = (.5, .07, .2)
    corners = [(x*case.length/2,y*case.width/2) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
    figure = statics(case, {"shares":case.shares()}, corners)
    scale = figure.meta["scale"]
    rectangles = [item_bbox(item) for item in figure.primitives
                  if isinstance(item, Polyline) and item.closed and item.layer == LAYER_OUTLINE]
    def view(width, height):
        return next(rect for rect in rectangles
                    if (rect[2]-rect[0],rect[3]-rect[1]) == pytest.approx((width*scale,height*scale)))
    front = view(case.length,case.height)
    top = view(case.length,case.width)
    end = view(case.width,case.height)
    assert front[0::2] == top[0::2]
    assert front[1::2] == end[1::2]
    assert top[3]-top[1] == pytest.approx(end[2]-end[0])
    assert top[3] < front[1] and front[2] < end[0]


@pytest.mark.parametrize("offset", [0.0, 0.5])
def test_elevations_project_cargo_end_and_only_one_crane_at_pickup(data, offset):
    case = Transfer.model_validate(data["transfer"])
    case.start = (13, -6, 90)
    case.end = (16, 7, 0)
    case.waypoints = []
    case.lugs = ((-5, -offset), (5, offset))
    case.cg = (0, 0, 0)
    pose = case.pose(0)
    stations = (-11-offset, 11+offset)
    for crane, lug, y in zip(case.cranes, case.lugs, stations):
        crane.center = world(pose, (lug[0]+4*offset, y))
    radius = math.hypot(11,4*offset)
    result = analyze(case, Repo(ROOT/"data/liftcalc.sqlite"))

    for side in range(2):
        tag, other = "AB"[side], "BA"[side]
        figure = crane_elevation(case, result, side)
        scale = figure.meta["scale"]
        texts = {item.content for item in figure.primitives if isinstance(item, Text)}
        assert {"吊物端面", "短边 3.00 m", "吊物高度 3.00 m", f"吊点 {tag}", f"{tag} 机占地包络投影"} <= texts
        assert all(f"吊点 {other}" not in text and f"{other} 机占地" not in text for text in texts)
        assert any("P0 起吊" in text for text in texts)
        assert any(text.startswith(f"起吊工作幅度 R={radius:.2f} m") for text in texts)
        assert {"吊索", "起升钢丝绳"} <= texts
        assert not any(isinstance(item, Polyline) and item.layer in (LAYER_TRACE_A,LAYER_TRACE_B)
                       for item in figure.primitives)
        lugs = [item for item in figure.primitives if isinstance(item, Circle) and item.r == .85]
        assert len(lugs) == 1
        body = next(item for item in figure.primitives if isinstance(item, Polyline) and item.closed
                    and len(item.points) == 4 and min(y for _, y in item.points) < lugs[0].cy
                    and max(y for _, y in item.points) == pytest.approx(lugs[0].cy))
        xs = [x for x, _ in body.points]
        center = (min(xs) + max(xs))/2
        assert max(xs) - min(xs) == pytest.approx(case.width * scale)
        assert lugs[0].cx == pytest.approx(center-case.lugs[side][1]*scale)
        pivot_z = lugs[0].cy + (HINGE_H-case.bottom-case.height)*scale
        pivots = [item.cx for item in figure.primitives if isinstance(item, Circle) and item.r == 1.2
                  and item.cy == pytest.approx(pivot_z)]
        assert pivots == pytest.approx([center-stations[side]*scale])
        wheel_y = lugs[0].cy + (WHEEL_R-case.bottom-case.height)*scale
        wheels = [item for item in figure.primitives if isinstance(item, Circle)
                  and item.r == pytest.approx(WHEEL_R*scale) and item.cy == pytest.approx(wheel_y)]
        assert len(wheels) == 4
        hook_y = lugs[0].cy + case.cranes[side].sling_height*scale
        red_lines = [item for item in figure.primitives if isinstance(item, Line) and item.layer == LAYER_RIGGING]
        assert any((line.x1,line.y1,line.x2,line.y2) == pytest.approx((lugs[0].cx,lugs[0].cy,lugs[0].cx,hook_y))
                   for line in red_lines)
        strands = sorted(line.x1 for line in red_lines if line.x1 == pytest.approx(line.x2)
                         and min(line.y1,line.y2) > hook_y and abs(line.y2-line.y1) > 5*scale)
        assert len(strands) == 2
        assert strands[1]-strands[0] == pytest.approx(2*LIFT_SHEAVE_RADIUS*scale*11/radius)
        pivot_x = pivots[0]
        radial = (case.lugs[side][1]-stations[side])/radius
        ground = lugs[0].cy-(case.bottom+case.height)*scale
        drum_x, drum_y = pivot_x-radial*MAIN_WINCH[0]*scale, ground+MAIN_WINCH[1]*scale
        assert any(math.hypot((x-drum_x)/(radial*scale),(y-drum_y)/scale) == pytest.approx(MAIN_WINCH_RADIUS)
                   for line in red_lines for x,y in ((line.x1,line.y1),(line.x2,line.y2)))


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
    assert info["clearance"] == dict(lower_m=.25,pair="A 机占地包络 / 障碍物 1 禁入区",leg=1,start=0,end=1)
    assert "A 机占地包络 / 障碍物 1 禁入区 水平净距不足" in info["segments"][0]["unsafe"]
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
        crane.center, crane.radius_limit = (0,y), 13
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
    case.cranes[0].boom = 123
    repo = Repo(ROOT/"data/liftcalc.sqlite")
    for mass in (2, 60):
        case.mass = mass
        result = analyze(case, repo)
        assert any("A 机工作幅度无性能表数据" in s["unknown"] for s in result["segments"])
        if mass == 60:
            assert any(s["unsafe"] for s in result["segments"])
        path, checked = improve_clearance(case, result, repo, {})
        assert path is case and checked is result
