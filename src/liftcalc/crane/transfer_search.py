"""Bounded minimax search in the planar rigid-body configuration space."""
from __future__ import annotations

import heapq
import math
from bisect import bisect_left
from functools import lru_cache

from liftcalc.crane.transfer import RouteTooLong, analyze, clearance, point_segment, segment_gap, world


def lattice_routes(case, charts, loads, limit, *, refinement=1):
    """Generate grid paths; the caller certifies every interpolated interval."""
    origin = case.start
    dx, dy = case.end[0]-origin[0], case.end[1]-origin[1]
    distance = math.hypot(dx, dy)
    if abs(case.end[2]-origin[2]) > 360:
        return
    if distance == 0:
        ux, uy = 1.0, 0.0
    else:
        ux, uy = dx/distance, dy/distance
    spacing = max(0.6, case.width/2, distance/24) / refinement
    nx = max(1, math.ceil(distance/spacing))
    step = distance/nx if distance else spacing
    lateral = spacing
    # Keep the physical search corridor when decreasing the cell size.
    margin_cells = math.ceil(8*refinement)
    along_margin = min(margin_cells, max(2, math.ceil(case.length / max(step, 0.6/refinement))))
    angle_step = 15/refinement
    half_turn = round(180/angle_step)
    angle_steps = (math.floor((case.end[2]-origin[2])/angle_step),
                   math.ceil((case.end[2]-origin[2])/angle_step))
    angles = sorted({origin[2]+angle_step*i for i in range(min(-half_turn, angle_steps[0]), max(half_turn, angle_steps[1])+1)}
                    | {case.end[2]})
    start = (0, 0, angles.index(origin[2]))
    goal = (nx if distance else 0, 0, angles.index(case.end[2]))
    boxes = [c.box for c in case.cranes]
    columns = [[r["radius"] for r in chart] for chart in charts]

    def coordinates(node):
        x, y, k = node
        return (origin[0]+x*step*ux-y*lateral*uy,
                origin[1]+x*step*uy+y*lateral*ux, angles[k])

    @lru_cache(maxsize=None)
    def inspect(x, y, degrees):
        angle = math.radians(degrees)
        pose = (x, y, math.cos(angle), math.sin(angle))
        gap = case.plan_clearance + 0.12  # Leave room for the final swept-interval bound.
        if any(b.separation(pose, case.length, case.width) <= gap for b in boxes):
            return None
        if any(clearance(case, pose, o) <= gap for o in case.obstacles):
            return None
        hooks = [world(pose, p) for p in case.lugs]
        a, b = case.cranes
        if segment_gap(a.center, hooks[0], b.center, hooks[1]) <= gap+a.boom_buffer+b.boom_buffer:
            return None
        largest = 0.0
        covered = True
        fits = 0
        for i, (crane, hook) in enumerate(zip(case.cranes, hooks)):
            pad = gap+crane.boom_buffer
            if boxes[1-i].segment_distance(crane.center, hook) <= pad:
                return None
            if any(point_segment(o[:2], crane.center, hook) <= pad+o[2] for o in case.obstacles):
                return None
            radius = math.dist(crane.center, hook)
            if crane.radius_limit is not None and radius > crane.radius_limit:
                return None
            largest = max(largest, radius)
            rows = charts[i]
            k = bisect_left(columns[i], radius)
            inside = bool(rows) and columns[i][0]+0.11 <= radius <= columns[i][-1]-0.11
            covered = covered and inside
            if inside and loads[i] <= limit*rows[k]["rated_load"]:
                fits |= 1 << i
        return largest, fits if covered else -1

    def search(required):
        def allowed(sample):
            return sample is not None and (required is None or
                (sample[1] >= 0 and sample[1] & required == required))

        first = inspect(*coordinates(start))
        last = inspect(*coordinates(goal))
        if not allowed(first) or not allowed(last):
            return None
        # Extending a path can only increase its maximum required radius.
        # Endpoint peak is a lower bound shared by all complete paths.
        initial = (max(first[0], last[0]), 0)
        queue = [(*initial, start)]
        best = {start: initial}
        parent = {}
        expanded = 0
        directions = [(x,y,k) for x,y in ((1,0),(-1,0),(0,1),(0,-1),(0,0))
                      for k in (-1,0,1) if x or y or k]
        # A suspended body may also translate diagonally while keeping its yaw.
        directions.extend((x,y,0) for x in (-1,1) for y in (-1,1))
        while queue:
            peak, steps, node = heapq.heappop(queue)
            if (peak, steps) != best[node]:
                continue
            # Refinement supplements the coarse search and bounds desktop latency.
            expanded += 1
            if refinement > 1 and expanded > 12000:
                return None
            if node == goal:
                chain = [node]
                while chain[-1] != start:
                    chain.append(parent[chain[-1]])
                chain.reverse()
                # Merge collinear translations and same-sense in-place turns.
                bends = [b for a,b,c in zip(chain, chain[1:], chain[2:])
                         if (b[0]-a[0], b[1]-a[1], angles[b[2]]-angles[a[2]]) !=
                            (c[0]-b[0], c[1]-b[1], angles[c[2]]-angles[b[2]])]
                if len(bends) <= 30:
                    return [coordinates(n) for n in bends]
                return None
            x,y,k = node
            pose = coordinates(node)
            for sx,sy,sk in directions:
                nxt = (x+sx,y+sy,k+sk)
                if not (-along_margin <= nxt[0] <= nx+along_margin and abs(nxt[1]) <= margin_cells
                        and 0 <= nxt[2] < len(angles)):
                    continue
                other = coordinates(nxt)
                finish = inspect(*other)
                if not allowed(finish):
                    continue
                score = (max(peak, finish[0]), steps+1)
                if nxt in best and best[nxt] <= score:
                    continue
                middle = inspect(*((a+b)/2 for a,b in zip(pose,other)))
                if not allowed(middle):
                    continue
                score = (max(score[0], middle[0]), steps+1)
                if nxt not in best or score < best[nxt]:
                    best[nxt], parent[nxt] = score, node
                    heapq.heappush(queue, (*score,nxt))
        return None

    seen = set()
    for required in ((3,) if refinement > 1 else (3, 1, 2, 0, None)):
        route = search(required)
        if route is not None and tuple(route) not in seen:
            seen.add(tuple(route))
            yield route


