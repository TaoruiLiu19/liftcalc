"""Horizontal two-hook rail transfer. All coordinates and clearances are in metres."""
from __future__ import annotations

import math
from bisect import bisect_left
from itertools import chain
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
    sling_height: Positive = 2.0  # Elevation drawing only.
    verified_height: Positive | None = None  # Accepted for older cases.
    radius_limit: Positive | None = None


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
    bottom: Nonnegative = 1.0  # Elevation drawing only.
    plan_clearance: Nonnegative = 0.0
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
            raise ValueError("重心水平投影偏离两吊点连线，两根竖向吊索无法维持所设水平姿态。")
        share = ((gx-a[0])*dx + (gy-a[1])*dy) / span**2
        if not 0 < share < 1:
            raise ValueError("重心水平投影须在两吊点之间，两侧均须受拉。")
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


class RouteTooLong(ValueError):
    """The required subdivisions exceed the supported route length."""


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
            raise RouteTooLong("轨迹过长，请拆分工况。")
        for i in range(count):
            yield (leg, (leg+i/count)/leg_count, (leg+(i+1)/count)/leg_count,
                   travel/count, turn/count, sweep/count)


def chart_rows(crane, repo, cache):
    key = (crane.brand, crane.model, crane.config, crane.boom)
    if key not in cache:
        rows = [r for r in repo.model_capacity(crane.brand, crane.model)
                if r["config_name"] == crane.config and r["boom_len"] == crane.boom]
        cache[key] = sorted(rows, key=lambda r: r["radius"])
    return cache[key]


