"""A3 vector sheets for a horizontal two-hook rail transfer."""
import math
from itertools import accumulate

from liftcalc.crane.transfer import world
from liftcalc.drawing import dim
from liftcalc.drawing.annotation import clear_annotation_lines, nearby_labels, place_label
from liftcalc.drawing.body import BODY_MODEL_FRONT, MODEL_REAR, draw_truck, drawing_axles
from liftcalc.drawing.figures import (
    BOOM_HEAD_REACH, HINGE_H, LIFT_SHEAVE_RADIUS, ElevationModel, _Paper,
    _draw_boom, _draw_hook_block, _draw_luffing_cylinder, _draw_rope,
)
from liftcalc.drawing.primitives import ALIGN_CENTER, ALIGN_RIGHT, Circle, Figure, Line, Polyline, Text
from liftcalc.drawing.sheet import Sheet, draw_frame, draw_ground, title_block
from liftcalc.drawing.style import (
    LAYER_RIGGING, LAYER_THIN, LAYER_TRACE_A, LAYER_TRACE_B, LAYER_TRACE_CENTER, LAYER_TRACE_GATE,
    SCALE_LADDER,
)


def drawing(title, number, max_scale, kind, *, meta=None):
    page = Sheet(420, 297)
    denominator = next((n for n in SCALE_LADDER if 1000/n <= max_scale),
                       max(500, math.ceil(1000/max_scale/50)*50))
    fig = Figure(title, page.width, page.height)
    fig.meta["kind"] = kind
    fig.meta["scale"] = 1000 / denominator
    draw_frame(fig, page)
    title_block(fig, page, title=title, subtitle="A3", scale_text=f"1:{denominator}",
                drawing_no=f"DT-0{number}", project=(meta.project if meta else "") or "列车双机抬吊上轨",
                designer=meta.author if meta else "", date="", sheet_no=f"{number}/4")
    return fig, 1000/denominator


def cross(fig, x, y, r):
    fig.add(Line(x-r,y,x+r,y,"CENTER"), Line(x,y-r,x,y+r,"CENTER"))


