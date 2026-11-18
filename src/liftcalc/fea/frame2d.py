"""2D 平面框架有限元（水平梁系专用，设计 §8.7）。

范围限定：**只支持水平单元**（两端 y 相同）。理由：斜杆的坐标变换与荷载
方向约定极易出错，而当前用途（吊梁、多跨连续梁）全是水平梁。需要斜杆时
再扩展，先保证正确性。

坐标系：x 向右、y 向上、转角逆时针为正。
内力符号：弯矩以使梁下缘受拉（下凸/sagging）为正。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from liftcalc.core.errors import InputError, SingularSystemError


@dataclass(frozen=True)
class FrameNode:
    x: float  # m
    y: float  # m


@dataclass(frozen=True)
class FrameElement:
    i: int
    j: int
    e_modulus: float  # Pa
    area: float  # m^2
    inertia: float  # m^4
    udl: float = 0.0  # 均布荷载 N/m，竖直向下为正


@dataclass(frozen=True)
class Support:
    node: int
    fix_ux: bool = False
    fix_uy: bool = True
    fix_rz: bool = False


@dataclass(frozen=True)
class NodalLoad:
    node: int
    fy: float = 0.0  # N，向上为正
    mz: float = 0.0  # N·m，逆时针为正


@dataclass
class FrameResult:
    displacements: np.ndarray  # (n,3)
    reactions: dict[int, tuple[float, float, float]]
    element_end_forces: list[np.ndarray]
    max_moment: float
    max_shear: float
    max_deflection: float
    deflection_node: int
    notes: list[str] = field(default_factory=list)


def _stiffness(e: FrameElement, length: float) -> np.ndarray:
    ea = e.e_modulus * e.area
    ei = e.e_modulus * e.inertia
    l2 = length * length
    l3 = l2 * length
    return np.array(
        [
            [ea / length, 0.0, 0.0, -ea / length, 0.0, 0.0],
            [0.0, 12 * ei / l3, 6 * ei / l2, 0.0, -12 * ei / l3, 6 * ei / l2],
            [0.0, 6 * ei / l2, 4 * ei / length, 0.0, -6 * ei / l2, 2 * ei / length],
            [-ea / length, 0.0, 0.0, ea / length, 0.0, 0.0],
            [0.0, -12 * ei / l3, -6 * ei / l2, 0.0, 12 * ei / l3, -6 * ei / l2],
            [0.0, 6 * ei / l2, 2 * ei / length, 0.0, -6 * ei / l2, 4 * ei / length],
        ],
        dtype=float,
    )


def _consistent_load(e: FrameElement, length: float) -> np.ndarray:
    """向下均布荷载的一致节点荷载向量（local == global，水平单元）。"""
    w = e.udl
    return np.array(
        [0.0, -w * length / 2.0, -w * length**2 / 12.0, 0.0, -w * length / 2.0, w * length**2 / 12.0],
        dtype=float,
    )


def _fixed_end_forces(e: FrameElement, length: float) -> np.ndarray:
    """固端力向量（= 负数的一致节点荷载）。"""
    return -_consistent_load(e, length)


def solve_frame(
    nodes: list[FrameNode],
    elements: list[FrameElement],
    supports: list[Support],
    nodal_loads: list[NodalLoad] | None = None,
) -> FrameResult:
    if not nodes or not elements:
        raise InputError("框架至少需要一个节点与一个单元")

    count = len(nodes)
    dofs = 3 * count
    # 水平单元检查
    for index, element in enumerate(elements):
        if abs(nodes[element.i].y - nodes[element.j].y) > 1e-9:
            raise InputError(f"单元 {index} 不是水平单元（当前实现只支持水平梁）")
        if nodes[element.i].x == nodes[element.j].x:
            raise InputError(f"单元 {index} 长度为零")

    stiffness = np.zeros((dofs, dofs))
    load = np.zeros(dofs)

    for element in elements:
        length = abs(nodes[element.j].x - nodes[element.i].x)
        k = _stiffness(element, length)
        idx = [
            3 * element.i + 0, 3 * element.i + 1, 3 * element.i + 2,
            3 * element.j + 0, 3 * element.j + 1, 3 * element.j + 2,
        ]
        for a in range(6):
            for b in range(6):
                stiffness[idx[a], idx[b]] += k[a, b]
        load[idx] = load[idx] + _consistent_load(element, length)

    for nodal in nodal_loads or []:
        load[3 * nodal.node + 1] += nodal.fy
        load[3 * nodal.node + 2] += nodal.mz

    fixed: dict[int, float] = {}
    for support in supports:
        if support.fix_ux:
            fixed[3 * support.node + 0] = 0.0
        if support.fix_uy:
            fixed[3 * support.node + 1] = 0.0
        if support.fix_rz:
            fixed[3 * support.node + 2] = 0.0

    constrained = sorted(fixed)
    free = [dof for dof in range(dofs) if dof not in fixed]
    if not free:
        raise InputError("所有自由度都被约束，没有可求解的位移")

    k_ff = stiffness[np.ix_(free, free)]
    k_fc = stiffness[np.ix_(free, constrained)]
    f_f = load[free] - k_fc @ np.array([fixed[dof] for dof in constrained])
    try:
        u_f = np.linalg.solve(k_ff, f_f)
    except np.linalg.LinAlgError as exc:
        raise SingularSystemError(
            "刚度矩阵奇异：结构可能缺少约束（机构）或存在未连接的节点"
        ) from exc

    displacement = np.zeros(dofs)
    displacement[free] = u_f
    for dof, value in fixed.items():
        displacement[dof] = value

    reaction_vector = stiffness @ displacement - load
    reactions: dict[int, tuple[float, float, float]] = {}
    for support in supports:
        base = 3 * support.node
        reactions[support.node] = (
            float(reaction_vector[base + 0]),
            float(reaction_vector[base + 1]),
            float(reaction_vector[base + 2]),
        )

    end_forces: list[np.ndarray] = []
    max_moment = 0.0
    max_shear = 0.0
    for element in elements:
        length = abs(nodes[element.j].x - nodes[element.i].x)
        k = _stiffness(element, length)
        u_local = displacement[
            [3 * element.i + 0, 3 * element.i + 1, 3 * element.i + 2,
             3 * element.j + 0, 3 * element.j + 1, 3 * element.j + 2]
        ]
        forces = k @ u_local + _fixed_end_forces(element, length)
        end_forces.append(forces)

        # 沿单元采样内力，取包络
        for step in range(21):
            x = length * step / 20.0
            moment = -forces[2] + forces[1] * x - element.udl * x * x / 2.0
            shear = forces[1] - element.udl * x
            max_moment = max(max_moment, abs(moment))
            max_shear = max(max_shear, abs(shear))

    vertical = displacement.reshape(count, 3)[:, 1]
    worst = int(np.argmax(np.abs(vertical)))
    return FrameResult(
        displacements=displacement.reshape(count, 3),
        reactions=reactions,
        element_end_forces=end_forces,
        max_moment=max_moment,
        max_shear=max_shear,
        max_deflection=float(abs(vertical[worst])),
        deflection_node=worst,
        notes=["仅水平单元", "未计入剪切变形（Euler-Bernoulli 梁）"],
    )


def internal_force_at(
    element: FrameElement, end_forces: np.ndarray, x: float
) -> tuple[float, float]:
    """单元内 x 处的 (弯矩, 剪力)；弯矩下凸为正。"""
    moment = -end_forces[2] + end_forces[1] * x - element.udl * x * x / 2.0
    shear = end_forces[1] - element.udl * x
    return float(moment), float(shear)
