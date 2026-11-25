"""Horizontal two-hook rail transfer. All coordinates and clearances are in metres."""
from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
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
    config: str | None = None
    boom: Positive | None = None
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
        return route_pose(self.route, t)


def route_pose(route, t):
    offset = t * (len(route)-1)
    leg = min(int(offset), len(route)-2)
    u = offset - leg
    ax, ay, a_deg = route[leg]
    bx, by, b_deg = route[leg+1]
    angle = math.radians(a_deg + u*(b_deg-a_deg))
    return ax + u*(bx-ax), ay + u*(by-ay), math.cos(angle), math.sin(angle)


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
    px, py = p[0]-a[0], p[1]-a[1]
    t = (px*dx+py*dy)/length2
    if t <= 0:
        return math.hypot(px, py)
    if t > 1:
        t = 1
    return math.hypot(px-t*dx, py-t*dy)


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
        self.half_length, self.half_width = length/2, width/2
        self.corners = tuple(world(self.pose, (x*length/2,y*width/2))
                             for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)))

    def separation(self, pose, length, width):
        # Maximum separating-axis gap is a conservative lower bound on distance.
        x,y,c,s = pose
        bx,by,u,v = self.pose
        dx,dy = x-bx,y-by
        co,si = abs(c*u+s*v),abs(s*u-c*v)
        a,b = self.half_length,self.half_width
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
        # For disjoint shapes a nearest pair includes either a segment
        # endpoint or a rectangle corner, including when two edges are parallel.
        x,y,u,v = self.pose
        ax,ay = a[0]-x, a[1]-y
        bx,by = b[0]-x, b[1]-y
        hl, hw = self.half_length, self.half_width
        end_a = math.hypot(max(0.0, abs(ax*u+ay*v)-hl), max(0.0, abs(-ax*v+ay*u)-hw))
        end_b = math.hypot(max(0.0, abs(bx*u+by*v)-hl), max(0.0, abs(-bx*v+by*u)-hw))
        p0,p1,p2,p3 = self.corners
        return min(end_a, end_b, point_segment(p0,a,b), point_segment(p1,a,b),
                   point_segment(p2,a,b), point_segment(p3,a,b))

    def distance(self, other):
        if self.separation(other.pose,other.length,other.width)<=0:
            return 0.0
        return min(self.segment_distance(other.corners[i-1],p) for i,p in enumerate(other.corners))