def improve_clearance(path, result, repo, chart_cache):
    """Maximize the certified gap in a small graph around a verified route."""
    route = path.route
    segments = result["segments"]
    if len(route) < 3 or any(s["unsafe"] or s["unknown"] for s in segments):
        return path, result

    peak_radius = [max(s["radii"][i][1] for s in segments) for i in (0, 1)]
    for i, crane in enumerate(path.cranes):
        if crane.radius_limit is not None:
            peak_radius[i] = min(peak_radius[i], crane.radius_limit)
    peak_ratio = [max(s["ratios"][i] for s in segments) for i in (0, 1)]
    old_gap = result["clearance"]["lower_m"]

    def admissible(check):
        for s in check["segments"]:
            if s["unsafe"] or s["unknown"]:
                return False
            if any(s["radii"][i][1] > peak_radius[i] + 1e-9
                   or s["ratios"][i] > peak_ratio[i] + 1e-12 for i in (0, 1)):
                return False
        return check["clearance"]["lower_m"] >= old_gap - 1e-9

    # At each layer try the original waypoint and one pose moved halfway
    # toward the chord midpoint. Start, finish, stations and lugs stay fixed.
    layers = [[route[0]]]
    for a,b,c in zip(route,route[1:],route[2:]):
        rounded = tuple((x+2*y+z)/4 for x,y,z in zip(a,b,c))
        # Enter or leave a turn slightly earlier at the same XY position.
        early = (b[0], b[1], (b[2]+c[2])/2)
        late = (b[0], b[1], (a[2]+b[2])/2)
        layers.append(list(dict.fromkeys((b,rounded,early,late))))
    layers.append([route[-1]])

    # Best prefix to each vertex: widest bottleneck, then fewest legs.
    scores = {(0,0): (math.inf, 0)}
    parents = {}
    intervals_checked = 0
    for j in range(1,len(layers)):
        for k,end in enumerate(layers[j]):
            node = (j,k)
            for i in range(max(0,j-3),j):
                for h,start in enumerate(layers[i]):
                    prev = (i,h)
                    if prev not in scores:
                        continue
                    prefix_gap, neg_steps = scores[prev]
                    if node in scores and (prefix_gap, neg_steps-1) <= scores[node]:
                        continue
                    if intervals_checked >= 30000:
                        return path, result
                    edge = path.model_copy(update={"start":start,"end":end,"waypoints":[]})
                    try:
                        check = analyze(edge, repo, chart_cache=chart_cache)
                    except RouteTooLong:
                        continue
                    intervals_checked += len(check["segments"])
                    if not admissible(check):
                        continue
                    score = (min(prefix_gap, check["clearance"]["lower_m"]), neg_steps-1)
                    if node not in scores or score > scores[node]:
                        scores[node], parents[node] = score, prev

    node = (len(layers)-1,0)
    if node not in parents:
        return path, result
    waypoints = []
    while parents[node] != (0,0):
        node = parents[node]
        waypoints.append(layers[node[0]][node[1]])
    trial = path.model_copy(update={"waypoints":list(reversed(waypoints))})
    try:
        check = analyze(trial, repo, chart_cache=chart_cache)
    except RouteTooLong:
        return path, result
    if admissible(check) and check["clearance"]["lower_m"] > old_gap + 1e-9:
        return trial, check
    return path, result
