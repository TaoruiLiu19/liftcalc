"""截面几何特性：数据模型。

坐标系：x 水平、y 竖向向上；全部使用 pint Quantity（SI 由调用方保证或在此归一）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from liftcalc.core.units import Q


@dataclass(frozen=True)
class SectionProps:
    area: Q
    cx: Q
    cy: Q
    ix: Q
    iy: Q
    ixy: Q
    i1: Q
    i2: Q
    principal_angle_deg: float
    wx: Q
    wy: Q
    rx: Q
    ry: Q
    y_top: Q
    y_bottom: Q
    x_left: Q
    x_right: Q
    torsion_constant: Q | None = None

    def as_dict(self) -> dict[str, float | None]:
        """转成便于序列化的数值字典（单位：mm、mm²、mm⁴、mm³）。"""
        return {
            "area": float(self.area.to("mm**2").magnitude),
            "cx": float(self.cx.to("mm").magnitude),
            "cy": float(self.cy.to("mm").magnitude),
            "ix": float(self.ix.to("mm**4").magnitude),
            "iy": float(self.iy.to("mm**4").magnitude),
            "ixy": float(self.ixy.to("mm**4").magnitude),
            "i1": float(self.i1.to("mm**4").magnitude),
            "i2": float(self.i2.to("mm**4").magnitude),
            "principal_angle_deg": self.principal_angle_deg,
            "wx": float(self.wx.to("mm**3").magnitude),
            "wy": float(self.wy.to("mm**3").magnitude),
            "rx": float(self.rx.to("mm").magnitude),
            "ry": float(self.ry.to("mm").magnitude),
            "y_top": float(self.y_top.to("mm").magnitude),
            "y_bottom": float(self.y_bottom.to("mm").magnitude),
            "x_left": float(self.x_left.to("mm").magnitude),
            "x_right": float(self.x_right.to("mm").magnitude),
            "torsion_constant": (
                None
                if self.torsion_constant is None
                else float(self.torsion_constant.to("mm**4").magnitude)
            ),
        }


@dataclass(frozen=True)
class RawIntegrals:
    """关于原点的截面积分（有符号，可正负相加）。"""

    area: float
    ax: float
    ay: float
    ixo: float
    iyo: float
    ixylo: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def __add__(self, other: RawIntegrals) -> RawIntegrals:
        return RawIntegrals(
            area=self.area + other.area,
            ax=self.ax + other.ax,
            ay=self.ay + other.ay,
            ixo=self.ixo + other.ixo,
            iyo=self.iyo + other.iyo,
            ixylo=self.ixylo + other.ixylo,
            x_min=min(self.x_min, other.x_min),
            x_max=max(self.x_max, other.x_max),
            y_min=min(self.y_min, other.y_min),
            y_max=max(self.y_max, other.y_max),
        )


def empty_integrals() -> RawIntegrals:
    inf = math.inf
    return RawIntegrals(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, inf, -inf, inf, -inf)
