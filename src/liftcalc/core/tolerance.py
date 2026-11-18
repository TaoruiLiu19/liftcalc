"""数值比较与容差。

三条容差线：
- 解析解对照：几乎精确
- 数值法对照：允许离散误差
- 与原程序对拍：工程可接受偏差（ADR-002 的判定口径）
"""

from __future__ import annotations

import math
from typing import Final

ANALYTIC_REL_TOL: Final = 1e-9
NUMERIC_REL_TOL: Final = 1e-6
GEOMETRY_REL_TOL: Final = 1e-3

ORACLE_PASS_TOL: Final = 0.01
ORACLE_WARN_TOL: Final = 0.05


def rel_diff(a: float, b: float) -> float:
    """相对偏差；两个 0 视为相同。"""
    if a == b:
        return 0.0
    scale = max(abs(a), abs(b))
    if scale == 0.0:
        return 0.0
    return abs(a - b) / scale


def close(a: float, b: float, rel: float = ANALYTIC_REL_TOL, abs_tol: float = 0.0) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=abs_tol)


def oracle_grade(new: float, ref: float) -> str:
    """对拍分级：PASS / WARN / HIGH。"""
    diff = rel_diff(new, ref)
    if diff <= ORACLE_PASS_TOL:
        return "PASS"
    if diff <= ORACLE_WARN_TOL:
        return "WARN"
    return "HIGH"
