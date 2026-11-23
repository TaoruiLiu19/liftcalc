"""Horizontal two-hook rail transfer. All coordinates and clearances are in metres."""
from __future__ import annotations

import math
from bisect import bisect_left
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from liftcalc.crane.capability import DUAL_LIMIT

Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
XY = tuple[float, float]


class Inputs(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")


class Crane(Inputs):
    brand: str
    model: str
    config: str
    boom: Positive
    center: XY
    boom_buffer: Positive
    footprint_length: Positive
    footprint_width: Positive
    heading: float = 0

    @model_validator(mode="before")
    @classmethod
    def legacy_footprint(cls, data):
        if isinstance(data, dict) and "exclusion" in data:
            data = dict(data)
            side = 2 * float(data.pop("exclusion"))
            data.setdefault("footprint_length", side)
            data.setdefault("footprint_width", side)
        return data

    @property
    def box(self):
        return Box(self.center, self.footprint_length, self.footprint_width, self.heading)

    hook: Positive
    hook_rating: Positive
    rigging: Nonnegative
    sling_height: Positive
    verified_height: Positive | None = None


class Transfer(Inputs):
    auto_route: bool = False
    auto_stations: bool = False
    length: Positive
    width: Positive
    height: Positive
    mass: Positive
    cg: tuple[float, float, float]
    lugs: tuple[XY, XY]
    cranes: tuple[Crane, Crane]
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    waypoints: list[tuple[float, float, float]] = Field(default_factory=list, max_length=30)
    gauge: Positive = 1.435
    bottom: Positive
    factor: Annotated[float, Field(ge=1)]
    obstacles: list[tuple[float, float, Positive]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def unspecified_stations(cls, data):
        if isinstance(data, dict) and data.get("auto_stations") is True:
            # Only a search seed; no unchecked placeholder position is exported.
            return {**data, "auto_route": True, "cranes": [
                {"center": (0,0), **crane} if isinstance(crane,dict) else crane
                for crane in data.get("cranes", ())
            ]}
        return data

    def shares(self):
        a, b = self.lugs
        gx, gy, gz = self.cg
        if any(abs(x) > self.length / 2 or abs(y) > self.width / 2
               for x, y in (a, b, (gx, gy))) or abs(gz) >= self.height / 2:
            raise ValueError("吊点须在顶面内，重心须在顶面以下且位于吊物内。")
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = math.hypot(dx, dy)
        if span < 1e-6:
            raise ValueError("两吊点不能重合。")
        if abs((gx-a[0])*dy - (gy-a[1])*dx) / span > 1e-8:
            raise ValueError("重心投影偏离两吊点连线，两根竖向吊索无法维持所设水平姿态。")
        share = ((gx-a[0])*dx + (gy-a[1])*dy) / span**2
        if not 0 < share < 1:
            raise ValueError("重心投影须在两吊点之间，两侧均须受拉。")
        return 1-share, share

    @property
    def route(self):
        return [self.start, *self.waypoints, self.end]

    def pose(self, t):
        route = self.route
        offset = t * (len(route)-1)
        leg = min(int(offset), len(route)-2)
        u = offset - leg
        x, y, deg = (a + u*(b-a) for a, b in zip(route[leg], route[leg+1]))
        angle = math.radians(deg)
        return x, y, math.cos(angle), math.sin(angle)


def world(pose, point):
    x, y, c, s = pose
    u, v = point
    return x + c*u - s*v, y + s*u + c*v


def clearance(case, pose, disk):
    x, y, c, s = pose
    dx, dy = disk[0]-x, disk[1]-y
    u = abs(c*dx+s*dy) - case.length/2
    v = abs(-s*dx+c*dy) - case.width/2
    return math.hypot(max(u, 0), max(v, 0)) + min(max(u, v), 0) - disk[2]


def point_segment(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length2 = dx*dx + dy*dy
    if not length2:
        return math.dist(p, a)
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length2))
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def segment_gap(a, b, c, d):
    def cross(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0])
    if cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0:
        return 0.0
    return min(point_segment(a,c,d), point_segment(b,c,d),
               point_segment(c,a,b), point_segment(d,a,b))


