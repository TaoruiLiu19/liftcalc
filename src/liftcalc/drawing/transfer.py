"""A3 vector sheets for a horizontal two-hook rail transfer."""
import math
from itertools import accumulate

from liftcalc.crane.transfer import Box, world
from liftcalc.drawing import dim
from liftcalc.drawing.body import BODY_MODEL_FRONT, MODEL_REAR, draw_truck, drawing_axles
from liftcalc.drawing.figures import (
    BLOCK_GAP, BLOCK_H, BOOM_HEAD_REACH, ElevationModel, _Paper, _draw_boom,
    _draw_hook_block, _draw_luffing_cylinder, _draw_rope,
)
from liftcalc.drawing.primitives import ALIGN_CENTER, ALIGN_RIGHT, Circle, Figure, Line, Polyline, Text
from liftcalc.drawing.sheet import Sheet, draw_frame, draw_ground, overlaps, title_block
from liftcalc.drawing.style import LAYER_TRACE_A, LAYER_TRACE_B, LAYER_TRACE_CENTER, LAYER_TRACE_GATE, SCALE_LADDER


def drawing(title, number, max_scale, kind):
    page = Sheet(420, 297)
    denominator = next((n for n in SCALE_LADDER if 1000/n <= max_scale),
                       max(500, math.ceil(1000/max_scale/50)*50))
    fig = Figure(title, page.width, page.height)
    fig.meta["kind"] = kind
    draw_frame(fig, page)
    title_block(fig, page, title=title, subtitle="A3", scale_text=f"1:{denominator}",
                drawing_no=f"DT-0{number}", project="列车双机上轨", date="", sheet_no=f"{number}/4")
    return fig, 1000/denominator


def cross(fig, x, y, r):
    fig.add(Line(x-r,y,x+r,y,"CENTER"), Line(x,y-r,x,y+r,"CENTER"))


def statics(case, result, corners):
    a,b = case.lugs
    span = math.dist(a,b)
    ux,uy = (b[0]-a[0])/span,(b[1]-a[1])/span
    def station(p):
        return ux*p[0]+uy*p[1]
    half = max(station(p) for p in corners)
    hook_z = [case.bottom+case.height+c.sling_height for c in case.cranes]
    fig,k = drawing("双机抬吊静力图", 1, min(275/(2*half), 193/case.length,
                                             72/max(hook_z), 56/case.width), "statics")
    def x(p):
        return 216+k*station(p)
    ground = 187
    y0 = ground+k*case.bottom
    y1 = y0+k*case.height
    left,right = 216-k*half,216+k*half
    fig.add(Text(36,281,"沿 AB 方向投影 · 水平吊运姿态",height=4),
            Line(left-14,ground,right+14,ground,"THIN"),
            Polyline(((left,y0),(right,y0),(right,y1),(left,y1))))
    for j,p in enumerate((a,b)):
        tag = "AB"[j]
        top = ground+k*hook_z[j]
        fig.add(Line(x(p),y1,x(p),top,"RIGGING"),Circle(x(p),top,1.6),
                Text(x(p)+2,top+4,tag+" 钩",height=3),
                Circle(x(p),y1,1.2),Text(x(p)+2,y1+3,"F"+tag,height=3))
        dim.arrow(fig,x(p),y1+min(7,(top-y1)*.8),0,1,layer="RIGGING")
        side = "left" if j==0 else "right"
        offset = -1 if j==0 else 1
        edge = left if j==0 else right
        dim.v_dim(fig,y1,top,edge+offset*10,f"{case.cranes[j].sling_height:.2f} m",
                  ref_x=x(p),side=side)
        dim.v_dim(fig,ground,top,edge+offset*23,f"{tag} 钩高 {hook_z[j]:.2f} m",
                  ref_x=edge,side=side)
    gy = y0+k*(case.cg[2]+case.height/2)
    fig.add(Circle(x(case.cg),gy,1.5),Line(x(case.cg),gy,x(case.cg),gy-9,"RIGGING"),
            Text(x(case.cg)+2,gy-5,"W",height=3.2))
    dim.arrow(fig,x(case.cg),gy-9,0,-1,layer="RIGGING")
    dim.v_dim(fig,y0,y1,right+10,f"H={case.height:.2f} m",ref_x=right,side="right")
    dim.v_dim(fig,ground,y0,left-10,f"{case.bottom:.2f} m",ref_x=left)
    for tag,lug in zip("AB",(a,b)):
        dist = abs(station(lug)-station(case.cg))
        dim.h_dim(fig,x(lug),x(case.cg),175,f"{tag}G  {dist:.2f} m",ref_y=y0)
    dim.h_dim(fig,x(a),x(b),163,f"AB  {span:.2f} m",ref_y=y0)
    fig.add(Text(36,146,"吊点布置 · 顶视",height=4),
            Polyline(tuple((149+k*u,99+k*v) for u,v in corners)))
    pts = [(149+k*p[0],99+k*p[1]) for p in (a,b,case.cg)]
    fig.add(Line(*pts[0],*pts[1],"CENTER"))
    for name,(px,py) in zip("ABG",pts):
        fig.add(Circle(px,py,1.7),Text(px+2,py+4,name,height=3.2))
        cross(fig,px,py,3)
    dim.h_dim(fig,149-k*case.length/2,149+k*case.length/2,60,
              f"L  {case.length:.2f} m",ref_y=99-k*case.width/2)
    dim.v_dim(fig,99-k*case.width/2,99+k*case.width/2,149+k*case.length/2+7,
              f"B={case.width:.2f} m",ref_x=149+k*case.length/2,side="right")
    fig.add(Text(271,138,"点位坐标 / m",height=4),
            Text(271,129,"原点为车体形心，Z 向上",height=3))
    coordinates = [("点","X","Y","Z")]
    for name,p in zip("ABG",((*a,case.height/2),(*b,case.height/2),case.cg)):
        coordinates.append((name,*(f"{v:.2f} m" for v in p)))
    for i,values in enumerate(coordinates):
        row = 117-i*9
        for col,value in enumerate(values):
            fig.add(Text(271+col*26,row,value,height=3))
    fig.add(Text(271,72,"尺寸单位  m",height=3),
            Text(271,63,f"车底离地  {case.bottom:.2f} m",height=3))
    for i,fraction in enumerate((*result["shares"],1)):
        fig.add(Text(35+i*69,28,f"{('FA','FB','W')[i]}  {case.mass*9.80665*fraction:.2f} kN",height=3.5))
    return fig


