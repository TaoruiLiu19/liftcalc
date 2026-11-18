"""参数化截面构造器。

形状来自 `sections.outline`，本模块只负责单位换算、解析解特例与扭转常数。
"""

from __future__ import annotations

import math

from liftcalc.core.errors import NonPositiveDimensionError
from liftcalc.core.units import Q
from liftcalc.sections import outline
from liftcalc.sections.models import SectionProps
from liftcalc.sections.props import make_section, section_from_polygons

_M = "m"


def _meters(value: Q, label: str) -> float:
    try:
        magnitude = float(value.to(_M).magnitude)
    except Exception as exc:
        raise NonPositiveDimensionError(f"{label} 需要长度单位：{value}") from exc
    if magnitude <= 0:
        raise NonPositiveDimensionError(f"{label} 必须为正：{magnitude} m")
    return magnitude


def rect(b: Q, h: Q) -> SectionProps:
    bb, hh = _meters(b, "宽度 b"), _meters(h, "高度 h")
    regions, holes = outline.rect(bb, hh)
    torsion = (min(bb, hh) * max(bb, hh) ** 3) / 3.0
    return section_from_polygons(regions, holes, torsion_constant=torsion)


def box(b_outer: Q, h_outer: Q, t: Q) -> SectionProps:
    bb, hh, tt = _meters(b_outer, "外宽"), _meters(h_outer, "外高"), _meters(t, "壁厚")
    if 2 * tt >= min(bb, hh):
        raise NonPositiveDimensionError("壁厚过大，内部空腔不为正")
    regions, holes = outline.box(bb, hh, tt)
    inner_b, inner_h = bb - 2 * tt, hh - 2 * tt
    a0 = inner_b * inner_h
    perimeter = 2 * (inner_b + inner_h)
    torsion = 4 * a0 * a0 / (perimeter / tt)
    return section_from_polygons(regions, holes, torsion_constant=torsion)


def round_bar(d: Q) -> SectionProps:
    dd = _meters(d, "直径 d")
    return make_section(
        area=math.pi * dd**2 / 4,
        cx=0.0,
        cy=0.0,
        ix=math.pi * dd**4 / 64,
        iy=math.pi * dd**4 / 64,
        ixy=0.0,
        x_min=-dd / 2,
        x_max=dd / 2,
        y_min=-dd / 2,
        y_max=dd / 2,
        torsion=math.pi * dd**4 / 32,
    )


def pipe(d_outer: Q, d_inner: Q) -> SectionProps:
    do, di = _meters(d_outer, "外径"), _meters(d_inner, "内径")
    if di >= do:
        raise NonPositiveDimensionError("内径必须小于外径")
    return make_section(
        area=math.pi * (do**2 - di**2) / 4,
        cx=0.0,
        cy=0.0,
        ix=math.pi * (do**4 - di**4) / 64,
        iy=math.pi * (do**4 - di**4) / 64,
        ixy=0.0,
        x_min=-do / 2,
        x_max=do / 2,
        y_min=-do / 2,
        y_max=do / 2,
        torsion=math.pi * (do**4 - di**4) / 32,
    )


def i_section(h: Q, b: Q, tw: Q, tf: Q) -> SectionProps:
    hh, bb, tww, tff = (
        _meters(h, "总高 h"),
        _meters(b, "翼缘宽 b"),
        _meters(tw, "腹板厚 tw"),
        _meters(tf, "翼缘厚 tf"),
    )
    if 2 * tff >= hh:
        raise NonPositiveDimensionError("翼缘过厚，腹板净高不为正")
    if tww >= bb:
        raise NonPositiveDimensionError("腹板厚不得大于翼缘宽")
    regions, holes = outline.i_section(hh, bb, tww, tff)
    torsion = (2 * bb * tff**3 + (hh - 2 * tff) * tww**3) / 3.0
    return section_from_polygons(regions, holes, torsion_constant=torsion)


def channel(h: Q, b: Q, tw: Q, tf: Q) -> SectionProps:
    hh, bb, tww, tff = (
        _meters(h, "总高 h"),
        _meters(b, "翼缘宽 b"),
        _meters(tw, "腹板厚 tw"),
        _meters(tf, "翼缘厚 tf"),
    )
    regions, holes = outline.channel(hh, bb, tww, tff)
    torsion = (2 * bb * tff**3 + (hh - 2 * tff) * tww**3) / 3.0
    return section_from_polygons(regions, holes, torsion_constant=torsion)


def t_section(h: Q, b: Q, tw: Q, tf: Q) -> SectionProps:
    hh, bb, tww, tff = (
        _meters(h, "总高 h"),
        _meters(b, "翼缘宽 b"),
        _meters(tw, "腹板厚 tw"),
        _meters(tf, "翼缘厚 tf"),
    )
    regions, holes = outline.t_section(hh, bb, tww, tff)
    torsion = (bb * tff**3 + (hh - tff) * tww**3) / 3.0
    return section_from_polygons(regions, holes, torsion_constant=torsion)


def angle_section(b_long: Q, b_short: Q, t: Q) -> SectionProps:
    bl, bs, tt = _meters(b_long, "长肢"), _meters(b_short, "短肢"), _meters(t, "厚度")
    regions, holes = outline.angle_section(bl, bs, tt)
    torsion = ((bl - tt) + (bs - tt)) * tt**3 / 3.0
    return section_from_polygons(regions, holes, torsion_constant=torsion)