class StationGeometry:
    """Fixed distances and bounded sample caches for one station pair."""

    def __init__(self, case):
        boxes = self.boxes = tuple(crane.box for crane in case.cranes)
        disks = tuple(case.obstacles)
        obstacles = tuple(f"障碍物 {i} 禁入区" for i in range(1, len(disks)+1))
        self.cargo_labels = ("A 机占地包络", "B 机占地包络", *obstacles)
        self.boom_labels = ((self.cargo_labels[1], *obstacles), (self.cargo_labels[0], *obstacles))
        fixed = [(boxes[0].distance(boxes[1]), "A 机占地包络 / B 机占地包络")]
        for box, label in zip(boxes, self.cargo_labels):
            fixed.extend((clearance(box, box.pose, disk), f"{label} / {name}")
                         for disk, name in zip(disks, obstacles))
        self.fixed_gap = min(fixed)
        stationary = ["两台起重机的占地包络相交"] if fixed[0][0] <= 0 else []
        stationary.extend(f"{pair} 接触或相交" for distance, pair in fixed[1:] if distance <= 0)
        if 0 < self.fixed_gap[0] < case.plan_clearance:
            stationary.append(self.fixed_gap[1] + " 水平净距不足")
        self.stationary = tuple(stationary)

        size = min(8192, 50000 // (len(disks)+2))
        center_a, center_b = (crane.center for crane in case.cranes)
        pad_a, pad_b = (crane.boom_buffer for crane in case.cranes)

        @lru_cache(maxsize=size)
        def cargo_gaps(pose):
            sides = (boxes[0].separation(pose, case.length, case.width),
                     boxes[1].separation(pose, case.length, case.width))
            if not disks:
                return sides
            return (*sides, *(clearance(case, pose, disk) for disk in disks))

        @lru_cache(maxsize=size)
        def boom_gaps(hooks):
            a, b = hooks
            side_a = (boxes[1].segment_distance(center_a, a) - pad_a,)
            side_b = (boxes[0].segment_distance(center_b, b) - pad_b,)
            if disks:
                side_a += tuple(point_segment(disk[:2], center_a, a) - disk[2] - pad_a for disk in disks)
                side_b += tuple(point_segment(disk[:2], center_b, b) - disk[2] - pad_b for disk in disks)
            mutual = segment_gap(center_a, a, center_b, b) - pad_a - pad_b
            return (side_a, side_b), mutual

        self.cargo_gaps = cargo_gaps
        self.boom_gaps = boom_gaps


class RouteTooLong(ValueError):
    """The required subdivisions exceed the supported route length."""


class _RouteClearanceRejected(ValueError):
    def __init__(self, bound, pair, leg, start, end, intervals_checked):
        self.bound = max(0.0, bound)
        self.pair = pair
        self.leg, self.start, self.end = leg, start, end
        self.intervals_checked = intervals_checked


def route_intervals(case, route):
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


@dataclass(frozen=True)
class LoadChart:
    config: str
    boom: float
    radii: tuple[float, ...]
    ratings: tuple[float, ...]


def automatic_charts(case, repo, cache):
    """Read each model once and keep each configuration/boom pair together."""
    models = {}
    options = []
    missing = []
    for tag, crane in zip("AB", case.cranes):
        if crane.config is not None and crane.boom is not None:
            options.append(None)
            continue
        model = crane.brand, crane.model
        if model not in models:
            groups = defaultdict(list)
            for row in repo.model_capacity(*model):
                groups[row["config_name"], row["boom_len"]].append(row)
            for key, rows in groups.items():
                cache[(*model, *key)] = sorted(rows, key=lambda row: row["radius"])
            models[model] = groups.keys()
        charts = []
        for config, boom in models[model]:
            if ((crane.config is not None and crane.config != config)
                    or (crane.boom is not None and crane.boom != boom)):
                continue
            rows = cache[(*model, config, boom)]
            charts.append(LoadChart(config, boom, tuple(row["radius"] for row in rows),
                                    tuple(row["rated_load"] for row in rows)))
        if not charts:
            name = f"{crane.brand} {crane.model}"
            if crane.config:
                name += f"（{crane.config}）"
            if crane.boom is not None:
                name += f" {crane.boom:g} m"
            missing.append(f"{tag} 机 {name} 没有可供自动选择的起重性能表数据。")
        options.append(charts)
    if missing:
        raise TransferSearchError(missing, "无法从起重性能表选出双机工况和臂长。")
    return options


def search_chart(crane, options, repo, cache):
    if options is None:
        return chart_rows(crane, repo, cache)
    # A pointwise upper envelope guides the lattice only. The final check
    # uses one real chart per crane for the entire route.
    radii = sorted({r for chart in options for r in chart.radii})
    return [
        dict(radius=r, rated_load=max(chart.ratings[bisect_left(chart.radii, r)]
                                      for chart in options if chart.radii[0] <= r <= chart.radii[-1]))
        for r in radii
    ]


def choose_chart(options, gross, samples):
    lower = min(bounds[0] for bounds, _ in samples)
    upper = max(bounds[1] for bounds, _ in samples)
    observed = sorted({r for _, witness in samples for r in witness})

    def rank(chart):
        radii, ratings = chart.radii, chart.ratings
        first, stop = bisect_left(radii, lower), bisect_left(radii, upper) + 1
        bucket = ratings[first:stop]
        ratio = max((gross / rating for rating in bucket if rating > 0), default=math.inf)
        covers = radii[0] <= lower and upper <= radii[-1] and all(r > 0 for r in bucket)
        uncovered = max(0.0, radii[0] - lower) + max(0.0, upper - radii[-1])
        if covers and ratio <= DUAL_LIMIT:
            return 0, False, uncovered, ratio, chart.boom, chart.config
        overload = False
        for k, rating in enumerate(bucket, first):
            if gross <= rating * DUAL_LIMIT:
                continue
            # A sampled radius selects this row only within its ceiling bin.
            i = bisect_right(observed, radii[k-1]) if k else bisect_left(observed, radii[0])
            if i < len(observed) and observed[i] <= radii[k]:
                overload = True
                break
        # Keep full-coverage overload evidence when the available shorter
        # charts would simply leave parts of the route without data.
        return (1 if covers else 2), overload, uncovered, ratio, chart.boom, chart.config

    return min(options, key=rank)


def check_chart(crane, tag, gross, rows, radii, bucket_check, bounds, witness, segment, diagnostics):
    lower, upper = bounds
    ratio, missing, overload_in_bucket = bucket_check(bisect_left(radii, lower), bisect_left(radii, upper)+1)
    segment["ratios"].append(ratio)
    covered = bool(rows) and radii[0] <= lower and upper <= radii[-1]
    observed_low, observed_high = min(witness), max(witness)
    if (covered and not missing and not overload_in_bucket and ratio is not None and ratio <= DUAL_LIMIT
            and lower <= observed_low <= observed_high <= upper):
        return

    unsafe, unknown = segment["unsafe"], segment["unknown"]
    times = (segment["start"], (segment["start"]+segment["end"])/2, segment["end"])

    def explain(reason, detail, progress=None):
        if diagnostics:
            segment.setdefault("evidence", {})[reason] = dict(text=detail, progress=progress)

    if not rows or observed_low < radii[0] or observed_high > radii[-1]:
        reason = f"{tag} 机工作幅度无性能表数据"
        unknown.append(reason)
        if diagnostics:
            if not rows:
                explain(reason, f"当前工况没有 {crane.boom:g} m 臂长的起重性能表数据。")
            else:
                time, r = next((t, r) for t, r in zip(times, witness) if not radii[0] <= r <= radii[-1])
                explain(reason, f"工作幅度 {r:.2f} m，表列工作幅度范围 {radii[0]:g}–{radii[-1]:g} m。", time)
    if rows and not covered:
        unknown.append(f"{tag} 机工作幅度包络超出性能表范围")
    if missing:
        unknown.append(f"{tag} 机区间内缺有效额定起重量")
    overload = f"{tag} 机起重性能表负荷率超限"
    for time, r in zip(times, witness):
        k = bisect_left(radii, r)
        if rows and radii[0] <= r and k < len(rows) and gross > rows[k]["rated_load"]*DUAL_LIMIT:
            unsafe.append(overload)
            if diagnostics:
                rated = rows[k]["rated_load"]
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


def analyze(case, repo, *, chart_cache=None, diagnostics=False, geometry=None, minimum_gap=None):
    """Check loads, working radii and horizontal clearances along the transfer."""
    cache = {} if chart_cache is None else chart_cache
    return assess_route(case, repo, cache, automatic_charts(case, repo, cache),
                        diagnostics=diagnostics, geometry=geometry, minimum_gap=minimum_gap)[1]


def assess_route(case, repo, chart_cache, options, *, diagnostics=False, geometry=None,
                 require_clearance=False, minimum_gap=None):
    """Measure the route once, then select and check its full-route load charts."""
    shares = case.shares()
    if geometry is None:
        geometry = StationGeometry(case)
    fixed_gap, stationary = geometry.fixed_gap, geometry.stationary
    loads = [(case.mass*share + crane.rigging)*case.factor + crane.hook
             for crane, share in zip(case.cranes, shares)]

    route = case.route
    lug_radii = tuple(math.hypot(*lug) for lug in case.lugs)
    lug_radius_sum = sum(lug_radii)
    lug_a, lug_b = case.lugs
    crane_a, crane_b = case.cranes

    @lru_cache(maxsize=2048)
    def sample(t):
        pose = route_pose(route, t)
        a, b = world(pose, lug_a), world(pose, lug_b)
        return geometry.cargo_gaps(pose), (a, b), (math.dist(a, crane_a.center), math.dist(b, crane_b.center))

    segments = []
    route_samples = []
    critical = None
    pending = [(interval, 0) for interval in route_intervals(case, route)]
    interval_count = len(pending)
    pending.reverse()
    while pending:
        (leg, start, end, travel, turn, sweep), depth = pending.pop()
        mid = (start+end)/2
        times = (start, mid, end)
        cargo_start, _, radii_start = sample(start)
        cargo_mid, hooks, radii_mid = sample(mid)
        cargo_end, _, radii_end = sample(end)
        unsafe, unknown = list(stationary), []
        evidence = {}

        def explain(reason, text, progress=None):
            if diagnostics:
                evidence[reason] = dict(text=text, progress=progress)

        if diagnostics:
            for reason in stationary:
                explain(reason, "两台起重机的站位在转运过程中固定。", 0.0)
        radius_bounds = []
        samples = []
        movements = []
        for j, (crane, lug_radius, gross) in enumerate(zip(case.cranes, lug_radii, loads)):
            tag = "AB"[j]
            delta = (travel + turn*lug_radius)/2
            movements.append(delta)
            if gross-crane.hook > crane.hook_rating:
                reason = f"{tag} 机主吊钩组承载超限"
                unsafe.append(reason)
                explain(reason, f"吊物分担质量及吊索具经系数放大后为 {gross-crane.hook:.2f} t，主吊钩组额定起重量 {crane.hook_rating:.2f} t。", 0.0)
            witness = (radii_start[j], radii_mid[j], radii_end[j])
            radius = witness[1]
            lower, upper = radius-delta, radius+delta
            # Translation is linear. Only the rotating lug departs from its
            # endpoint chord, by at most max|p''(t)|/8 on this interval.
            upper = min(upper, max(witness[0], witness[-1])+lug_radius*turn**2/8)
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
            radius_bounds.append((max(0, lower), upper))
            samples.append(((lower, upper), witness))
        lower_gap = fixed_gap
        for i, label in enumerate(geometry.cargo_labels):
            distances = (cargo_start[i], cargo_mid[i], cargo_end[i])
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
        boom_sides, mutual_gap = geometry.boom_gaps(hooks)
        for j, movement in enumerate(movements):
            for label, gap in zip(geometry.boom_labels[j], boom_sides[j]):
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
        boom_bound = mutual_gap - (2*travel+turn*lug_radius_sum)/2
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
        if (require_clearance and unresolved) or (minimum_gap is not None and max(0.0, bound) < minimum_gap):
            raise _RouteClearanceRejected(bound, pair, leg+1, start, end, len(segments)+1)
        if 0 < case.plan_clearance and bound < case.plan_clearance and not any(
                pair in msg and "净距不足" in msg for msg in unsafe):
            reason = pair+" 未证实达到要求的水平净距"
            unknown.append(reason)
            explain(reason, f"此段净距下界 {max(0, bound):.3f} m，要求 {case.plan_clearance:.3f} m。")
        if critical is None or bound < critical["lower_m"]:
            critical = dict(lower_m=bound, pair=pair, leg=leg+1, start=start, end=end)
        segment = dict(leg=leg+1, start=start, end=end, ratios=[], radii=radius_bounds,
                       unsafe=unsafe, unknown=list(dict.fromkeys(unknown)))
        if diagnostics and evidence:
            segment["evidence"] = evidence
        segments.append(segment)
        route_samples.append(samples)
    # Zero means no positive clearance was established, not measured penetration.
    critical["lower_m"] = max(0.0, critical["lower_m"])
    cranes = list(case.cranes)
    for i, charts in enumerate(options):
        if charts is None:
            continue
        chart = choose_chart(charts, loads[i], [samples[i] for samples in route_samples])
        cranes[i] = cranes[i].model_copy(update=dict(config=chart.config, boom=chart.boom))
    for j, (tag, crane, gross) in enumerate(zip("AB", cranes, loads)):
        rows = chart_rows(crane, repo, chart_cache)
        radii = tuple(row["radius"] for row in rows)
        ratings = tuple(row["rated_load"] for row in rows)

        @lru_cache(maxsize=512)
        def bucket_check(first, stop, ratings=ratings, gross=gross):
            bucket = ratings[first:stop]
            positive = tuple(rating for rating in bucket if rating > 0)
            weakest = min(positive, default=None)
            return (gross/weakest if weakest is not None else None, len(positive) != len(bucket),
                    weakest is not None and gross > weakest*DUAL_LIMIT)

        for segment, samples in zip(segments, route_samples):
            bounds, witness = samples[j]
            check_chart(crane, tag, gross, rows, radii, bucket_check, bounds, witness, segment, diagnostics)
    return (case.model_copy(update={"cranes": tuple(cranes)}),
            dict(shares=shares, loads=loads, segments=segments, clearance=critical))


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


def candidate_routes(case, *, boxes=None):
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
    if boxes is None:
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


def candidate_rank(segments, min_gap, motion, *, prefer_chart_coverage=False):
    """Classify the evidence first; optimize only within each class."""
    unsafe = {msg for seg in segments for msg in seg["unsafe"]}
    unknown = {msg for seg in segments for msg in seg["unknown"]}
    severity = 2 if unsafe else (1 if unknown else 0)
    if prefer_chart_coverage and any("性能表" in msg or "缺有效额定起重量" in msg for msg in unknown):
        severity = 3
    peak = max((r for seg in segments for r in seg["ratios"] if r is not None), default=math.inf)
    peaks = sorted((max(s["radii"][i][1] for s in segments) for i in (0, 1)), reverse=True)
    return severity, len(unsafe), len(unknown), *peaks, peak, -min_gap, motion


class TransferSearchError(ValueError):
    def __init__(self, reasons, summary="在本次有限搜索范围内未找到满足连续避碰、指定工作幅度上限及水平净距的路径。"):
        super().__init__(summary)
        self.reasons = tuple(reasons)


def endpoint_obstruction(case, geometry, poses, hook_pairs):
    """Check endpoint clearance upper bounds shared by every path at these stations."""
    for name, pose, hooks in zip(("起吊", "落位"), poses, hook_pairs):
        for label, gap in zip(geometry.cargo_labels, geometry.cargo_gaps(pose)):
            if gap <= 0:
                return f"{name}姿态的吊物与{label}接触或相交。"
        sides, mutual = geometry.boom_gaps(hooks)
        gaps = [(mutual, "A 机起重臂水平投影 / B 机起重臂水平投影")]
        for tag, labels, distances in zip("AB", geometry.boom_labels, sides):
            gaps.extend((gap, f"{tag} 机起重臂水平投影 / {label}") for label, gap in zip(labels, distances))
        gap, pair = min(gaps)
        if gap <= 0:
            return f"{name}时 {pair} 接触或相交。"
        if gap < case.plan_clearance - 1e-9:
            return f"{name}时 {pair} 的水平净距 {gap:.3f} m，小于要求 {case.plan_clearance:.3f} m。"
    return None


def dominated_overload(route, case, loads, chart_columns, incumbent):
    """Bound the rank from waypoints shared by all subdivisions of this route."""
    mandatory_overloads = [False, False]
    peak = 0.0
    legs = len(route)-1
    for step in range(legs+1):
        pose = route_pose(route, step/legs)
        for i, (lug, crane) in enumerate(zip(case.lugs, case.cranes)):
            radii, capacities = chart_columns[i]
            radius = math.dist(world(pose, lug), crane.center)
            if not radii or radius < radii[0]-1e-9 or radius > radii[-1]+1e-9:
                # Every real chart would lack coverage and rank below the incumbent.
                return True
            peak = max(peak, radius)
            k = bisect_left(radii, radius)
            if k < len(radii) and radius >= radii[0] and loads[i] > capacities[k]+1e-9:
                # The search table is an upper envelope over real tables.
                mandatory_overloads[i] = True
    count = sum(mandatory_overloads)
    return count > incumbent[1] or (count == incumbent[1] and peak > incumbent[3]+1e-9)


def plan_transfer(case, repo, *, diagnostics=False):
    """Bounded corridor search, with continuous interval checks on each finalist."""
    chart_cache = {}
    options = automatic_charts(case, repo, chart_cache)
    automatic = any(charts is not None for charts in options)
    if not (case.auto_route or case.auto_stations):
        return assess_route(case, repo, chart_cache, options, diagnostics=diagnostics)
    from liftcalc.crane.transfer_search import improve_clearance, lattice_routes

    loads = [(case.mass*share+c.rigging)*case.factor+c.hook
             for c,share in zip(case.cranes, case.shares())]
    heading = math.atan2(case.end[1]-case.start[1], case.end[0]-case.start[0])
    best = None
    rejected = {}
    endpoint_poses = case.pose(0), case.pose(1)
    endpoint_hooks = [tuple(world(pose, lug) for lug in case.lugs) for pose in endpoint_poses]
    endpoint_reasons = []
    for pose, name in zip(endpoint_poses, ("起吊", "落位")):
        for index, disk in enumerate(case.obstacles, 1):
            gap = clearance(case, pose, disk)
            if gap <= 0:
                endpoint_reasons.append(f"{name}姿态的吊物与障碍物 {index} 禁入区接触或相交。")
            elif gap < case.plan_clearance:
                endpoint_reasons.append(f"{name}姿态的吊物至障碍物 {index} 禁入区的水平净距 {gap:.3f} m，"
                                        f"小于要求 {case.plan_clearance:.3f} m。")
    if endpoint_reasons:
        raise TransferSearchError(endpoint_reasons)
    charts = [search_chart(crane, choices, repo, chart_cache) for crane, choices in zip(case.cranes, options)]
    chart_columns = [(tuple(row["radius"] for row in rows),
                      tuple(row["rated_load"] * DUAL_LIMIT for row in rows)) for rows in charts]
    for pair in candidate_stations(case,heading):
        layout = case.model_copy(update={"cranes":pair})
        geometry = StationGeometry(layout)
        fixed_gap, fixed_pair = geometry.fixed_gap
        if fixed_gap <= 0 or fixed_gap < case.plan_clearance:
            reason = (f"{fixed_pair} 接触或相交。" if fixed_gap <= 0 else
                      f"{fixed_pair} 净距 {fixed_gap:.3f} m，小于要求 {case.plan_clearance:.3f} m。")
            rejected.setdefault("station", reason)
            continue
        # Every possible route at these stations has the same end poses.
        endpoint_radii = [tuple(math.dist(cr.center, hook) for cr, hook in zip(pair, hooks))
                          for hooks in endpoint_hooks]
        lower_bounds = [max(radii) for radii in zip(*endpoint_radii)]
        endpoint_limit = next(((tag, r, cr.radius_limit, "起吊" if first >= r else "落位")
                               for tag,cr,r,first in zip("AB",pair,lower_bounds,endpoint_radii[0])
                               if cr.radius_limit is not None and r > cr.radius_limit + 1e-9), None)
        if endpoint_limit:
            tag, radius, limit, phase = endpoint_limit
            rejected.setdefault("endpoint-radius", f"{phase}时 {tag} 机工作幅度 {radius:.2f} m，超过指定上限 {limit:.2f} m。")
            continue
        if best is not None and best[0][0] == 0 and max(lower_bounds) > best[0][3] + 1e-9:
            continue
        endpoint_failure = endpoint_obstruction(layout, geometry, endpoint_poses, endpoint_hooks)
        if endpoint_failure:
            rejected.setdefault("endpoint-clearance", endpoint_failure)
            continue
        free_routes = (route for refinement in (1, 1.5, 2)
                       for route in lattice_routes(layout, charts, loads, DUAL_LIMIT,
                                                   refinement=refinement, boxes=geometry.boxes,
                                                   peak_cap=(best[0][3] + 1e-9
                                                             if best is not None and best[0][0] == 0 else math.inf)))
        for waypoints in chain(candidate_routes(layout, boxes=geometry.boxes), free_routes):
            path = layout.model_copy(update={"waypoints":waypoints})
            route = path.route
            incumbent = best[0][3] if best is not None and best[0][0] == 0 else None
            # Shared point samples reject collisions and prove when a verified
            # incumbent already has a smaller peak radius.
            samples = max(8,8*(len(waypoints)+1))
            rejected_early = True
            for step in range(samples+1):
                progress = step/samples
                pose = route_pose(route, progress)
                label = next((label for label, gap in zip(geometry.cargo_labels, geometry.cargo_gaps(pose))
                              if gap <= 0), None)
                if label:
                    rejected.setdefault("collision", f"候选路径 {progress:.1%} 处，吊物与{label}接触或相交。")
                    break
                if incumbent is not None and any(math.dist(world(pose, lug), crane.center) > incumbent + 1e-9
                                                 for lug, crane in zip(case.lugs, pair)):
                    break
            else:
                rejected_early = False
            if rejected_early:
                continue
            if (automatic and best is not None and best[0][0] == 2 and best[0][2] == 0
                    and dominated_overload(route, path, loads, chart_columns, best[0])):
                continue
            try:
                path, result = assess_route(path, repo, chart_cache, options,
                                            geometry=geometry, require_clearance=True)
            except _RouteClearanceRejected as exc:
                required = (f"要求 {case.plan_clearance:.3f} m" if case.plan_clearance else "未证实有正净距")
                rejected.setdefault("clearance", f"候选 P{exc.leg-1} → P{exc.leg}，"
                                    f"{exc.start:.1%}–{exc.end:.1%}：{exc.pair} "
                                    f"净距下界 {exc.bound:.3f} m，{required}。")
                continue
            min_gap = result["clearance"]["lower_m"]
            breach = next(((tag, c.radius_limit, s, i) for i,(tag,c) in enumerate(zip("AB",pair))
                           if c.radius_limit is not None for s in result["segments"]
                           if s["radii"][i][1] > c.radius_limit + 1e-9), None)
            if breach:
                tag, limit, segment, index = breach
                rejected.setdefault("route-radius", f"候选路径 {segment['start']:.1%}–{segment['end']:.1%}，"
                                    f"{tag} 机工作幅度上界 {segment['radii'][index][1]:.2f} m，指定上限 {limit:.2f} m。")
                continue
            rank = candidate_rank(result["segments"], min_gap, hook_motion_cost(path),
                                  prefer_chart_coverage=automatic)
            if best is None or rank < best[0]:
                best = rank,path,result,geometry
    if best is None:
        raise TransferSearchError(tuple(rejected.values()) or ("本次搜索没有生成可校核的路径候选。",))
    _, path, result, geometry = best
    path, result = improve_clearance(path, result, repo, chart_cache, geometry=geometry)
    if diagnostics:
        result = analyze(path, repo, chart_cache=chart_cache, diagnostics=True, geometry=geometry)
    return path, result
