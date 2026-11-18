"""型钢查表与组合截面。

ADR 与设计 §3.2：内核不认识数据库——行数据由编排层注入。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from liftcalc.core.errors import NotFoundError
from liftcalc.core.units import Q
from liftcalc.sections import custom
from liftcalc.sections.models import SectionProps
from liftcalc.sections.props import make_section

Row = Mapping[str, object]


def _as_mm(row: Row, key: str) -> Q:
    value = row.get(key)
    if value in (None, ""):
        raise NotFoundError(f"型钢行缺少字段 {key}", row=dict(row))
    return Q(float(str(value)), "mm")


def _lookup(sections: Sequence[Row], family: str, designation: str) -> Row:
    for row in sections:
        if str(row.get("family")) == family and str(row.get("designation")) == designation:
            return row
    raise NotFoundError("未找到该型钢规格", family=family, designation=designation)


def _has_table_props(row: Row) -> bool:
    """行内是否已带表值（面积/惯性矩）。"""
    for key in ("A", "Ix", "Iy"):
        value = row.get(key)
        if value in (None, ""):
            return False
        try:
            if float(str(value)) <= 0:
                return False
        except ValueError:
            return False
    return True


def section_from_row(row: Row) -> SectionProps:
    """由数据行得到截面特性。

    优先级：行内表值 > 由公称尺寸计算。计算路径会标记为 derived，
    由调用方在结果里注明"非标准表值"。
    """
    family = str(row.get("family", ""))
    if _has_table_props(row):
        area_mm2 = float(str(row["A"]))
        ix_mm4 = float(str(row["Ix"]))
        iy_mm4 = float(str(row["Iy"]))
        h_mm = float(str(row.get("h", 0) or 0))
        b_mm = float(str(row.get("b", 0) or 0))
        if h_mm <= 0 or b_mm <= 0:
            raise NotFoundError("表值行缺少 h/b，无法确定包围盒", row=dict(row))
        # 型钢形心近似居中：以几何中心作为包围盒基准
        return make_section(
            area=area_mm2 * 1e-6,
            cx=0.0,
            cy=0.0,
            ix=ix_mm4 * 1e-12,
            iy=iy_mm4 * 1e-12,
            ixy=0.0,
            x_min=-b_mm / 2000.0,
            x_max=b_mm / 2000.0,
            y_min=-h_mm / 2000.0,
            y_max=h_mm / 2000.0,
        )

    if family in {"H", "I"}:
        return custom.i_section(_as_mm(row, "h"), _as_mm(row, "b"), _as_mm(row, "tw"), _as_mm(row, "tf"))
    if family == "C":
        return custom.channel(_as_mm(row, "h"), _as_mm(row, "b"), _as_mm(row, "tw"), _as_mm(row, "tf"))
    if family == "T":
        return custom.t_section(_as_mm(row, "h"), _as_mm(row, "b"), _as_mm(row, "tw"), _as_mm(row, "tf"))
    if family == "L":
        return custom.angle_section(_as_mm(row, "b"), _as_mm(row, "h"), _as_mm(row, "tw"))
    if family == "PIPE":
        return custom.pipe(_as_mm(row, "h"), _as_mm(row, "b"))
    if family == "BAR":
        return custom.round_bar(_as_mm(row, "h"))
    raise NotFoundError(f"不支持的型钢族：{family}", row=dict(row))


def get_section(sections: Sequence[Row], family: str, designation: str) -> SectionProps:
    return section_from_row(_lookup(sections, family, designation))


def composite(parts: Sequence[tuple[SectionProps, Q, Q]]) -> SectionProps:
    """按平行轴定理组合同一平面内的若干截面。

    parts 中的偏移是**形心相对组合截面参考原点的位置**。
    """
    if not parts:
        raise NotFoundError("组合截面至少需要一个子截面")

    total_area = 0.0
    moment_x = 0.0
    moment_y = 0.0
    for props, dx, dy in parts:
        area = float(props.area.to("m**2").magnitude)
        total_area += area
        moment_x += area * (float(props.cx.to("m").magnitude) + float(dx.to("m").magnitude))
        moment_y += area * (float(props.cy.to("m").magnitude) + float(dy.to("m").magnitude))

    cx = moment_x / total_area
    cy = moment_y / total_area

    ix = iy = ixy = 0.0
    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")
    torsion: float | None = 0.0

    for props, dx, dy in parts:
        area = float(props.area.to("m**2").magnitude)
        px = float(props.cx.to("m").magnitude) + float(dx.to("m").magnitude)
        py = float(props.cy.to("m").magnitude) + float(dy.to("m").magnitude)
        ix += float(props.ix.to("m**4").magnitude) + area * (py - cy) ** 2
        iy += float(props.iy.to("m**4").magnitude) + area * (px - cx) ** 2
        ixy += float(props.ixy.to("m**4").magnitude) + area * (px - cx) * (py - cy)
        x_min = min(x_min, float(props.x_left.to("m").magnitude) + px)
        x_max = max(x_max, float(props.x_right.to("m").magnitude) + px)
        y_min = min(y_min, float(props.y_bottom.to("m").magnitude) + py)
        y_max = max(y_max, float(props.y_top.to("m").magnitude) + py)
        if props.torsion_constant is None or torsion is None:
            torsion = None
        else:
            torsion += float(props.torsion_constant.to("m**4").magnitude)

    return make_section(
        area=total_area,
        cx=cx,
        cy=cy,
        ix=ix,
        iy=iy,
        ixy=ixy,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        torsion=torsion,
    )