def analyze(case, repo, *, chart_cache=None, diagnostics=False):
    """Check loads, working radii and horizontal clearances along the transfer."""
    shares = case.shares()
    boxes = [c.box for c in case.cranes]
    stationary = []
    fixed_gap = (boxes[0].distance(boxes[1]), "A 机占地包络 / B 机占地包络")
    if fixed_gap[0] <= 0:
        stationary.append("两台起重机的占地包络相交")
    for j,box in enumerate(boxes):
        for k, disk in enumerate(case.obstacles):
            distance = clearance(box,box.pose,disk)
            pair = f"{'AB'[j]} 机占地包络 / 障碍物 {k+1} 禁入区"
            fixed_gap = min(fixed_gap, (distance, pair))
            if distance <= 0:
                stationary.append(f"{pair} 接触或相交")
    if 0 < fixed_gap[0] < case.plan_clearance:
        stationary.append(fixed_gap[1]+" 水平净距不足")
    if chart_cache is None:
        chart_cache = {}
    charts = []
    loads = []
    for crane, share in zip(case.cranes, shares):
        charts.append(chart_rows(crane, repo, chart_cache))
        loads.append((case.mass*share + crane.rigging)*case.factor + crane.hook)

    segments = []
    critical = None
    pending = [(interval, 0) for interval in route_intervals(case)]
    interval_count = len(pending)
    pending.reverse()
    while pending:
        (leg, start, end, travel, turn, sweep), depth = pending.pop()
        mid = (start+end)/2
        pose = case.pose(mid)
        times = (start, mid, end)
        unsafe, unknown = stationary.copy(), []
        evidence = {}

        def explain(reason, text, progress=None):
            if diagnostics:
                evidence[reason] = dict(text=text, progress=progress)

        if diagnostics:
            for reason in stationary:
                explain(reason, "两台起重机的站位在转运过程中固定。", 0.0)
        ratios = []
        radius_bounds = []
        hooks = [world(pose, lug) for lug in case.lugs]
        for j, (crane, lug, rows, gross) in enumerate(zip(case.cranes, case.lugs, charts, loads)):
            tag = "AB"[j]
            radius = math.dist(world(pose, lug), crane.center)
            delta = (travel + turn*math.hypot(*lug))/2
            radii = [r["radius"] for r in rows]
            if gross-crane.hook > crane.hook_rating:
                reason = f"{tag} 机主吊钩组承载超限"
                unsafe.append(reason)
                explain(reason, f"吊物分担质量及吊索具经系数放大后为 {gross-crane.hook:.2f} t，主吊钩组额定起重量 {crane.hook_rating:.2f} t。", 0.0)
            witness = [math.dist(world(case.pose(t), lug), crane.center) for t in times]
            if not rows or min(witness) < radii[0] or max(witness) > radii[-1]:
                reason = f"{tag} 机工作幅度无性能表数据"
                unknown.append(reason)
                if diagnostics:
                    if not rows:
                        explain(reason, f"当前工况没有 {crane.boom:g} m 臂长的起重性能表数据。")
                    else:
                        time, r = next((t, r) for t, r in zip(times, witness) if not radii[0] <= r <= radii[-1])
                        explain(reason, f"工作幅度 {r:.2f} m，表列工作幅度范围 {radii[0]:g}–{radii[-1]:g} m。", time)
            lower, upper = radius-delta, radius+delta
            # Translation is linear. Only the rotating lug departs from its
            # endpoint chord, by at most max|p''(t)|/8 on this interval.
            upper = min(upper, max(witness[0], witness[-1])+math.hypot(*lug)*turn**2/8)
            if crane.radius_limit is not None:
                if max(witness) > crane.radius_limit + 1e-9:
                    reason = f"{tag} 机超过指定工作幅度上限"
                    unsafe.append(reason)
                    peak = max(witness)
                    explain(reason, f"工作幅度 {peak:.2f} m，指定上限 {crane.radius_limit:.2f} m。", times[witness.index(peak)])
                elif upper > crane.radius_limit + 1e-9:
                    reason = f"{tag} 机工作幅度上限待核"
                    unknown.append(reason)
                    explain(reason, f"区间工作幅度上界 {upper:.2f} m，指定上限 {crane.radius_limit:.2f} m。")
            if rows and (lower < radii[0] or upper > radii[-1]):
                unknown.append(f"{tag} 机工作幅度包络超出性能表范围")
            radius_bounds.append((max(0, lower), upper))
            bucket = rows[bisect_left(radii, lower):bisect_left(radii, upper)+1]
            if any(r["rated_load"] <= 0 for r in bucket):
                unknown.append(f"{tag} 机区间内缺有效额定起重量")
            ratio = max((gross/r["rated_load"] for r in bucket if r["rated_load"] > 0), default=None)
            ratios.append(ratio)
            overload = f"{tag} 机起重性能表负荷率超限"
            for time, r in zip(times, witness):
                k = bisect_left(radii, r)
                if rows and radii[0] <= r and k < len(rows) and gross > rows[k]["rated_load"]*DUAL_LIMIT:
                    unsafe.append(overload)
                    rated = rows[k]["rated_load"]
                    if diagnostics:
                        detail = (f"负荷率 {gross/rated:.1%}，上限 {DUAL_LIMIT:.0%}。" if rated > 0
                                  else "该工况缺有效额定起重量。")
                        explain(overload, f"工作幅度 {r:.2f} m，采用表列工作幅度 {radii[k]:g} m。计算总起重量 {gross:.2f} t，"
                                f"表列额定总起重量 {rated:.2f} t。{detail}", time)
                    break
            if ratio is not None and ratio > DUAL_LIMIT and overload not in unsafe:
                reason = f"{tag} 机区间内负荷率可能超限"
                unknown.append(reason)
                if diagnostics:
                    explain(reason, f"区间涉及表列工况的最高负荷率 {ratio:.1%}，上限 {DUAL_LIMIT:.0%}。")
        witnesses = (case.pose(start), pose, case.pose(end))
        gaps = [(f"{'AB'[j]} 机占地包络", [box.separation(p,case.length,case.width) for p in witnesses])
                for j,box in enumerate(boxes)]
        gaps += [(f"障碍物 {j+1} 禁入区", [clearance(case,p,disk) for p in witnesses])
                 for j,disk in enumerate(case.obstacles)]
        lower_gap = fixed_gap
        for label, distances in gaps:
            lower_gap = min(lower_gap, (distances[1]-sweep/2, "吊物 / "+label))
            closest = min(distances)
            if closest <= 0:
                reason = f"吊物与{label}接触或相交"
                unsafe.append(reason)
                explain(reason, f"吊物水平投影与{label}接触或相交。", times[distances.index(closest)])
            elif label.startswith("障碍") and closest < case.plan_clearance:
                reason = f"吊物 / {label} 水平净距不足"
                unsafe.append(reason)
                explain(reason, f"采样净距 {closest:.3f} m，小于要求 {case.plan_clearance:.3f} m。",
                        times[distances.index(closest)])
            elif distances[1] <= sweep/2:
                unknown.append(f"吊物 / {label} 区间水平净距待核")
        for j, crane in enumerate(case.cranes):
            movement = (travel + turn*math.hypot(*case.lugs[j]))/2
            start_xy,end_xy = crane.center,hooks[j]
            gaps = [(f"{'AB'[1-j]} 机占地包络",boxes[1-j].segment_distance(start_xy,end_xy))]
            gaps += [(f"障碍物 {k+1} 禁入区", point_segment(disk[:2],start_xy,end_xy)-disk[2])
                     for k,disk in enumerate(case.obstacles)]
            for label, dist in gaps:
                gap = dist-crane.boom_buffer
                lower_gap = min(lower_gap, (gap-movement, "AB"[j]+" 起重臂水平投影 / "+label))
                if 0 < gap < case.plan_clearance:
                    reason = f"{'AB'[j]} 机起重臂水平投影 / {label} 水平净距不足"
                    unsafe.append(reason)
                    explain(reason, f"臂包络净距 {gap:.3f} m，小于要求 {case.plan_clearance:.3f} m。", mid)
                if gap <= movement:
                    if gap <= 0:
                        reason = f"{'AB'[j]} 机起重臂水平投影包络与{label}接触或相交"
                        unsafe.append(reason)
                        explain(reason, "该轨迹位置的水平净距为零或负值。", mid)
                    else:
                        unknown.append(f"{'AB'[j]} 机起重臂水平投影 / {label} 区间水平净距待核")
        c1,c2 = case.cranes
        gap = segment_gap(c1.center,hooks[0],c2.center,hooks[1])-c1.boom_buffer-c2.boom_buffer
        boom_bound = gap - (2*travel+turn*sum(math.hypot(*p) for p in case.lugs))/2
        lower_gap = min(lower_gap, (boom_bound, "A 机起重臂水平投影 / B 机起重臂水平投影"))
        if boom_bound <= 0:
            unknown.append("两台起重机的起重臂水平投影可能重叠，须校核三维净距")
        bound, pair = lower_gap
        # A midpoint sweep bound can straddle the requested clearance even
        # when the geometry has room. Recheck both halves before classifying.
        # Measured conflicts and fixed gaps cannot be resolved by subdivision.
        threshold = case.plan_clearance
        unresolved = bound <= 0 or bound < threshold
        if (unresolved and depth < 3 and interval_count < 5000 and sweep > 0
                and fixed_gap[0] > 0 and fixed_gap[0] >= threshold
                and bound + sweep >= threshold
                and not any("相交" in msg or "净距不足" in msg for msg in unsafe)):
            interval_count += 1
            for left,right in ((mid,end),(start,mid)):
                pending.append(((leg,left,right,travel/2,turn/2,sweep/2), depth+1))
            continue
        if 0 < case.plan_clearance and bound < case.plan_clearance and not any(
                pair in msg and "净距不足" in msg for msg in unsafe):
            reason = pair+" 未证实达到要求的水平净距"
            unknown.append(reason)
            explain(reason, f"此段净距下界 {max(0, bound):.3f} m，要求 {case.plan_clearance:.3f} m。")
        if critical is None or bound < critical["lower_m"]:
            critical = dict(lower_m=bound, pair=pair, leg=leg+1, start=start, end=end)
        segment = dict(leg=leg+1, start=start, end=end, ratios=ratios, radii=radius_bounds,
                       unsafe=unsafe, unknown=list(dict.fromkeys(unknown)))
        if diagnostics and evidence:
            segment["evidence"] = evidence
        segments.append(segment)
    # Zero means no positive clearance was established, not measured penetration.
    critical["lower_m"] = max(0.0, critical["lower_m"])
    return dict(shares=shares, loads=loads, segments=segments, clearance=critical)


