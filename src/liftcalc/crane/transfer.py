"""Horizontal two-hook rail transfer. All coordinates and clearances are in metres."""
from __future__ import annotations

import math
from bisect import bisect_left
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

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
    exclusion: Positive
    hook: Positive
    hook_rating: Positive
    rigging: Nonnegative
    sling_height: Positive
    verified_height: Positive | None = None


class Transfer(Inputs):
    length: Positive
    width: Positive
    height: Positive
    mass: Positive
    cg: tuple[float, float, float]
    lugs: tuple[XY, XY]
    cranes: tuple[Crane, Crane]
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    gauge: Positive = 1.435
    bottom: Positive
    factor: Annotated[float, Field(ge=1)]
    obstacles: list[tuple[float, float, Positive]] = Field(default_factory=list, max_length=100)

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

    def pose(self, t):
        x, y, deg = (a + t*(b-a) for a, b in zip(self.start, self.end))
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


def analyze(case, repo):
    shares = case.shares()
    travel = math.dist(case.start[:2], case.end[:2])
    turn = abs(math.radians(case.end[2]-case.start[2]))
    speed = travel + turn*math.hypot(case.length, case.width)/2
    count = max(1, math.ceil(speed/.2), math.ceil(turn/math.radians(1)))
    if count > 5000:
        raise ValueError("轨迹过长，请分段校核。")
    disks = [(*c.center, c.exclusion) for c in case.cranes] + case.obstacles
    charts = []
    loads = []
    for crane, share in zip(case.cranes, shares):
        rows = [r for r in repo.model_capacity(crane.brand, crane.model)
                if r["config_name"] == crane.config and r["boom_len"] == crane.boom]
        charts.append(sorted(rows, key=lambda r: r["radius"]))
        loads.append((case.mass*share + crane.rigging)*case.factor + crane.hook)

    segments = []
    for i in range(count):
        mid = (i+.5)/count
        pose = case.pose(mid)
        unsafe, unknown = [], []
        ratios = []
        radius_bounds = []
        hooks = [world(pose, lug) for lug in case.lugs]
        for j, (crane, lug, rows, gross) in enumerate(zip(case.cranes, case.lugs, charts, loads)):
            tag = "AB"[j]
            radius = math.dist(world(pose, lug), crane.center)
            delta = (travel + turn*math.hypot(*lug))/(2*count)
            radii = [r["radius"] for r in rows]
            if gross-crane.hook > crane.hook_rating:
                unsafe.append(tag+"钩载超限")
            witness = [math.dist(world(case.pose(t), lug), crane.center)
                       for t in (i/count, mid, (i+1)/count)]
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
        for j, disk in enumerate(disks):
            label = ("AB"[j]+"机" if j < 2 else f"障碍{j-1}")
            gap = clearance(case, pose, disk)
            if min(gap, clearance(case, case.pose(i/count), disk),
                   clearance(case, case.pose((i+1)/count), disk)) <= 0:
                unsafe.append(label+"禁入区相交")
            elif gap <= speed/(2*count):
                unknown.append(label+"区间净距待核")
        # Moving endpoint bounds the displacement of the entire projected boom segment.
        for j, crane in enumerate(case.cranes):
            movement = (travel + turn*math.hypot(*case.lugs[j]))/(2*count)
            for k, disk in enumerate(disks):
                if k == j:
                    continue
                gap = point_segment(disk[:2], crane.center, hooks[j])-disk[2]-crane.boom_buffer
                if gap <= movement:
                    tag = "AB"[j] + "臂平面包络与" + ("AB"[k]+"机" if k<2 else f"障碍{k-1}") + "禁区"
                    (unsafe if gap <= 0 else unknown).append(tag+("相交" if gap <= 0 else "待核"))
        c1,c2 = case.cranes
        gap = segment_gap(c1.center,hooks[0],c2.center,hooks[1])-c1.boom_buffer-c2.boom_buffer
        if gap <= (2*travel+turn*sum(math.hypot(*p) for p in case.lugs))/(2*count):
            unknown.append("两臂投影可能交叠，须核三维净空")
        segments.append(dict(start=i/count, end=(i+1)/count, ratios=ratios, radii=radius_bounds,
                             unsafe=unsafe, unknown=list(dict.fromkeys(unknown))))
    return dict(shares=shares, loads=loads, segments=segments)