def first_gate_crossing(case):
    """First side change across the finite segment joining the slew centres."""
    a,b = (crane.center for crane in case.cranes)
    length = math.dist(a,b)
    if length < 1e-9:
        return None
    tx,ty = (b[0]-a[0])/length, (b[1]-a[1])/length
    nx,ny = ty,-tx
    route = case.route
    previous_side = 0
    for i,(p,q) in enumerate(zip(route,route[1:])):
        d = (p[0]-a[0])*nx+(p[1]-a[1])*ny
        e = (q[0]-a[0])*nx+(q[1]-a[1])*ny
        if abs(d) > 1e-9:
            previous_side = 1 if d > 0 else -1
        if previous_side*e >= -1e-9:
            continue
        u = max(0.0,min(1.0,d/(d-e)))
        pose = case.pose((i+u)/(len(route)-1))
        along = (pose[0]-a[0])*tx+(pose[1]-a[1])*ty
        if 0 < along < length:
            def inclination(x,y):
                return math.degrees(math.atan2(abs(x*tx+y*ty),abs(x*nx+y*ny)))
            return pose, inclination(pose[2],pose[3]), inclination(q[0]-p[0],q[1]-p[1])
    return None


def patterned_path(fig, points, dash, gap, layer):
    """Carry the dash phase through vertices of a sampled path."""
    distance = 0.0
    period = dash + gap
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        if length < 1e-9:
            continue
        end = distance + length
        dx, dy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        for mark in range(math.floor(distance / period), math.ceil(end / period)):
            lo = max(distance, mark * period) - distance
            hi = min(end, mark * period + dash) - distance
            if hi > lo:
                fig.add(Line(a[0] + lo*dx, a[1] + lo*dy, a[0] + hi*dx, a[1] + hi*dy, layer))
        distance = end