def station_shift(crane, obstacles, heading, clearance_m, low, high):
    """Nearest longitudinal shift outside the clearance-inflated disk intervals."""
    c,s = math.cos(heading),math.sin(heading)
    forbidden = []
    for x,y,r in obstacles:
        dx,dy = x-crane.center[0],y-crane.center[1]
        along = dx*c + dy*s
        outside = max(0, abs(-dx*s+dy*c) - crane.footprint_width/2)
        padding = r + clearance_m
        if outside > padding:
            continue
        half = crane.footprint_length/2 + math.sqrt(max(0, padding**2-outside**2))
        forbidden.append((along-half, along+half))
    # Merge overlapping intervals before choosing the closest exit: clearing
    # the first obstacle alone may move the footprint into the next one.
    merged = []
    for a,b in sorted(forbidden):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0],max(merged[-1][1],b))
        else:
            merged.append((a,b))
    for left,right in merged:
        if left < 0 < right:
            choices = [v for v in (left,right) if low <= v <= high]
            return min(choices,key=abs) if choices else None
    return 0.


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
    travel = math.dist(case.start[:2], case.end[:2])
    stagger = min(travel, math.dist(a,b), *(cr.footprint_length for cr in case.cranes))/4
    for fraction in (.5,.35,.65):
        mid = [case.start[i]+fraction*(case.end[i]-case.start[i]) for i in (0,1)]
        for margin in (.35,1.5):
            pair = []
            for j,crane in enumerate(case.cranes):
                offset = (case.width/2+crane.footprint_width/2+case.plan_clearance+margin)*sign*(-1 if j==0 else 1)
                xy = tuple(mid[i]+offset*normal[i] for i in (0,1))
                pair.append(crane.model_copy(update={"center":xy,"heading":math.degrees(heading)}))
            yield tuple(pair)
            offsets = []
            if case.obstacles:
                shifts = [station_shift(cr,case.obstacles,heading,case.plan_clearance+.12,
                                        -fraction*travel,(1-fraction)*travel) for cr in pair]
                if None not in shifts and any(shifts):
                    offsets.append(tuple(shifts))
            # Try both lead/lag orders at the corridor midpoint. Moving the
            # pair together can leave one footprint blocked in either direction.
            if fraction == .5 and stagger > 1e-9:
                offsets.extend(((stagger,-stagger),(-stagger,stagger)))
            for shifts in dict.fromkeys(offsets):
                yield tuple(cr.model_copy(update={"center": (cr.center[0]+offset*c,
                                                             cr.center[1]+offset*s)})
                            for cr,offset in zip(pair,shifts))


