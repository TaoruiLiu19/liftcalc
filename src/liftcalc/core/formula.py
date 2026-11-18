"""公式登记表（设计 §9）。

公式只写一次，计算书、测试、文档都从这里取，避免三处漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_FORMULAS_PATH = Path(__file__).resolve().parent.parent / "data" / "pack" / "formulas.yaml"

TBD_MARK = "TBD"


@dataclass(frozen=True)
class Symbol:
    name: str
    unit: str = ""


@dataclass(frozen=True)
class Formula:
    id: str
    title: str
    expression: str
    source: str = ""
    applies: str = ""
    limit_ref: str = ""
    notes: str = ""
    symbols: dict[str, Symbol] = field(default_factory=dict)

    @property
    def source_is_provisional(self) -> bool:
        """条文号尚未核定时为 True（判断依据见设计 §17-R2）。"""
        return TBD_MARK in self.source or TBD_MARK in self.limit_ref


def load_formulas(path: Path | None = None) -> dict[str, Formula]:
    target = path or DEFAULT_FORMULAS_PATH
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or []
    formulas: dict[str, Formula] = {}
    for entry in raw:
        symbols = {
            key: Symbol(name=value.get("name", key), unit=value.get("unit", ""))
            for key, value in (entry.get("symbols") or {}).items()
        }
        formula = Formula(
            id=entry["id"],
            title=entry["title"],
            expression=entry["expression"],
            source=entry.get("source", ""),
            applies=entry.get("applies", ""),
            limit_ref=entry.get("limit_ref", ""),
            notes=entry.get("notes", ""),
            symbols=symbols,
        )
        if formula.id in formulas:
            raise ValueError(f"公式 ID 重复：{formula.id}")
        formulas[formula.id] = formula
    return formulas


_CACHE: dict[str, Formula] | None = None


def get_formulas() -> dict[str, Formula]:
    global _CACHE
    if _CACHE is None:
        _CACHE = load_formulas()
    return _CACHE


def get_formula(formula_id: str) -> Formula:
    formulas = get_formulas()
    try:
        return formulas[formula_id]
    except KeyError as exc:
        raise ValueError(f"未登记的公式 ID：{formula_id}") from exc
