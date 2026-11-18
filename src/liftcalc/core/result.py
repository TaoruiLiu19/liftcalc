"""结果模型（设计 §5.3）。

计算书、绘图、对拍都只消费这两个模型；它们是全系统的"唯一事实"。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NA = "N/A"


class CheckResult(BaseModel):
    """一个校核项，也是计算书里的最小展示单元。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    formula_id: str = ""
    substituted: str = ""
    inputs: dict[str, float] = Field(default_factory=dict)
    value: float
    limit: float | None = None
    ratio: float | None = None
    verdict: Verdict
    unit: str = ""
    source: str = ""
    notes: list[str] = Field(default_factory=list)


class ComputationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    engine_version: str
    data_version: str = ""
    input_digest: str = ""
    verdict: Verdict = Verdict.NA
    governing: str | None = None
    utilization: float = 0.0
    checks: list[CheckResult] = Field(default_factory=list)
    aux: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def summarize(checks: list[CheckResult]) -> tuple[Verdict, str | None, float]:
    """由 checks 推出总判定、控制项与最大利用率。

    规则：任一项 FAIL → FAIL；全部 NA → NA；否则 PASS。
    控制项取 ratio 最大者（ratio 缺失的按 0 处理）。
    """
    if not checks:
        return Verdict.NA, None, 0.0

    governing: str | None = None
    utilization = 0.0
    for check in checks:
        if check.ratio is None:
            continue
        if check.ratio > utilization:
            utilization = check.ratio
            governing = check.id

    if any(check.verdict is Verdict.FAIL for check in checks):
        return Verdict.FAIL, governing, utilization
    if all(check.verdict is Verdict.NA for check in checks):
        return Verdict.NA, governing, utilization
    return Verdict.PASS, governing, utilization
