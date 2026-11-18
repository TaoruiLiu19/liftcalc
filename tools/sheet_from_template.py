"""改造复用原软件的 DXF 图纸：保留图框/标题栏/材料表，换成吊装立面。"""

from __future__ import annotations

import math
import pathlib

import ezdxf

TEMPLATE = pathlib.Path(r"D:\学习日志\吊装助理\Dxf\Liftingdg.dxf")
OUT_DIR = pathlib.Path(r"D:\学习日志\吊装\liftcalc\out\sheet")
OUT_DXF = OUT_DIR / "吊装立面图.dxf"
OUT_PNG = OUT_DIR / "吊装立面图.png"


def build(params: dict) -> None:
    doc = ezdxf.readfile(str(TEMPLATE))
    msp = doc.modelspace()

    # 1) 删掉模型空间里的纯几何（吊耳图形），保留块引用（图框/符号/表格）
    removed = 0
    DROP_BLOCKS = ("debzst", "WeldCJP")
    for entity in list(msp):
        kind = entity.dxftype()
        if kind in ("LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE",
                    "SPLINE", "ELLIPSE", "HATCH", "SOLID", "DIMENSION"):
            msp.delete_entity(entity)
            removed += 1
        elif kind == "INSERT" and any(key in entity.dxf.name for key in DROP_BLOCKS):
            msp.delete_entity(entity)
            removed += 1
    print(f"删除几何实体 {removed} 个，保留块引用 {len(list(msp))} 个")

    # 2) 图层
    for name, color in (("LD实体", 7), ("LD虚线", 8), ("LD中心线", 8), ("LD标注", 1)):
        if name not in doc.layers:
            doc.layers.add(name, color=color)

    # 3) 吊装立面（1:100，单位 mm → 1 m = 10 mm）
    K = 100.0
    boom = params["boom"] * K
    radius = params["radius"] * K
    lift = params["lift"] * K
    ang = math.radians(params["angle"])
    from ezdxf import bbox as _bbox
    kept = [e for e in msp if e.dxftype() == "INSERT"]
    ext = _bbox.extents(kept)
    fx0, fy0, fx1, fy1 = ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y
    print(f"图框范围 x {fx0:.0f}..{fx1:.0f}  y {fy0:.0f}..{fy1:.0f}")
    origin = (fx0 + 0.10 * (fx1 - fx0), fy0 + 0.12 * (fy1 - fy0))

    def P(x: float, y: float) -> tuple[float, float]:
        return origin[0] + x, origin[1] + y

    tip = (boom * math.cos(ang), boom * math.sin(ang))

    msp.add_line(P(-90, 0), P(radius + 160, 0), dxfattribs={"layer": "LD实体"})
    msp.add_line(P(0, 0), P(*tip), dxfattribs={"layer": "LD实体"})
    msp.add_line(P(*tip), P(radius, lift), dxfattribs={"layer": "LD虚线"})
    msp.add_lwpolyline(
        [P(radius - 8, lift), P(radius + 8, lift), P(radius + 8, lift - 14), P(radius - 8, lift - 14)],
        close=True, dxfattribs={"layer": "LD实体"},
    )
    msp.add_lwpolyline(
        [P(radius - 20, lift - 14), P(radius + 20, lift - 14),
         P(radius + 20, lift - 55), P(radius - 20, lift - 55)],
        close=True, dxfattribs={"layer": "LD实体"},
    )
    msp.add_line(P(radius, lift - 70), P(radius, lift + 20), dxfattribs={"layer": "LD中心线"})
    msp.add_line(P(0, 0), P(radius, 0), dxfattribs={"layer": "LD标注"})
    msp.add_line(P(radius, 0), P(radius, lift), dxfattribs={"layer": "LD标注"})

    style = "Standard"
    msp.add_text(f"R = {params['radius']:g} m", height=45.0,
                 dxfattribs={"layer": "LD标注", "style": style}).set_placement(
        P(radius / 2 - 100, -140))
    msp.add_text(f"H = {params['lift']:.2f} m", height=45.0,
                 dxfattribs={"layer": "LD标注", "style": style}).set_placement(
        P(radius + 100, lift / 2))
    msp.add_text(f"L = {params['boom']:.2f} m   a = {params['angle']:.1f} deg", height=45.0,
                 dxfattribs={"layer": "LD标注", "style": style}).set_placement(
        P(tip[0] * 0.30, tip[1] * 0.42))
    msp.add_text("吊物", height=55.0,
                 dxfattribs={"layer": "LD实体", "style": style}).set_placement(
        P(radius - 160, lift - 400))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(OUT_DXF))
    print("已保存", OUT_DXF)

    from dxf_preview import render

    render(OUT_DXF, OUT_PNG, 2400)


if __name__ == "__main__":
    build({"boom": 25.98, "angle": 67.6, "radius": 10.0, "lift": 24.43})
