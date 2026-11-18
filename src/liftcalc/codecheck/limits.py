"""限值与折减系数（设计 §8.8）。

**本模块的系数全部是占位值**，必须对着规范原文核定后替换。
每个 Limit 都带 `provisional` 标记，计算书会据此打印"占位系数"提示。

待核定清单（设计 §17-R2）：
- 抗拉强度设计值 f = fy / γR 中的 γR
- 承压强度设计值的取值方式（是否按 1.5f）
- 抗剪强度设计值（f / √3 或规范给定值）
- 角焊缝强度设计值 f_f^w（按焊条型号）
- 净截面/端部抗剪的构造要求（孔边距、板端距离下限）
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PROVISIONAL = True

GAMMA_R = 1.1
BEARING_FACTOR = 1.5
SHEAR_FACTOR = 1.0 / math.sqrt(3.0)
WELD_STRENGTH_E43 = 160.0
WELD_STRENGTH_E50 = 200.0


@dataclass(frozen=True)
class Limit:
    value: float  # MPa
    source: str
    provisional: bool = PROVISIONAL

    def note(self) -> str:
        return f"限值来源：{self.source}" + ("（占位系数，待规范核定）" if self.provisional else "")


def tensile_design_strength(fy_mpa: float) -> Limit:
    return Limit(fy_mpa / GAMMA_R, "GB 50017-2017 抗拉强度设计值（TBD-核定）")


def bearing_strength(fy_mpa: float) -> Limit:
    return Limit(BEARING_FACTOR * fy_mpa / GAMMA_R, "GB 50017-2017 承压强度设计值（TBD-核定）")


def shear_strength(fy_mpa: float) -> Limit:
    return Limit(SHEAR_FACTOR * fy_mpa / GAMMA_R, "GB 50017-2017 抗剪强度设计值（TBD-核定）")


def weld_strength(electrode: str = "E43") -> Limit:
    value = WELD_STRENGTH_E43 if electrode.upper().startswith("E43") else WELD_STRENGTH_E50
    return Limit(value, f"GB 50017-2017 角焊缝强度设计值 {electrode}（TBD-核定）")