class Box:
    """Oriented footprint centered on the entered rotation center."""

    def __init__(self, center, length, width, heading):
        theta = math.radians(heading)
        self.pose = (*center, math.cos(theta), math.sin(theta))
        self.length, self.width = length, width
        self.corners = tuple(world(self.pose, (x*length/2,y*width/2))
                             for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)))

    def separation(self, pose, length, width):
        # Maximum separating-axis gap is a conservative lower bound on distance.
        x,y,c,s = pose
        bx,by,u,v = self.pose
        dx,dy = x-bx,y-by
        co,si = abs(c*u+s*v),abs(s*u-c*v)
        a,b = self.length/2,self.width/2
        l,w = length/2,width/2
        return max(abs(dx*u+dy*v)-a-l*co-w*si,
                   abs(-dx*v+dy*u)-b-l*si-w*co,
                   abs(dx*c+dy*s)-l-a*co-b*si,
                   abs(-dx*s+dy*c)-w-a*si-b*co)

    def segment_distance(self, a, b):
        dx,dy = b[0]-a[0],b[1]-a[1]
        length = math.hypot(dx,dy)
        c,s = (dx/length,dy/length) if length else (1,0)
        pose = ((a[0]+b[0])/2,(a[1]+b[1])/2,c,s)
        if self.separation(pose,length,0) <= 0:
            return 0
        return min(segment_gap(a,b,self.corners[i-1],p) for i,p in enumerate(self.corners))

    def distance(self, other):
        if self.separation(other.pose,other.length,other.width)<=0:
            return 0.0
        return min(self.segment_distance(other.corners[i-1],p) for i,p in enumerate(other.corners))


def route_intervals(case):
    route = case.route
    leg_count = len(route)-1
    total = 0
    for leg, (a, b) in enumerate(zip(route, route[1:])):
        travel = math.dist(a[:2], b[:2])
        turn = abs(math.radians(b[2]-a[2]))
        sweep = travel + turn*math.hypot(case.length, case.width)/2
        count = max(1, math.ceil(sweep/.2), math.ceil(turn/math.radians(1)))
        total += count
        if total > 5000:
            raise ValueError("轨迹过长，请拆分工况。")
        for i in range(count):
            yield (leg, (leg+i/count)/leg_count, (leg+(i+1)/count)/leg_count,
                   travel/count, turn/count, sweep/count)