def statics(case, result, corners, *, meta=None):
    """First-angle projections of the same horizontal suspended load."""
    a, b = case.lugs
    top_z = case.bottom + case.height
    hook_z = [top_z + crane.sling_height for crane in case.cranes]
    fig, k = drawing("双机抬吊静力图", 1,
                     min(262/(case.length+case.width), 145/(max(hook_z)+case.width)), "statics", meta=meta)
    length, width = k*case.length, k*case.width
    gap = 49
    left = 221 - (length + gap + width)/2
    right = left + length
    end_left, end_right = right + gap, right + gap + width
    x_front, x_end = (left+right)/2, (end_left+end_right)/2
    plan_bottom = 65
    plan_top = plan_bottom + width
    y_plan = (plan_bottom+plan_top)/2
    ground = plan_top + 45
    y0, y1 = ground+k*case.bottom, ground+k*top_z
    hook_y = [ground+k*z for z in hook_z]
    view_title_y = max(hook_y) + 17
    fig.add(Text(36,281,"吊物水平悬吊 · 第一角画法 · 竖向布置示意",height=4.5))

    # Left view sits to the right of the front view in first-angle projection.
    # The two mitre points carry the plan width to the horizontal end-view axis.
    for x in (left, right):
        dim.dashed(fig,(x,y0-2),(x,plan_top+2),layer=LAYER_THIN)
    for y in (y0, y1):
        dim.dashed(fig,(right+2,y),(end_left-2,y),layer=LAYER_THIN)
    for x,y in ((end_left,plan_top),(end_right,plan_bottom)):
        dim.dashed(fig,(right+2,y),(x,y),layer=LAYER_THIN)
        dim.dashed(fig,(x,y),(x,y0-2),layer=LAYER_THIN)
    dim.dashed(fig,(end_left,plan_top),(end_right,plan_bottom),layer=LAYER_THIN)

    def vertical_view(lo, hi, x_point, title):
        fig.add(Polyline(((lo,y0),(hi,y0),(hi,y1),(lo,y1))),
                Line(lo-7,ground,hi+7,ground,LAYER_THIN),
                Text((lo+hi)/2,view_title_y,title,height=4,align=ALIGN_CENTER))
        positions = [x_point(lug) for lug in (a, b)]
        same_position = abs(positions[0]-positions[1]) < 1e-6
        same_hook = same_position and abs(hook_y[0]-hook_y[1]) < 1e-6
        if same_hook:
            fig.add(Text(positions[0]+4,hook_y[0]+5,"A、B 吊钩（投影重合）",height=3))
        for i,(x,y) in enumerate(zip(positions,hook_y)):
            if same_hook and i == 1:
                break
            fig.add(Line(x,y1,x,y,LAYER_RIGGING), Circle(x,y,1.5),
                    Circle(x,y1,1.0,LAYER_RIGGING))
            dim.arrow(fig,x,y1+min(6,(y-y1)*.75),0,1,layer=LAYER_RIGGING)
            if not same_hook:
                side = -1 if x < positions[1-i] or (same_position and i == 0) else 1
                align = ALIGN_RIGHT if side < 0 else "left"
                dim.leader(fig,(x,y),(x+side*5,y+5),f"{'AB'[i]} 吊钩",align=align,height=3,dot=False)
        gx, gy = x_point(case.cg), y0+k*(case.cg[2]+case.height/2)
        fg = max(3.5, min(9, (y1-y0)*.35))
        fig.add(Circle(gx,gy,1.4),Line(gx,gy,gx,gy-fg,LAYER_RIGGING),
                Text(gx+2,gy-fg+2.5,"W",height=3.2))
        dim.arrow(fig,gx,gy-fg,0,-1,layer=LAYER_RIGGING)

    vertical_view(left,right,lambda p: x_front+k*p[0],"主视图")
    vertical_view(end_left,end_right,lambda p: x_end-k*p[1],"左视图 · 吊物端面")
    dim.v_dim(fig,y0,y1,left-12,f"H={case.height:.2f} m",ref_x=left)
    dim.v_dim(fig,y0,y1,end_right+12,f"H={case.height:.2f} m",ref_x=end_right,side="right")
    dim.h_dim(fig,end_left,end_right,ground-13,f"B={case.width:.2f} m",
              ref_y=y0,above=False)

    def plan(p):
        return x_front+k*p[0], y_plan+k*p[1]

    fig.add(Polyline(tuple(map(plan,corners))),
            Text(x_front,plan_top+12,"俯视图",height=4,align=ALIGN_CENTER))
    pts = [plan(p) for p in (a,b,case.cg)]
    fig.add(Line(*pts[0],*pts[1],"CENTER"))
    for px,py in pts:
        fig.add(Circle(px,py,1.4))
        cross(fig,px,py,2.4)
    dim.h_dim(fig,left,right,plan_bottom-8,f"L  {case.length:.2f} m",ref_y=plan_bottom)
    dim.v_dim(fig,plan_bottom,plan_top,left-12,f"B={case.width:.2f} m",ref_x=left)

    for i, (label, value) in enumerate((("AG",math.dist(a,case.cg[:2])),
                                       ("BG",math.dist(b,case.cg[:2])),("AB",math.dist(a,b)))):
        fig.add(Text(36+i*66,48,f"{label}  {value:.2f} m",height=3.3))
    fig.add(Text(36,38,f"A 吊钩中心离地高度 {hook_z[0]:.2f} m",height=3.2),
            Text(114,38,f"B 吊钩中心离地高度 {hook_z[1]:.2f} m",height=3.2),
            Text(192,38,f"吊物底面离地  {case.bottom:.2f} m",height=3.2))
    for i,(label,fraction) in enumerate(zip(("A 吊索拉力 FA","B 吊索拉力 FB","吊物重力 W"),(*result["shares"],1))):
        fig.add(Text(36+i*72,27,f"{label}  {case.mass*9.80665*fraction:.2f} kN",height=3.3))
    for name,(px,py) in zip("ABG",pts):
        label = Text(px+2,py+5,name,height=3.2)
        fig.add(place_label(fig,nearby_labels(label),bounds=(34,62,406,ground-7)) or label)
    clear_annotation_lines(fig)
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