def interpolate_hook(crane, lug, start, end, t):
    """Interpolate master-hook radius and unwrapped slew, then recover the body centre."""
    def polar(pose):
        angle = math.radians(pose[2])
        x,y = world((*pose[:2],math.cos(angle),math.sin(angle)),lug)
        dx,dy = x-crane.center[0],y-crane.center[1]
        return math.hypot(dx,dy),math.atan2(dy,dx)
    r0,a0 = polar(start)
    r1,a1 = polar(end)
    radius = r0 + t*(r1-r0)
    azimuth = a0 + t*math.remainder(a1-a0,2*math.pi)
    yaw = start[2] + t*(end[2]-start[2])
    rad = math.radians(yaw)
    ox,oy = world((0,0,math.cos(rad),math.sin(rad)),lug)
    return (crane.center[0]+radius*math.cos(azimuth)-ox,
            crane.center[1]+radius*math.sin(azimuth)-oy, yaw)


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
    boxes = [cr.box for cr in case.cranes]
    # Width of the passage along the line of centres, accounting for headings.
    def normal_projection(p):
        return (p[0]-mid[0])*nx + (p[1]-mid[1])*ny
    lower = max(map(normal_projection, boxes[0].corners))
    upper = min(map(normal_projection, boxes[1].corners))
    room = upper-lower-case.width
    if room <= 0:
        return
    gate = (lower+upper)/2
    depth = max(abs((x-mid[0])*ux+(y-mid[1])*uy) for box in boxes for x,y in box.corners)
    reach = depth + math.hypot(case.length,case.width)/2 + 0.35
    # A yaw allowance from the transverse projection of a rigid vehicle.
    slack_angle = math.degrees(math.asin(min(1,room/case.length)))
    def point(along, across, yaw):
        return (mid[0]+along*ux+across*nx,mid[1]+along*uy+across*ny,yaw)

    def blend(a,b,t):
        return tuple(x+t*(y-x) for x,y in zip(a,b))

    # Use the clear strip between the two footprint projections to seed
    # oblique crossings. This is sufficient geometry for a candidate only;
    # all connections, load charts and boom envelopes are checked downstream.
    span = upper-lower-2*case.plan_clearance
    diagonal = math.hypot(case.length,case.width)
    if span > case.width:
        yaw_limit = (math.pi/2 if span >= diagonal else
                     math.asin(span/diagonal)-math.atan2(case.width,case.length))
        for sign in (-1,1):
            for fraction in (.45,.85):
                tilt = sign*fraction*yaw_limit
                side_room = (span-case.length*abs(math.sin(tilt))-case.width*math.cos(tilt))/2
                # Centre travel and body yaw can be oblique independently.
                for drift in (-.8*side_room, .8*side_room):
                    for axis in (angle, angle+(180 if angle<case.start[2] else -180)):
                        yaw = axis+math.degrees(tilt)
                        entry = point(-depth,gate-drift,yaw)
                        departure = point(depth,gate+drift,yaw)
                        yield [entry,departure]
                        yield [point(-reach,gate-drift,yaw),entry,departure,
                               point(reach,gate+drift,yaw)]

    for axis in (angle, angle+(180 if angle<case.start[2] else -180)):
        for direction in (1,-1):
            for fraction in (.65,.28):
                skew = direction*min(32,slack_angle*fraction)
                bend = direction*min(room*.13,case.width/2)
                entry = point(-reach,gate-bend,axis+skew)
                exit_pose = point(reach,gate+bend,axis+skew)
                throat = []
                for j in range(1,9):
                    t = j/8
                    across = gate + bend*(2*t-1 + .55*math.sin(2*math.pi*t))
                    throat.append(point(reach*(2*t-1),across,
                                        axis+skew*(1-.65*math.sin(math.pi*t))))
                # Try either master hook on approach, exchanging roles at the exit.
                # The other hook follows the rigid body. All chords are rechecked.
                for master in (0,1):
                    approach = [interpolate_hook(case.cranes[master],case.lugs[master],
                                                 case.start,entry,j/6) for j in range(1,7)]
                    other = 1-master
                    departing = [interpolate_hook(case.cranes[other],case.lugs[other],
                                                  exit_pose,case.end,j/6) for j in range(1,6)]
                    yield approach + throat + departing

                def swing(start,end,sign,steps):
                    pivot = point(sign*(reach+case.width*.5),gate,(start[2]+end[2])/2)
                    return [blend(blend(start,pivot,t),blend(pivot,end,t),t) for t in steps]
                yield (swing(case.start,entry,-1,[j/6 for j in range(1,7)]) + throat
                       + swing(exit_pose,case.end,1,[j/6 for j in range(1,6)]))