def trajectory(case, result, corners):
    poses = [case.pose(s["start"]) for s in result["segments"]]+[case.pose(1)]
    disks = case.obstacles
    bounds = [world(p,c) for p in poses for c in corners]
    bounds.extend(p for crane in case.cranes for p in crane.box.corners)
    for x,y,r in disks:
        bounds.extend(((x-r,y-r),(x+r,y+r)))
    rail_extent = case.length*.67
    rails = [(world(poses[-1],(-rail_extent,y)),world(poses[-1],(rail_extent,y)))
             for y in (-case.gauge/2,case.gauge/2)]
    bounds.extend(p for line in rails for p in line)
    xs,ys = zip(*bounds)
    fig,k = drawing("双机转运轨迹平面图", 2,
                    min(313/(max(xs)-min(xs)), 178/(max(ys)-min(ys))), "trajectory")
    geometry_start = len(fig.primitives)
    mx,my = (min(xs)+max(xs))/2,(min(ys)+max(ys))/2
    def paper(p):
        return 219+(p[0]-mx)*k,159+(p[1]-my)*k

    for left,right in rails:
        fig.add(Line(*paper(left),*paper(right),"NOTE"))
    # Sleepers identify the target track; their spacing is a drawing convention.
    for j in range(19):
        u=rail_extent*(j/9-1)
        ends=[paper(world(poses[-1],(u,side*case.gauge*.76))) for side in (-1,1)]
        fig.add(Line(*ends[0],*ends[1],"THIN"))
    ca,cb = case.cranes
    crossing = first_gate_crossing(case)
    gate_pose = crossing[0] if crossing else None
    if crossing:
        dim.dash_dot(fig, paper(ca.center), paper(cb.center), layer="NOTE")
        fig.add(Polyline(tuple(paper(world(gate_pose,p)) for p in corners),True,LAYER_TRACE_GATE),
                Text(36,269,f"首次穿隙 · 车体 {crossing[1]:.1f}°，形心行进 {crossing[2]:.1f}°"
                     "（以两机中心连线法向为 0°）",height=3.5,layer=LAYER_TRACE_GATE))

    layers = (LAYER_TRACE_A, LAYER_TRACE_B)
    patterns = ((4.5, 2.0), (1.6, 2.1))
    for crane, layer in zip(case.cranes, layers):
        px,py = paper(crane.center)
        fig.add(Polyline(tuple(paper(p) for p in crane.box.corners), True, layer),
                Circle(px, py, 1.8, layer), Line(px-3, py, px+3, py, layer),
                Line(px, py-3, px, py+3, layer))
    for x,y,r in disks:
        px,py = paper((x,y))
        fig.add(Circle(px, py, r*k, "NOTE"))

    legs = len(case.route)-1
    start_outline = tuple(paper(world(poses[0], p)) for p in corners)
    end_outline = tuple(paper(world(poses[-1], p)) for p in corners)
    patterned_path(fig, (*start_outline, start_outline[0]), 4, 2, "OUTLINE")
    fig.add(Polyline(end_outline, True, "OUTLINE"))
    for lug, (dash, gap), layer in zip(case.lugs, patterns, layers):
        path = tuple(paper(world(p,lug)) for p in poses)
        patterned_path(fig, path, dash, gap, layer)

    centerline = tuple(paper(p[:2]) for p in case.route)
    fig.add(Polyline(centerline, False, LAYER_TRACE_CENTER))
    distances = list(accumulate((math.dist(a, b) for a, b in zip(centerline, centerline[1:])), initial=0.0))
    travel = distances[-1]
    if travel >= 10:
        for fraction in ((.25, .5, .75) if travel >= 60 else (.5,)):
            position = fraction * travel
            for a, b, lo, hi in zip(centerline, centerline[1:], distances, distances[1:]):
                if lo <= position < hi:
                    dx, dy = (b[0]-a[0])/(hi-lo), (b[1]-a[1])/(hi-lo)
                    dim.arrow(fig, a[0]+dx*(position-lo), a[1]+dy*(position-lo), dx, dy,
                              size=3.8, layer=LAYER_TRACE_CENTER)
                    break
    start, end = centerline[0], centerline[-1]
    fig.add(Circle(*start, 2.0, LAYER_TRACE_CENTER), Circle(*end, 2.0, LAYER_TRACE_CENTER))
    label = trajectory_labels(fig, geometry_start)
    label(start, "P0 起吊", LAYER_TRACE_CENTER, below=True, height=4.5)
    label(end, f"P{legs} 落位", LAYER_TRACE_CENTER, height=4.5)
    for tag, crane, layer in zip("AB", case.cranes, layers):
        px, py = paper(crane.center)
        label((px, py), f"{tag} 机", layer, height=4.6)
    if gate_pose:
        label(paper(gate_pose[:2]), "穿隙姿态", LAYER_TRACE_GATE, height=3.5)
    for index, (x,y,_) in enumerate(disks, 1):
        label(paper((x, y)), f"障碍 {index}", "NOTE", height=3.1)
    marked = [start, end]
    for index in sorted({round(legs*fraction) for fraction in (.25, .5, .75)} - {0, legs}):
        point = centerline[index]
        if all(math.dist(point, previous) >= 24 for previous in marked):
            fig.add(Circle(*point, 1.1, LAYER_TRACE_CENTER))
            label(point, f"P{index}", LAYER_TRACE_CENTER, below=True, height=3.3)
            marked.append(point)

    spacing = math.dist(ca.center,cb.center)
    fig.add(Text(36,282,f"P0 起吊  →  P{legs} 落位",height=5),
            Text(403,281,f"回转中心距 {spacing:.2f} m   ·   两机占地净距 {ca.box.distance(cb.box):.2f} m",
                 height=3.6,align=ALIGN_RIGHT),
            Text(403,269,f"转运净距下界 ≥ {math.floor(result['clearance']['lower_m']*1000)/1000:.3f} m",
                 height=3.6,align=ALIGN_RIGHT),
            Text(36,14,f"车长 {case.length:g} m   ·   车宽 {case.width:g} m   ·   轨距 {case.gauge:g} m",
                 height=3.4),
            Line(36,40,56,40,LAYER_TRACE_CENTER),Text(62,42,"车体形心路径",height=3.8),
            Text(154,42,"矩形：吊机占地 · 十字：回转中心",height=3.6),
            Text(154,30,"车体：起吊虚线 / 落位实线",height=3.6),
            Text(154,18,"圆形：场地障碍",height=3.5))
    for y, tag, (dash, gap), layer in zip((29, 19), "AB", patterns, layers):
        patterned_path(fig, ((36, y), (56, y)), dash, gap, layer)
        fig.add(Text(62, y+2, f"吊点 {tag} 路径", height=3.6, layer=layer))
    return fig


