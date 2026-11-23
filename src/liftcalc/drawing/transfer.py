"""A3 vector sheets for a horizontal two-hook rail transfer."""
import math

from liftcalc.crane.transfer import world
from liftcalc.drawing import dim
from liftcalc.drawing.primitives import Circle, Figure, Line, Polyline, Text
from liftcalc.drawing.sheet import Sheet, draw_frame, title_block
from liftcalc.drawing.style import SCALE_LADDER


def drawing(title, number, max_scale):
    page = Sheet(420, 297)
    denominator = next((n for n in SCALE_LADDER if 1000/n <= max_scale),
                       max(500, math.ceil(1000/max_scale/50)*50))
    fig = Figure(title, page.width, page.height)
    draw_frame(fig, page)
    title_block(fig, page, title=title, subtitle="A3", scale_text=f"1:{denominator}",
                drawing_no=f"DT-0{number}", project="列车双机上轨", date="", sheet_no=f"{number}/2")
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
                                             72/max(hook_z), 56/case.width))
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


def trajectory(case, result, corners):
    poses = [case.pose(s["start"]) for s in result["segments"]]+[case.pose(1)]
    disks = case.obstacles
    bounds = [world(p,c) for p in poses for c in corners]
    bounds.extend(p for crane in case.cranes for p in crane.box.corners)
    for x,y,r in disks:
        bounds.extend(((x-r,y-r),(x+r,y+r)))
    rails = [(world(poses[-1],(-case.length*.85,y)),world(poses[-1],(case.length*.85,y)))
             for y in (-case.gauge/2,case.gauge/2)]
    bounds.extend(p for line in rails for p in line)
    xs,ys = zip(*bounds)
    fig,k = drawing("双机转运轨迹平面图",2,min(327/(max(xs)-min(xs)),196/(max(ys)-min(ys))))
    mx,my = (min(xs)+max(xs))/2,(min(ys)+max(ys))/2
    def paper(p):
        return 219+(p[0]-mx)*k,163+(p[1]-my)*k
    for left,right in rails:
        fig.add(Line(*paper(left),*paper(right),"OUTLINE"))
    # Sleepers identify the target track; their spacing is a drawing convention.
    for j in range(19):
        u=case.length*.85*(j/9-1)
        ends=[paper(world(poses[-1],(u,side*case.gauge*.76))) for side in (-1,1)]
        fig.add(Line(*ends[0],*ends[1],"THIN"))
    ca,cb = case.cranes
    middle = tuple((a+b)/2 for a,b in zip(ca.center,cb.center))
    gate_pose = min(poses,key=lambda p: math.dist(p[:2],middle))
    for j,crane in enumerate(case.cranes):
        px,py = paper(crane.center)
        fig.add(Polyline(tuple(paper(p) for p in crane.box.corners)),
                Text(px+2,py+6,"AB"[j]+" 机",height=3),
                Line(px,py,*paper(world(gate_pose,case.lugs[j])),"NOTE"))
        cross(fig,px,py,3)
    for j,(x,y,r) in enumerate(disks):
        px,py = paper((x,y))
        fig.add(Circle(px,py,r*k,"THIN"),Text(px+2,py+6,f"障碍 {j+1}",height=3))
    legs = len(case.route)-1
    keyframes = sorted({round(j*legs/4) for j in range(5)})
    for i in keyframes:
        pose = case.pose(i/legs)
        layer = "OUTLINE" if i in (0,legs) else "NOTE"
        fig.add(Polyline(tuple(paper(world(pose,p)) for p in corners),True,layer))
        px,py = paper(world(pose,corners[2]))
        fig.add(Text(px+1,py+4,f"P{i}",height=3.4))
    for lug in case.lugs:
        path = tuple(paper(world(p,lug)) for p in poses)
        fig.add(Polyline(path,False,"CENTER"))
    centerline = tuple(paper(p[:2]) for p in case.route)
    fig.add(Polyline(centerline,False,"THIN"))
    for i in keyframes[:-1]:
        a,b = centerline[i:i+2]
        d = math.dist(a,b)
        if d>4:
            dim.arrow(fig,(a[0]+b[0])/2,(a[1]+b[1])/2,(b[0]-a[0])/d,(b[1]-a[1])/d,layer="OUTLINE")
    spacing = math.dist(ca.center,cb.center)
    fig.add(Text(36,281,f"P0 起吊  →  P{legs} 落位    ·    中间编号为选示姿态",height=3.7),
            Text(35,34,f"回转中心距  {spacing:.2f} m",height=3.4),
            Text(35,24,f"矩形边界净距  {ca.box.distance(cb.box):.2f} m",height=3.4),
            Text(35,14,f"车长  {case.length:g} m     车宽  {case.width:g} m     轨距  {case.gauge:g} m",height=3.4),
            Text(158,34,"矩形为吊机占地包络",height=3.2),
            Line(157,21,171,21,"CENTER"),Text(174,23,"吊点轨迹",height=3.2))
    return fig


def sheets(case,result):
    corners = [(x*case.length/2,y*case.width/2) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return statics(case,result,corners), trajectory(case,result,corners)