def hook_motion_cost(case):
    """Planar actuator travel equivalent: radial change and arc travel at each hook."""
    total = 0.0
    previous = None
    steps = 4*(len(case.route)-1)
    for i in range(steps+1):
        pose = case.pose(i/steps)
        current = []
        for crane,lug in zip(case.cranes,case.lugs):
            x,y = world(pose,lug)
            dx,dy = x-crane.center[0],y-crane.center[1]
            current.append((math.hypot(dx,dy),math.atan2(dy,dx)))
        if previous is not None:
            for (r,a),(s,b) in zip(previous,current):
                slew = abs(math.remainder(b-a,2*math.pi))
                total += abs(s-r) + (r+s)/2*slew
        previous = current
    return total


def candidate_rank(segments, min_gap, motion):
    """Classify the evidence first; optimize only within each class."""
    unsafe = {msg for seg in segments for msg in seg["unsafe"]}
    unknown = {msg for seg in segments for msg in seg["unknown"]}
    severity = 2 if unsafe else (1 if unknown else 0)
    peak = max((r for seg in segments for r in seg["ratios"] if r is not None), default=math.inf)
    peaks = sorted((max(s["radii"][i][1] for s in segments) for i in (0, 1)), reverse=True)
    return severity, len(unsafe), len(unknown), *peaks, peak, -min_gap, motion