def analyze(case, repo, *, chart_cache=None):
    shares = case.shares()
    boxes = [c.box for c in case.cranes]
    stationary = []
    if boxes[0].distance(boxes[1]) <= 0:
        stationary.append("两机占地矩形相交")
    for j,box in enumerate(boxes):
        if any(clearance(box,box.pose,o)<=0 for o in case.obstacles):
            stationary.append("AB"[j]+"机占地与场地障碍相交")
    if chart_cache is None:
        chart_cache = {}
    charts = []
    loads = []
    for crane, share in zip(case.cranes, shares):
        key = (crane.brand, crane.model, crane.config, crane.boom)
        if key not in chart_cache:
            rows = [r for r in repo.model_capacity(crane.brand, crane.model)
                    if r["config_name"] == crane.config and r["boom_len"] == crane.boom]
            chart_cache[key] = sorted(rows, key=lambda r: r["radius"])
        charts.append(chart_cache[key])
        loads.append((case.mass*share + crane.rigging)*case.factor + crane.hook)

    segments = []
    for leg, start, end, travel, turn, sweep in route_intervals(case):
        mid = (start+end)/2
        pose = case.pose(mid)
        unsafe, unknown = stationary.copy(), []
        ratios = []
        radius_bounds = []
        hooks = [world(pose, lug) for lug in case.lugs]
        for j, (crane, lug, rows, gross) in enumerate(zip(case.cranes, case.lugs, charts, loads)):
            tag = "AB"[j]
            radius = math.dist(world(pose, lug), crane.center)
            delta = (travel + turn*math.hypot(*lug))/2
            radii = [r["radius"] for r in rows]
            if gross-crane.hook > crane.hook_rating:
                unsafe.append(tag+"钩载超限")
            witness = [math.dist(world(case.pose(t), lug), crane.center)
                       for t in (start, mid, end)]
            if not rows or min(witness) < radii[0] or max(witness) > radii[-1]:
                unknown.append(tag+"幅度无表档")
            lower, upper = radius-delta, radius+delta
            if rows and (lower < radii[0] or upper > radii[-1]):
                unknown.append(tag+"幅度包络超出表域")
            radius_bounds.append((max(0, lower), upper))
            bucket = rows[bisect_left(radii, lower):bisect_left(radii, upper)+1]
            ratio = max((gross/r["rated_load"] for r in bucket if r["rated_load"] > 0), default=None)
            ratios.append(ratio)
            for r in witness:
                k = bisect_left(radii, r)
                if rows and radii[0] <= r and k < len(rows) and gross > rows[k]["rated_load"]*DUAL_LIMIT:
                    unsafe.append(tag+"表档负荷率超限")
                    break
            if ratio is not None and ratio > DUAL_LIMIT and tag+"表档负荷率超限" not in unsafe:
                unknown.append(tag+"区间可能超载")
            required_h = case.bottom+case.height+crane.sling_height
            for r in witness:
                k = bisect_left(radii, r)
                if k < len(rows) and radii[k] == r and rows[k]["lift_height"] is not None and rows[k]["lift_height"] < required_h:
                    unsafe.append(tag+"钩高不足")
                    break
            chart_height = None
            k = bisect_left(radii, radius)
            if delta == 0 and k < len(rows) and radii[k] == radius:
                chart_height = rows[k]["lift_height"]
            if max(chart_height or 0, crane.verified_height or 0) < required_h:
                unknown.append(tag+"全段可用钩高待核")
        witnesses = (case.pose(start), pose, case.pose(end))
        gaps = [("AB"[j]+"机", [box.separation(p,case.length,case.width) for p in witnesses])
                for j,box in enumerate(boxes)]
        gaps += [(f"障碍{j+1}", [clearance(case,p,disk) for p in witnesses])
                 for j,disk in enumerate(case.obstacles)]
        for label, distances in gaps:
            if min(distances) <= 0:
                unsafe.append(label+"禁入区相交")
            elif distances[1] <= sweep/2:
                unknown.append(label+"区间净距待核")
        for j, crane in enumerate(case.cranes):
            movement = (travel + turn*math.hypot(*case.lugs[j]))/2
            start_xy,end_xy = crane.center,hooks[j]
            gaps = [("AB"[1-j]+"机",boxes[1-j].segment_distance(start_xy,end_xy))]
            gaps += [(f"障碍{k+1}", point_segment(disk[:2],start_xy,end_xy)-disk[2])
                     for k,disk in enumerate(case.obstacles)]
            for label, dist in gaps:
                gap = dist-crane.boom_buffer
                if gap <= movement:
                    tag = "AB"[j]+"臂平面包络与"+label+"禁区"
                    (unsafe if gap<=0 else unknown).append(tag+("相交" if gap<=0 else "待核"))
        c1,c2 = case.cranes
        gap = segment_gap(c1.center,hooks[0],c2.center,hooks[1])-c1.boom_buffer-c2.boom_buffer
        if gap <= (2*travel+turn*sum(math.hypot(*p) for p in case.lugs))/2:
            unknown.append("两臂投影可能交叠，须核三维净空")
        segments.append(dict(leg=leg+1, start=start, end=end, ratios=ratios, radii=radius_bounds,
                             unsafe=unsafe, unknown=list(dict.fromkeys(unknown))))
    return dict(shares=shares, loads=loads, segments=segments)


