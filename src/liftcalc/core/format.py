"""数值格式化（报告、计算书、substituted 串共用）。"""

from __future__ import annotations


def sig(value: float, digits: int = 3) -> str:
    """有效数字格式化，去掉浮点尾差。"""
    if value == 0:
        return "0"
    text = f"{value:.{digits}g}"
    return text


def fixed(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


def ratio_text(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