def trajectory_labels(fig, geometry_start):
    """Place captions near their leader points without covering route strokes."""
    strokes = []
    for item in fig.primitives[geometry_start:]:
        if isinstance(item, Line):
            points = ((item.x1, item.y1), (item.x2, item.y2))
        elif isinstance(item, Polyline):
            points = (*item.points, item.points[0]) if item.closed else item.points
        else:
            continue
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)
            if length > 1e-9:
                x,y = (a[0]+b[0])/2, (a[1]+b[1])/2
                dx,dy = (b[0]-a[0])/length, (b[1]-a[1])/length
                bounds = (min(a[0],b[0]), min(a[1],b[1]), max(a[0],b[0]), max(a[1],b[1]))
                strokes.append((bounds, (x,y,dx,dy), length))

    used = []

    def label(point, content, layer, *, below=False, height=3.8):
        x, y = point
        vertical = -1 if below else 1
        offsets = ((9, vertical*12), (-9, vertical*12), (9, -vertical*12), (-9, -vertical*12),
                   (16, vertical*21), (-16, vertical*21), (19, -vertical*25), (-19, -vertical*25))
        fallback = None
        for dx, dy in offsets:
            note = Text(x+dx, y+dy, content, height=height, layer=layer,
                        align=ALIGN_RIGHT if dx < 0 else "left")
            left, bottom, right, top = bounds = note.bbox()
            if (not (35 <= left <= right <= 406 and 58 <= bottom <= top <= 260)
                    or any(overlaps(bounds, other, margin=1.5) for other in used)):
                continue
            end = (right + 2 if dx < 0 else left - 2, y+dy-height/2)
            if fallback is None:
                fallback = (bounds, end, note)
            caption = Box(((left+right)/2, (top+bottom)/2), right-left+2, top-bottom+2, 0)
            if not any(overlaps(bounds, edge, margin=1) and caption.separation(pose, length, 0) <= 0
                       for edge, pose, length in strokes):
                fallback = (bounds, end, note)
                break
        if fallback:
            bounds, end, note = fallback
            used.append(bounds)
            fig.add(Line(x, y, *end, "NOTE"), note)

    return label


