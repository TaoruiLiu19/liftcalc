"""依赖方向检查（设计 §3.2）。

内核不得反向依赖数据层、编排层、渲染层或 CLI。
用 AST 静态扫描，比运行时 import 更能抓出"暂未执行"的违规。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "liftcalc"

FORBIDDEN_FOR_KERNEL = (
    "liftcalc.data",
    "liftcalc.services",
    "liftcalc.report",
    "liftcalc.drawing",
    "liftcalc.cli",
)

KERNEL_PACKAGES = ("sections", "geometry", "lifting", "codecheck")


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("package", KERNEL_PACKAGES)
def test_kernel_does_not_depend_outward(package: str) -> None:
    offenders: list[str] = []
    for path in (SRC / package).rglob("*.py"):
        for name in _imports_of(path):
            if any(name == bad or name.startswith(bad + ".") for bad in FORBIDDEN_FOR_KERNEL):
                offenders.append(f"{path.name} -> {name}")
    assert not offenders, f"内核出现反向依赖：{offenders}"


def test_core_has_no_internal_dependencies() -> None:
    offenders: list[str] = []
    for path in (SRC / "core").rglob("*.py"):
        for name in _imports_of(path):
            if name.startswith("liftcalc.") and not name.startswith("liftcalc.core"):
                offenders.append(f"{path.name} -> {name}")
    assert not offenders, f"core 不得依赖其他内部模块：{offenders}"


def test_report_does_not_import_kernel_calculators() -> None:
    """渲染层只吃结果模型，不得直接调计算模块。"""
    offenders: list[str] = []
    for path in (SRC / "report").rglob("*.py"):
        for name in _imports_of(path):
            if name.startswith(("liftcalc.sections", "liftcalc.lifting", "liftcalc.geometry")):
                offenders.append(f"{path.name} -> {name}")
    assert not offenders, f"渲染层出现计算依赖：{offenders}"
