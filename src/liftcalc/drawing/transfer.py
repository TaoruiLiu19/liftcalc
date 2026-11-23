"""Paired CAD sheets for the same rail-transfer calculation."""
import math

from liftcalc.crane.transfer import world
from liftcalc.drawing.primitives import Circle, Figure, Line, Polyline, Text


def sheets(case, result):
    static = Figure("双机水平抬吊 · 静力分析", 297, 210)
    plan = Figure("列车上轨 · 俯视轨迹", 297, 210)
    for fig in (static, plan):
        fig.add(Text(10, 202, fig.title, height=6))
        fig.add(Text(10, 13, "水平刚体 · 竖向吊索 · 场地坐标 m · 工况图面单位 mm · 不含动力与整机稳定分析", height=3))
    a, b = case.lugs
    span = math.dist(a, b)
    # Elevation projected onto the vertical plane through A and B.
    direction = ((b[0]-a[0])/span, (b[1]-a[1])/span)
    corners = [(x*case.length/2, y*case.width/2) for x,y in ((-1,-1),(1,-1),(1,1),(-1,1))]
    def station(p):
        return sum((p[i]-a[i])*direction[i] for i in range(2))
    lo, hi = min(map(station, corners)), max(map(station, corners))
    scale = min(245/(hi-lo), 52/case.height)
    def sx(p):
        return 148 + (station(p)-(lo+hi)/2)*scale
    bottom, top = 102-case.height*scale/2, 102+case.height*scale/2
    xl, xr = 148-(hi-lo)*scale/2, 148+(hi-lo)*scale/2
    static.add(Polyline(((xl,bottom),(xr,bottom),(xr,top),(xl,top))))
    for j, p in enumerate((a,b,case.cg)):
        down = j == 2
        x, y = sx(p), 102+case.cg[2]*scale if down else top
        end = y + (-25 if down else 25*result["shares"][j])
        back = end + (3 if down else -3)
        force = case.mass*9.80665*(1 if down else result["shares"][j])
        static.add(Circle(x,y,1.3), Line(x,y,x,end,"RIGGING"),
                   Polyline(((x-1.6,back),(x,end),(x+1.6,back)),False,"RIGGING"),
                   Text(x,end+(-1 if down else 5), "ABG"[j],height=3.5))
        static.add(Text(11+j*94, 182, f"{'FA FB W'.split()[j]} = {force:.2f} kN",height=4.5))
    static.add(Text(10,166,f"沿 AB 剖视   AG = {station(case.cg):.3f} m     GB = {span-station(case.cg):.3f} m     AB = {span:.3f} m",height=3.8))
    for j,(lug,crane) in enumerate(zip(case.lugs,case.cranes)):
        static.add(Text(10,46-j*8,f"{'AB'[j]}  吊点 ({lug[0]:g}, {lug[1]:g}) m    分载 {result['shares'][j]:.1%}    "
                        f"计算总吊重 {result['loads'][j]:.2f} t    所需钩高 {case.bottom+case.height+crane.sling_height:.2f} m",height=3.5))
    static.add(Text(10,26,f"重心 G ({case.cg[0]:g}, {case.cg[1]:g}, {case.cg[2]:g}) m，相对形心。吊点位于顶面。",height=3.2))

    segments = result["segments"]
    poses = [case.pose(s["start"]) for s in segments]+[case.pose(1)]
    disks = [(*c.center,c.exclusion) for c in case.cranes]+case.obstacles
    bounds = [world(p,c) for p in poses for c in corners]
    for x,y,r in disks:
        bounds.extend(((x-r,y-r),(x+r,y+r)))
    rails = [(world(poses[-1],(-case.length*.7, y)), world(poses[-1],(case.length*.7,y)))
             for y in (-case.gauge/2, case.gauge/2)]
    bounds.extend(p for rail in rails for p in rail)
    xs, ys = zip(*bounds)
    scale = min(252/max(max(xs)-min(xs),.001),130/max(max(ys)-min(ys),.001))
    def paper(p):
        return (148+(p[0]-(min_x+max_x)/2)*scale, 102+(p[1]-(min_y+max_y)/2)*scale)
    min_x,max_x,min_y,max_y = min(xs),max(xs),min(ys),max(ys)
    for ra, rb in rails:
        plan.add(Line(*paper(ra),*paper(rb),"THIN"))
    for j,(x,y,r) in enumerate(disks):
        px,py = paper((x,y))
        plan.add(Circle(px,py,r*scale,"THIN"),Text(px,py,"AB"[j] if j<2 else f"障碍{j-1}",height=3))
    for t in (0,.5,1):
        pose=case.pose(t)
        plan.add(Polyline(tuple(paper(world(pose,c)) for c in corners)))
        px,py = paper(world(pose,corners[2]))
        plan.add(Text(px,py,{0:"起",.5:"转",1:"落"}[t],height=3.5))
        for crane,lug in zip(case.cranes,case.lugs):
            plan.add(Line(*paper(crane.center),*paper(world(pose,lug)),"THIN"))
    for lug in case.lugs:
        for i,seg in enumerate(segments):
            layer = "RIGGING" if seg["unsafe"] else "NOTE" if seg["unknown"] else "OUTLINE"
            plan.add(Line(*paper(world(poses[i],lug)),*paper(world(poses[i+1],lug)),layer))
    n_bad=sum(bool(s["unsafe"]) for s in segments)
    n_open=sum(bool(s["unknown"]) and not s["unsafe"] for s in segments)
    plan.add(Text(10,189,f"航向 {case.start[2]:g}° → {case.end[2]:g}°    区间 {len(segments)}    超限/相交 {n_bad}    待核 {n_open}",height=4))
    plan.add(Text(10,179,"三姿态外框和两吊点轨迹；圆为禁入区。轨迹图层 RIGGING 超限，NOTE 待核，OUTLINE 已核项满足。",height=3))
    for j,crane in enumerate(case.cranes):
        ratios = [s["ratios"][j] for s in segments if s["ratios"][j] is not None]
        peak = f"{max(ratios):.1%}" if ratios else "无表档"
        plan.add(Text(10+j*138,34,f"{'AB'[j]}  {crane.model}   L={crane.boom:g} m   已覆盖档负荷率上界 {peak}",height=3.2))
    plan.add(Line(20,52,34,52),Line(20,52,20,66),Text(35,54,"X",height=3),Text(18,71,"Y",height=3))
    plan.add(Text(10,26,"终点车体纵轴为目标轨向；尚需核对实际轨道对位、臂间净空、支承及现场障碍。",height=3.2))
    return static, plan