class TransferSearchError(ValueError):
    def __init__(self, reasons):
        super().__init__("在本次有限搜索范围内未找到满足连续避碰、指定工作幅度上限及水平净距的路径。")
        self.reasons = tuple(reasons)


def cargo_obstruction(case, boxes, pose):
    for tag, box in zip("AB", boxes):
        if box.separation(pose, case.length, case.width) <= 0:
            return f"{tag} 机占地包络"
    for index, obstacle in enumerate(case.obstacles, 1):
        if clearance(case, pose, obstacle) <= 0:
            return f"障碍物 {index} 禁入区"
    return None


def plan_transfer(case, repo, *, diagnostics=False):
    """Bounded corridor search, with continuous interval checks on each finalist."""
    if not (case.auto_route or case.auto_stations):
        return case, analyze(case,repo,diagnostics=diagnostics)
    from liftcalc.crane.transfer_search import improve_clearance, lattice_routes

    loads = [(case.mass*share+c.rigging)*case.factor+c.hook
             for c,share in zip(case.cranes, case.shares())]
    heading = math.atan2(case.end[1]-case.start[1], case.end[0]-case.start[0])
    best = None
    chart_cache = {}
    rejected = {}
    endpoints = [(world(case.pose(0),lug),world(case.pose(1),lug)) for lug in case.lugs]
    endpoint_reasons = []
    for time, name in ((0, "起吊"), (1, "落位")):
        for index, disk in enumerate(case.obstacles, 1):
            gap = clearance(case, case.pose(time), disk)
            if gap <= 0:
                endpoint_reasons.append(f"{name}姿态的吊物与障碍物 {index} 禁入区接触或相交。")
            elif gap < case.plan_clearance:
                endpoint_reasons.append(f"{name}姿态的吊物至障碍物 {index} 禁入区的水平净距 {gap:.3f} m，"
                                        f"小于要求 {case.plan_clearance:.3f} m。")
    if endpoint_reasons:
        raise TransferSearchError(endpoint_reasons)
    for pair in candidate_stations(case,heading):
        layout = case.model_copy(update={"cranes":pair})
        boxes = [cr.box for cr in pair]
        fixed_gap, fixed_pair = min([(boxes[0].distance(boxes[1]), "A 机占地包络 / B 机占地包络")] + [
            (clearance(box,box.pose,o), f"{tag} 机占地包络 / 障碍物 {index} 禁入区")
            for tag,box in zip("AB",boxes) for index,o in enumerate(case.obstacles,1)
        ])
        if fixed_gap <= 0 or fixed_gap < case.plan_clearance:
            reason = (f"{fixed_pair} 接触或相交。" if fixed_gap <= 0 else
                      f"{fixed_pair} 净距 {fixed_gap:.3f} m，小于要求 {case.plan_clearance:.3f} m。")
            rejected.setdefault("station", reason)
            continue
        # Every possible route at these stations has the same end poses.
        lower_bounds = [max(math.dist(cr.center,p) for p in ends)
                        for cr,ends in zip(pair,endpoints)]
        endpoint_limit = next(((tag, r, cr.radius_limit, "起吊" if math.dist(cr.center, ends[0]) >= r else "落位")
                               for tag,cr,r,ends in zip("AB",pair,lower_bounds,endpoints)
                               if cr.radius_limit is not None and r > cr.radius_limit + 1e-9), None)
        if endpoint_limit:
            tag, radius, limit, phase = endpoint_limit
            rejected.setdefault("endpoint-radius", f"{phase}时 {tag} 机工作幅度 {radius:.2f} m，超过指定上限 {limit:.2f} m。")
            continue
        if best is not None and best[0][0] == 0 and max(lower_bounds) > best[0][3] + 1e-9:
            continue
        charts = [chart_rows(crane, repo, chart_cache) for crane in pair]
        free_routes = (route for refinement in (1, 1.5, 2)
                       for route in lattice_routes(layout, charts, loads, DUAL_LIMIT,
                                                   refinement=refinement))
        for waypoints in chain(candidate_routes(layout), free_routes):
            path = layout.model_copy(update={"waypoints":waypoints})
            # Cheap collision rejection before evaluating the entire load chart.
            samples = max(8,8*(len(waypoints)+1))
            obstruction = next(((t/samples, label) for t in range(samples+1)
                                if (label := cargo_obstruction(path,boxes,path.pose(t/samples)))), None)
            if obstruction:
                progress, label = obstruction
                rejected.setdefault("collision", f"候选路径 {progress:.1%} 处，吊物与{label}接触或相交。")
                continue
            result = analyze(path,repo,chart_cache=chart_cache)
            critical = result["clearance"]
            min_gap = critical["lower_m"]
            if min_gap <= 0 or min_gap < case.plan_clearance:
                required = (f"要求 {case.plan_clearance:.3f} m" if case.plan_clearance else "未证实有正净距")
                rejected.setdefault("clearance", f"候选 P{critical['leg']-1} → P{critical['leg']}，"
                                    f"{critical['start']:.1%}–{critical['end']:.1%}：{critical['pair']} "
                                    f"净距下界 {min_gap:.3f} m，{required}。")
                continue
            breach = next(((tag, c.radius_limit, s, i) for i,(tag,c) in enumerate(zip("AB",pair))
                           if c.radius_limit is not None for s in result["segments"]
                           if s["radii"][i][1] > c.radius_limit + 1e-9), None)
            if breach:
                tag, limit, segment, index = breach
                rejected.setdefault("route-radius", f"候选路径 {segment['start']:.1%}–{segment['end']:.1%}，"
                                    f"{tag} 机工作幅度上界 {segment['radii'][index][1]:.2f} m，指定上限 {limit:.2f} m。")
                continue
            rank = candidate_rank(result["segments"],min_gap,hook_motion_cost(path))
            if best is None or rank < best[0]:
                best = rank,path,result
    if best is None:
        raise TransferSearchError(tuple(rejected.values()) or ("本次搜索没有生成可校核的路径候选。",))
    path, result = improve_clearance(best[1], best[2], repo, chart_cache)
    if diagnostics:
        result = analyze(path, repo, chart_cache=chart_cache, diagnostics=True)
    return path, result