def candidate_stations(case, heading):
    if not case.auto_stations:
        yield case.cranes
        return
    # Sample stationary layouts along the transfer corridor. Dimensions include
    # the outriggers; the footprint stays fixed throughout each candidate lift.
    c,s = math.cos(heading),math.sin(heading)
    normal = (-s,c)
    a,b = [world(case.pose(0),lug) for lug in case.lugs]
    sign = 1 if (b[0]-a[0])*normal[0]+(b[1]-a[1])*normal[1]>=0 else -1
    for fraction in (.5,.35,.65):
        mid = [case.start[i]+fraction*(case.end[i]-case.start[i]) for i in (0,1)]
        for margin in (.35,1.5):
            pair = []
            for j,crane in enumerate(case.cranes):
                offset = (case.width/2+crane.footprint_width/2+margin)*sign*(-1 if j==0 else 1)
                xy = tuple(mid[i]+offset*normal[i] for i in (0,1))
                pair.append(crane.model_copy(update={"center":xy,"heading":math.degrees(heading)}))
            yield tuple(pair)


def candidate_routes(case):
    yield []
    a,b = case.cranes
    dx,dy = b.center[0]-a.center[0], b.center[1]-a.center[1]
    sep = math.hypot(dx,dy)
    if sep == 0:
        return
    nx,ny = dx/sep,dy/sep
    ux,uy = ny,-nx
    if ux*(case.end[0]-case.start[0])+uy*(case.end[1]-case.start[1])<0:
        ux,uy = -ux,-uy
    mid = tuple((x+y)/2 for x,y in zip(a.center,b.center))
    angle = math.degrees(math.atan2(uy,ux))
    angle += 180*round((case.start[2]-angle)/180)
    # Search both end-first orientations, several lateral passages and staging
    # distances. Never silently wrap the user's requested final heading.
    for tilt in (0,180 if angle<case.start[2] else -180):
        yaw = angle+tilt
        for side in (0,-.22,.22):
            gx,gy = mid[0]+side*sep*nx,mid[1]+side*sep*ny
            for reach in (.65,1.05):
                d = reach*case.length+max(cr.footprint_length for cr in case.cranes)/2
                yield [(gx-ux*d,gy-uy*d,yaw),(gx,gy,yaw),(gx+ux*d,gy+uy*d,yaw)]


def plan_transfer(case, repo):
    """Bounded corridor search, with continuous interval checks on each finalist."""
    if not (case.auto_route or case.auto_stations):
        return case, analyze(case,repo)
    case.shares()
    heading = math.atan2(case.end[1]-case.start[1], case.end[0]-case.start[0])
    best = None
    chart_cache = {}
    for pair in candidate_stations(case,heading):
        layout = case.model_copy(update={"cranes":pair})
        boxes = [cr.box for cr in pair]
        if boxes[0].distance(boxes[1])<=0 or any(clearance(box,box.pose,o)<=0
                for box in boxes for o in case.obstacles):
            continue
        for waypoints in candidate_routes(layout):
            path = layout.model_copy(update={"waypoints":waypoints})
            # Cheap collision rejection before evaluating the entire load chart.
            samples = max(8,8*(len(waypoints)+1))
            witness_poses = (path.pose(t/samples) for t in range(samples+1))
            if any(any(box.separation(p,path.length,path.width)<=0 for box in boxes)
                   or any(clearance(path,p,o)<=0 for o in path.obstacles)
                   for p in witness_poses):
                continue
            result = analyze(path,repo,chart_cache=chart_cache)
            segments = result["segments"]
            issues = {msg for seg in segments for msg in seg["unsafe"]+seg["unknown"]}
            if any(any(term in msg for term in ("相交","净距","禁区","交叠")) for msg in issues):
                continue
            overload = any(seg["unsafe"] for seg in segments)
            outside = any("表域" in m or "表档" in m and "无" in m for m in issues)
            peak = max((r for seg in segments for r in seg["ratios"] if r is not None),default=math.inf)
            rank = (overload or outside, outside, overload, len(issues),peak,len(waypoints))
            if best is None or rank < best[0]:
                best = rank,path,result
            if not issues:
                return path,result
    if best is None:
        raise ValueError("在本次有限搜索范围内未找到通过平面连续避碰校核的路径。请核对起止位置、占地和可用场地。")
    return best[1],best[2]
