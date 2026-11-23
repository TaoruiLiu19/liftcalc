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
    fig,k = drawing("双机抬吊静力图", 1, min(305/(2*half), 305/case.length,
                                             64/case.height, 60/case.width))
    def x(p):
        return 212+k*station(p)
    y0, y1 = 209-k*case.height/2, 209+k*case.height/2
    fig.add(Text(36,281,"沿 AB 线剖视",height=4),
            Polyline(((212-k*half,y0),(212+k*half,y0),(212+k*half,y1),(212-k*half,y1))))
    for j,p in enumerate((a,b,case.cg)):
        y = y1 if j<2 else 209+k*p[2]
        direction = 1 if j<2 else -1
        tip = y+direction*21
        fig.add(Circle(x(p),y,1.5), Line(x(p),y,x(p),tip,"RIGGING"),
                Text(x(p)+2,tip+3,("FA","FB","W")[j],height=3.4))
        dim.arrow(fig,x(p),tip,0,direction,layer="RIGGING")
    dim.v_dim(fig,y0,y1,212+k*half+10,f"{case.height:.2f} m",ref_x=212+k*half,side="right")
    for left,right in ((a,case.cg),(case.cg,b)):
        dim.h_dim(fig,x(left),x(right),169,f"{station(right)-station(left):.2f} m",ref_y=y0)
    dim.h_dim(fig,x(a),x(b),153,f"AB  {span:.2f} m",ref_y=y0)
    fig.add(Text(36,138,"吊点布置 · 顶视",height=4),
            Polyline(tuple((212+k*u,95+k*v) for u,v in corners)))
    pts = [(212+k*p[0],95+k*p[1]) for p in (a,b,case.cg)]
    fig.add(Line(*pts[0],*pts[1],"CENTER"))
    for name,(px,py) in zip("ABG",pts):
        fig.add(Circle(px,py,1.7),Text(px+2,py+5,name,height=3.2))
        if j<2:
            # Conventional plan symbol centered at the rotation axis (not a footprint).
            fig.add(Polyline(((px-6,py-2),(px+6,py-2),(px+6,py+2),(px-6,py+2))),
                    Line(px+3,py-2,px+3,py+2,"THIN"),
                    Line(px,py,*paper(world(gate_pose,case.lugs[j])),"NOTE"))
        cross(fig,px,py,3)
    dim.h_dim(fig,212-k*case.length/2,212+k*case.length/2,52,
              f"{case.length:.2f} m",ref_y=95-k*case.width/2)
    for i,fraction in enumerate((*result["shares"],1)):
        fig.add(Text(35+i*69,28,f"{('FA','FB','W')[i]}  {case.mass*9.80665*fraction:.2f} kN",height=3.5))
    return fig


def trajectory(case, result, corners):
    poses = [case.pose(s["start"]) for s in result["segments"]]+[case.pose(1)]
    disks = [(*c.center,c.exclusion) for c in case.cranes]+case.obstacles
    bounds = [world(p,c) for p in poses for c in corners]
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
    for j,(x,y,r) in enumerate(disks):
        px,py = paper((x,y))
        fig.add(Circle(px,py,r*k,"THIN"),Text(px+2,py+6,("AB"[j]+" 机") if j<2 else f"障碍 {j-1}",height=3))
        if j<2:
            # Conventional plan symbol centered at the rotation axis (not a footprint).
            fig.add(Polyline(((px-6,py-2),(px+6,py-2),(px+6,py+2),(px-6,py+2))),
                    Line(px+3,py-2,px+3,py+2,"THIN"),
                    Line(px,py,*paper(world(gate_pose,case.lugs[j])),"NOTE"))
        cross(fig,px,py,3)
    legs = len(case.route)-1
    for i in range(legs+1):
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
    for a,b in zip(centerline,centerline[1:]):
        d = math.dist(a,b)
        if d>4:
            dim.arrow(fig,(a[0]+b[0])/2,(a[1]+b[1])/2,(b[0]-a[0])/d,(b[1]-a[1])/d,layer="OUTLINE")
    spacing = math.dist(ca.center,cb.center)
    fig.add(Text(36,281,f"P0 起吊  →  P{legs} 落位    ·    中间编号为调姿位置",height=3.7),
            Text(35,34,f"回转中心距  {spacing:.2f} m",height=3.4),
            Text(35,24,f"禁入圆边界间距  {spacing-ca.exclusion-cb.exclusion:.2f} m",height=3.4),
            Text(35,14,f"车长  {case.length:g} m     车宽  {case.width:g} m     轨距  {case.gauge:g} m",height=3.4),
            Text(158,34,"吊机为符号；圆为禁入区",height=3.2),
            Line(157,21,171,21,"CENTER"),Text(174,23,"吊点轨迹",height=3.2))
    return fig


def sheets(case,result):
    corners = [(x*case.length/2,y*case.width/2) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
    return statics(case,result,corners), trajectory(case,result,corners)