def trajectory(case, result, corners, *, meta=None):
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
                    min(313/(max(xs)-min(xs)), 178/(max(ys)-min(ys))), "trajectory", meta=meta)
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
                Text(36,269,f"首次通过两机之间 · 吊物纵轴 {crossing[1]:.1f}°，形心移动方向 {crossing[2]:.1f}°",
                     height=3.5,layer=LAYER_TRACE_GATE),
                Text(36,261,"均为与两机回转中心连线法线的夹角",height=3.0,layer=LAYER_TRACE_GATE))

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
    label = trajectory_labels(fig)
    label(start, "P0 起吊", LAYER_TRACE_CENTER, below=True, height=4.5)
    label(end, f"P{legs} 落位", LAYER_TRACE_CENTER, height=4.5)
    for tag, crane, layer in zip("AB", case.cranes, layers):
        px, py = paper(crane.center)
        label((px, py), f"{tag} 机", layer, height=4.6)
    if gate_pose:
        label(paper(gate_pose[:2]), "通过两机间隙时的姿态", LAYER_TRACE_GATE, height=3.5)
    for index, (x,y,_) in enumerate(disks, 1):
        label(paper((x, y)), f"障碍物 {index}", "NOTE", height=3.1)
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
            Text(403,269,f"全程水平净距下界 {math.floor(result['clearance']['lower_m']*1000)/1000:.3f} m",
                 height=3.6,align=ALIGN_RIGHT),
            Text(36,14,f"吊物长 {case.length:g} m   ·   吊物宽 {case.width:g} m   ·   轨距 {case.gauge:g} m",
                 height=3.4),
            Line(36,40,56,40,LAYER_TRACE_CENTER),Text(62,42,"吊物形心轨迹",height=3.8),
            Text(154,42,"矩形：起重机占地包络 · 十字：回转中心",height=3.6),
            Text(154,30,"吊物：起吊虚线 / 落位实线",height=3.6),
            Text(154,18,"圆形：障碍物禁入区",height=3.5))
    for y, tag, (dash, gap), layer in zip((29, 19), "AB", patterns, layers):
        patterned_path(fig, ((36, y), (56, y)), dash, gap, layer)
        fig.add(Text(62, y+2, f"吊点 {tag} 轨迹", height=3.6, layer=layer))
    clear_annotation_lines(fig)
    return fig


def trajectory_labels(fig):
    """Place captions near their leader points without covering route strokes."""
    def label(point, content, layer, *, below=False, height=3.8):
        x, y = point
        vertical = -1 if below else 1
        offsets = ((9, vertical*12), (-9, vertical*12), (9, -vertical*12), (-9, -vertical*12),
                   (16, vertical*21), (-16, vertical*21), (19, -vertical*25), (-19, -vertical*25),
                   (28, vertical*33), (-28, vertical*33), (28, -vertical*33), (-28, -vertical*33))
        candidates = (Text(x+dx,y+dy,content,height=height,layer=layer,
                           align=ALIGN_RIGHT if dx < 0 else "left") for dx,dy in offsets)
        note = place_label(fig,candidates,bounds=(35,58,406,260))
        if note:
            left,_,right,_ = note.bbox()
            end_x = right+2 if note.align == ALIGN_RIGHT else left-2
            fig.add(Line(x,y,end_x,note.y-height/2,"NOTE"), note)

    return label