def crane_elevation(case, result, corners, side):
    """Project the train onto the vertical plane through this crane and its hook."""
    crane, lug = case.cranes[side], case.lugs[side]
    tag = "AB"[side]
    times = (t for segment in result["segments"]
             for t in (segment["start"], (segment["start"] + segment["end"])/2, segment["end"]))
    radius, time = max((math.dist(crane.center, world(case.pose(t), lug)), -t) for t in times)
    time = -time
    pose = case.pose(time)
    hook = world(pose, lug)
    if radius > 1e-9:
        ux, uy = (hook[0]-crane.center[0])/radius, (hook[1]-crane.center[1])/radius
    else:
        ux, uy = pose[2:]

    def radial(point):
        x, y = world(pose, point)
        return (x-crane.center[0])*ux + (y-crane.center[1])*uy

    projected = [radial(point) for point in corners]
    rear, front = min(projected), max(projected)
    body_top = case.bottom + case.height
    hook_height = body_top + crane.sling_height
    horizontal = (radius - BOOM_HEAD_REACH) / crane.boom
    reaches = -1 <= horizontal <= 1
    angle = math.degrees(math.acos(min(1, max(-1, horizontal))))
    model = ElevationModel(crane.boom, angle, radius, hook_height, front-rear, case.height)
    usable_rope = reaches and model.block_top <= model.tip_height - .61
    left = min(rear, -BODY_MODEL_FRONT)
    right = max(front, radius + 1.1, MODEL_REAR)
    top = max(hook_height + BLOCK_GAP + BLOCK_H, model.tip_height + 1 if reaches else 5.5)
    fig,k = drawing(f"{tag} 机吊装立面图", 3+side, min(317/(right-left), 195/top), f"elevation-{tag.lower()}")
    ground = 68
    paper = _Paper(k, 225+k*(left+right)/2, ground)
    draw_ground(fig, 39, 402, ground)
    axles = drawing_axles({}, {"model": crane.model}, crane.brand)
    draw_truck(fig, paper, axles, model.hinge if reaches else (0, model.hinge[1]), crane.model)
    if reaches:
        _draw_boom(fig, paper, model)
        _draw_luffing_cylinder(fig, paper, model)
    _draw_hook_block(fig, paper, model)
    if usable_rope:
        _draw_rope(fig, paper, model)

    body = ((rear,case.bottom), (front,case.bottom), (front,body_top), (rear,body_top))
    hx, hy = paper(radius, hook_height)
    sx, sy = paper(radius, body_top)
    cx, cy = paper((rear+front)/2, case.bottom+case.height/2)
    fig.add(Polyline(tuple(paper(x,y) for x,y in body), True),
            Line(sx,sy,hx,hy,"RIGGING"), Circle(sx,sy,1.15,"RIGGING"),
            Text(cx,cy+1.5,"车体投影",height=3.3,align=ALIGN_CENTER))
    dim.leader(fig, (sx,sy), (sx-7,sy+7), f"吊点 {tag}", align=ALIGN_RIGHT, height=3.2)
    dim.v_dim(fig,ground,hy,paper(right,0)[0]-11,f"H={hook_height:.2f} m",ref_x=hx,side="left")
    dim.h_dim(fig,hx,paper.ox,ground-10,f"R={radius:.2f} m",ref_y=ground)
    upper = max(s["radii"][side][1] for s in result["segments"])
    leg = min(len(case.route)-2, int(time*(len(case.route)-1)))
    fig.add(Text(36,282,f"{tag} 机  ·  {crane.brand} {crane.model}   ·   {crane.config}",height=4.7),
            Text(36,272,f"本机幅度采样峰值姿态  P{leg} → P{leg+1}   ·   路径 {100*time:.1f}%",height=3.6),
            Text(36,49,f"固定臂长 {crane.boom:g} m   ·   索具高度 {crane.sling_height:.2f} m   ·   "
                 f"全程幅度上界 {math.ceil(upper*100)/100:.2f} m",height=3.7),
            Text(36,37,f"吊物分载 {case.mass*result['shares'][side]:.2f} t   ·   "
                 f"本机总吊重 {result['loads'][side]:.2f} t",height=3.7),
            Text(36,24,"沿本机回转中心至本侧吊点投影，底盘为侧视示意。臂架仰角由幅度和臂长推算。",height=3.2))
    if not usable_rope:
        message = "示意臂长够不到本侧吊点" if not reaches else "示意臂端与所需吊钩高度之间空间不足"
        fig.add(Text(36,14,f"{message}，起升绳省略。",height=3.2,layer="RIGGING"))
    return fig


def sheets(case,result):
    corners = [(x*case.length/2,y*case.width/2) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return (statics(case,result,corners), trajectory(case,result,corners),
            crane_elevation(case,result,corners,0), crane_elevation(case,result,corners,1))
