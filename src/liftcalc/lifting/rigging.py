"""索具校核（设计 §8.5）：钢丝绳、多分支受力、卸扣/吊钩选型。

不插值、不外推：索具选型一律"取不小于计算值的最近档"。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from liftcalc.core.errors import InfeasibleSectionError, OutOfTableError
from liftcalc.core.format import sig
from liftcalc.core.result import CheckResult, Verdict
from liftcalc.core.units import Q

DEFAULT_K_PRIME = 0.356  # 6×37 类捻制系数（TBD-核定）
DEFAULT_SAFETY_FACTOR = 6.0


@dataclass(frozen=True)
class RopeSpec:
    diameter: Q
    rated_strength: Q  # 公称抗拉强度 R0，MPa
    k_prime: float = DEFAULT_K_PRIME
    safety_factor: float = DEFAULT_SAFETY_FACTOR


@dataclass(frozen=True)
class SlingArrangement:
    branches: int
    angle_deg: float  # 分支与竖直方向夹角


@dataclass(frozen=True)
class SelectionOption:
    name: str
    capacity: float  # 吨


@dataclass(frozen=True)
class RiggingOutcome:
    checks: list[CheckResult]
    aux: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def rope_break_force(spec: RopeSpec) -> Q:
    """最小破断拉力 F0 = K' · d² · R0（返回 N）。"""
    diameter = float(spec.diameter.to("mm").magnitude)
    strength = float(spec.rated_strength.to("MPa").magnitude)
    if diameter <= 0 or strength <= 0 or spec.k_prime <= 0:
        raise InfeasibleSectionError("钢丝绳直径、抗拉强度、捻制系数都必须为正")
    return Q(spec.k_prime * diameter**2 * strength, "N")


def branch_force(total: Q, arrangement: SlingArrangement) -> Q:
    """多分支单支受力 T = N / (n · cosα)。"""
    if arrangement.branches < 1:
        raise InfeasibleSectionError("分支数至少为 1")
    angle = math.radians(arrangement.angle_deg)
    if not 0 <= angle < math.pi / 2:
        raise InfeasibleSectionError("分支夹角须在 [0°, 90°) 内")
    cosine = math.cos(angle)
    if cosine < 0.2:
        raise InfeasibleSectionError("分支夹角过大，单支受力发散")
    total_n = float(total.to("N").magnitude)
    if total_n <= 0:
        raise InfeasibleSectionError("总荷载必须为正")
    return Q(total_n / (arrangement.branches * cosine), "N")


def select_from_table(required_t: float, options: list[SelectionOption]) -> SelectionOption:
    """按吨位选型：取不小于需求的最小档；超表则报错，不外推。"""
    if not options:
        raise OutOfTableError("选型表为空")
    ordered = sorted(options, key=lambda item: item.capacity)
    for option in ordered:
        if option.capacity + 1e-12 >= required_t:
            return option
    raise OutOfTableError(
        f"需求 {required_t:.2f} t 超出表内最大档 {ordered[-1].name}（{ordered[-1].capacity:.2f} t）",
        required=required_t,
        max_available=ordered[-1].capacity,
    )


def check_rigging(
    *,
    total_load: Q,
    arrangement: SlingArrangement,
    rope: RopeSpec | None = None,
    shackle_options: list[SelectionOption] | None = None,
    hook_options: list[SelectionOption] | None = None,
) -> RiggingOutcome:
    warnings: list[str] = []
    checks: list[CheckResult] = []

    if arrangement.angle_deg > 60.0:
        warnings.append(f"分支夹角 {arrangement.angle_deg:g}° > 60°，规范通常限制在 60° 以内，请核实")
    if arrangement.branches > 2 and arrangement.angle_deg > 0:
        warnings.append("多分支按对称受力计算；实际应计入 1.1~1.25 的不均匀系数（当前未计入）")

    per_branch = branch_force(total_load, arrangement)
    per_branch_kn = float(per_branch.to("kN").magnitude)
    aux: dict[str, Any] = {
        "branches": arrangement.branches,
        "angle_deg": arrangement.angle_deg,
        "per_branch_kN": per_branch_kn,
        "per_branch_t": per_branch_kn / 9.80665,
    }

    if rope is not None:
        breaking = rope_break_force(rope)
        breaking_kn = float(breaking.to("kN").magnitude)
        required = per_branch_kn * rope.safety_factor
        aux.update(
            {
                "rope_break_kN": breaking_kn,
                "rope_required_kN": required,
                "safety_factor": rope.safety_factor,
            }
        )
        ratio = required / breaking_kn if breaking_kn > 0 else None
        checks.append(
            CheckResult(
                id="rigging.rope",
                title="钢丝绳破断拉力",
                formula_id="rigging.rope_break",
                substituted=(
                    f"F₀ = {rope.k_prime:g} × {sig(float(rope.diameter.to('mm').magnitude))}² "
                    f"× {sig(float(rope.rated_strength.to('MPa').magnitude)):s}"
                ),
                inputs={
                    "d": round(float(rope.diameter.to("mm").magnitude), 3),
                    "R0": round(float(rope.rated_strength.to("MPa").magnitude), 1),
                    "K": rope.k_prime,
                    "required": round(required, 2),
                },
                value=round(breaking_kn, 3),
                limit=round(required, 3),
                ratio=None if ratio is None else round(ratio, 4),
                verdict=Verdict.PASS if ratio is not None and ratio <= 1.0 + 1e-12 else Verdict.FAIL,
                unit="kN",
                source="GB/T 8918-2006（K′ 取值 TBD-核定）",
                notes=[f"安全系数取 {rope.safety_factor:g}（TBD-核定）", "限值为所需破断拉力"],
            )
        )
    else:
        warnings.append("未提供钢丝绳规格，跳过破断拉力校核")

    for kind, options in (("shackle", shackle_options), ("hook", hook_options)):
        if options is None:
            continue
        required_t = per_branch_kn / 9.80665
        try:
            chosen = select_from_table(required_t, options)
        except OutOfTableError as exc:
            checks.append(
                CheckResult(
                    id=f"rigging.{kind}",
                    title="卸扣选型" if kind == "shackle" else "吊钩选型",
                    substituted=f"需求 {required_t:.2f} t 超出现有表范围",
                    value=round(required_t, 3),
                    verdict=Verdict.FAIL,
                    unit="t",
                    source="按吨位选型（取不小于需求的最小档）",
                    notes=[str(exc)],
                )
            )
            continue
        checks.append(
            CheckResult(
                id=f"rigging.{kind}",
                title="卸扣选型" if kind == "shackle" else "吊钩选型",
                substituted=f"需求 {required_t:.2f} t → 选 {chosen.name}（{chosen.capacity:g} t）",
                inputs={"required": round(required_t, 3), "chosen": chosen.capacity},
                value=round(required_t, 3),
                limit=chosen.capacity,
                ratio=round(required_t / chosen.capacity, 4) if chosen.capacity > 0 else None,
                verdict=Verdict.PASS,
                unit="t",
                source="按吨位选型（取不小于需求的最小档）",
                notes=[f"选型：{chosen.name}"],
            )
        )

    return RiggingOutcome(checks=checks, aux=aux, warnings=warnings)