def draw_end_view_profile(fig, paper, profile, center, factor):
    def project(x, z):
        # The temporary drawing uses _Paper's reversed horizontal axis.
        return paper(center-x*factor, z)

    for item in profile.primitives:
        if isinstance(item, Line):
            fig.add(Line(*project(item.x1, item.y1), *project(item.x2, item.y2), item.layer))
        elif isinstance(item, Polyline):
            fig.add(Polyline(tuple(project(x, z) for x, z in item.points), item.closed, item.layer))
        elif isinstance(item, Circle):
            if abs(factor) == 1:
                fig.add(Circle(*project(item.cx,item.cy),item.r*paper.s,item.layer))
            else:
                angles = (i*math.tau/24 for i in range(24))
                points = tuple(project(item.cx+item.r*math.cos(a), item.cy+item.r*math.sin(a)) for a in angles)
                fig.add(Polyline(points, True, item.layer))


def crane_elevation(case, result, side, *, meta=None):
    """Show one crane in the transverse elevation of the initial lift."""
    tag = "AB"[side]
    crane, lug = case.cranes[side], case.lugs[side]
    pose = case.pose(0)
    px, py, cosine, sine = pose

    def transverse(point):
        return -(point[0]-px)*sine + (point[1]-py)*cosine

    center = transverse(crane.center)
    span = [transverse(point) for point in crane.box.corners]
    radius = math.dist(crane.center, world(pose, lug))
    body_top = case.bottom + case.height
    height = body_top + crane.sling_height
    radial = max(-1.0,min(1.0,(lug[1]-center)/radius)) if radius > 1e-9 else 0
    facing = 1 if center <= lug[1] else -1
    reach = (radius - BOOM_HEAD_REACH) / crane.boom
    model = (ElevationModel(crane.boom, math.degrees(math.acos(reach)), radius, height, case.width, case.height)
             if abs(reach) <= 1 else None)

    half_width = case.width/2
    body_ends = (center - facing*BODY_MODEL_FRONT, center + facing*MODEL_REAR)
    edge_left = min(-half_width, *span, *body_ends)
    edge_right = max(half_width, *span, *body_ends)
    top = max(height + 2, model.tip_height + .9 if model else HINGE_H + .8)
    fig,k = drawing(f"{tag} 机起吊端视图", 3+side, min(310/(edge_right-edge_left), 178/top),
                    f"elevation-{tag.lower()}", meta=meta)
    ground = 80
    paper = _Paper(k, 222+k*(edge_left+edge_right)/2, ground)
    draw_ground(fig, 39, 401, ground)

    cargo = ((-half_width,case.bottom), (half_width,case.bottom), (half_width,body_top), (-half_width,body_top))
    fig.add(Polyline(tuple(paper(*point) for point in cargo), True))
    cx, cy = paper(0, body_top)
    # Place the caption outside a narrow end face at small drawing scales.
    if case.width*k >= 12 and case.height*k >= 6:
        _, middle = paper(0, case.bottom+case.height/2)
        fig.add(Text(cx,middle+1.5,"吊物端面",height=2.9,align=ALIGN_CENTER))
    else:
        dim.leader(fig,(cx,cy-2),(cx+14,cy-2),"吊物端面",height=2.8,dot=False)
    x1, bottom = paper(-half_width,case.bottom)
    x2, _ = paper(half_width,case.bottom)
    height_x = min(x1,x2)-7
    dim.h_dim(fig,x1,x2,ground-8,"",ref_y=bottom)
    dim.v_dim(fig,bottom,cy,height_x,"",ref_x=min(x1,x2),side="left")
    fig.add(Text(cx,ground-4,f"短边 {case.width:.2f} m",height=2.9,align=ALIGN_CENTER,layer="DIM"),
            Text(height_x-4,(bottom+cy)/2,f"吊物高度 {case.height:.2f} m",height=2.8,
                 align=ALIGN_CENTER,angle=90,layer="DIM"))

    layer = (LAYER_TRACE_A, LAYER_TRACE_B)[side]
    sx, _ = paper(center, 0)
    hx, hy = paper(lug[1], height)
    lift_point = paper(lug[1], body_top)
    pivot = paper(center, HINGE_H)
    foot_x1, foot_x2 = paper(max(span),0)[0], paper(min(span),0)[0]
    foot_row = ground-18
    fig.add(Line(foot_x1,foot_row,foot_x2,foot_row,layer),
            Line(foot_x1,foot_row-1.6,foot_x1,foot_row+1.6,layer),
            Line(foot_x2,foot_row-1.6,foot_x2,foot_row+1.6,layer),
            Line(sx,foot_row-1.6,sx,foot_row+1.6,layer),
            Text(foot_x2+3,foot_row+1.5,f"{tag} 机占地包络投影",height=3.0,layer=layer))
    truck = Figure("", 0, 0)
    upper = Figure("", 0, 0)
    local = _Paper(1, 0, 0)
    axles = drawing_axles({}, {"model": crane.model}, crane.brand)
    draw_truck(truck, local, axles, (0, HINGE_H), crane.model, upper_figure=upper)
    draw_end_view_profile(fig,paper,truck,center,facing)
    usable_rope = model is not None and model.block_top < model.tip_height - .61
    if model:
        _draw_boom(upper, local, model)
        _draw_luffing_cylinder(upper, local, model, annotate=False)
        if usable_rope:
            _draw_hook_block(upper, local, model)
            _draw_rope(upper, local, model, annotate=False)
    draw_end_view_profile(fig,paper,upper,center,radial if model else facing)
    fig.add(Circle(*pivot,1.2))
    fig.add(Line(*lift_point,hx,hy,LAYER_RIGGING), Circle(*lift_point,.85,LAYER_RIGGING))
    if not usable_rope:
        fig.add(Circle(hx,hy,1.2))
    label_sign = -1 if sx >= hx else 1
    align = ALIGN_RIGHT if label_sign < 0 else "left"
    if usable_rope:
        rope_x = model.radius + LIFT_SHEAVE_RADIUS
        rope_y = (model.tip_height + model.block_sheave[1])/2
        rx, ry = paper(center + radial*rope_x,rope_y)
        dim.leader(fig,(rx,ry),(rx+label_sign*12,ry+8),"起升钢丝绳",align=align,height=2.9,dot=False)
    dim.leader(fig,(hx,hy),(hx+label_sign*13,hy+6),f"{tag} 吊钩中心  H={height:.2f} m",align=align,height=3.0,dot=False)
    _, ty = lift_point
    dim.leader(fig,lift_point,(max(x1,x2)+7,ty+2),f"吊点 {tag}",height=2.8,dot=False)
    sling_y = (ty+hy)/2
    sling_align = "left" if label_sign < 0 else ALIGN_RIGHT
    dim.leader(fig,(hx,sling_y),(hx-label_sign*8,max(sling_y+3,ty+9)),"吊索",align=sling_align,height=2.8,dot=False)

    fig.add(Text(36,282,f"{tag} 机  ·  {crane.brand} {crane.model}   ·   {crane.config}",height=4.7),
            Text(36,272,"吊物端视（短边 × 高）· P0 起吊 · 竖向布置示意",height=3.6),
            Text(36,46,f"起吊工作幅度 R={radius:.2f} m   ·   固定起重臂长度 {crane.boom:g} m",height=3.5),
            Text(36,37,f"{tag} 机分担的吊物质量 {case.mass*result['shares'][side]:.2f} t   ·   本机计算总起重量 "
                 f"{result['loads'][side]:.2f} t",height=3.5),
            Text(36,28,f"吊点 {tag}  局部 X={lug[0]:.2f} m，Y={lug[1]:.2f} m",height=3.3),
            Text(36,19,"上车及起升钢丝绳按吊物端面投影，底盘采用侧视示意。",height=3.0))
    if not usable_rope:
        fig.add(Text(36,12,"示意臂端与钩位之间条件不足，起升钢丝绳省略。",height=2.8,layer="RIGGING"))
    clear_annotation_lines(fig)
    return fig


def sheets(case, result, *, meta=None):
    corners = [(x*case.length/2,y*case.width/2) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return (statics(case, result, corners, meta=meta), trajectory(case, result, corners, meta=meta),
            crane_elevation(case, result, 0, meta=meta), crane_elevation(case, result, 1, meta=meta))
