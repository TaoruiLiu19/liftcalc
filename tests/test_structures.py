"""梁 / 索具 / 吊车 / 有限元 / 规范校核 的解析解与边界测试。"""

from __future__ import annotations

import math

import pytest

from liftcalc.codecheck.steel_gb import check_slenderness, slenderness
from liftcalc.core.errors import InfeasibleSectionError, OutOfTableError
from liftcalc.core.result import Verdict
from liftcalc.core.tolerance import close
from liftcalc.core.units import Q
from liftcalc.crane.select import (
    CapacityRow,
    OutriggerLayout,
    check_working_region,
    ground_pressure,
    load_ratio,
    lookup_capacity,
    outrigger_reactions,
)
from liftcalc.fea.frame2d import FrameElement, FrameNode, NodalLoad, Support, solve_frame
from liftcalc.lifting.beam import BeamInput, check_beam
from liftcalc.lifting.rigging import (
    RopeSpec,
    SelectionOption,
    SlingArrangement,
    branch_force,
    check_rigging,
    rope_break_force,
    select_from_table,
)

# 库里 DEMO-HW300x300 的截面特性（由公称尺寸算出）
I_MM4 = 199_327_500.0
W_MM3 = 1_328_850.0
E_MPA = 206000.0


def _beam(**overrides: object) -> BeamInput:
    base = {
        "support": "simply_supported",
        "span": Q(4000, "mm"),
        "total_load": Q(200, "kN"),
        "load_type": "udl",
        "inertia": Q(I_MM4, "mm**4"),
        "section_modulus": Q(W_MM3, "mm**3"),
        "e_modulus": Q(E_MPA, "MPa"),
        "web_area": Q(2700, "mm**2"),
        "fy": Q(355, "MPa"),
    }
    base.update(overrides)
    return BeamInput(**base)  # type: ignore[arg-type]


def _by_id(outcome: object) -> dict[str, object]:
    return {check.id: check for check in outcome.checks}  # type: ignore[attr-defined]


# ---------------------------------------------------------------- 梁：解析解

def test_beam_simply_supported_udl() -> None:
    outcome = check_beam(_beam())
    checks = _by_id(outcome)

    q = 200_000.0 / 4.0  # N/m
    length = 4.0
    moment = q * length**2 / 8.0  # N·m
    sigma = moment * 1000.0 / W_MM3  # N·mm / mm³ = MPa
    assert close(checks["beam.bending"].value, sigma, 1e-6)  # type: ignore[attr-defined]

    deflection = 5 * q * length**4 / (384 * E_MPA * 1e6 * I_MM4 * 1e-12) * 1000.0
    assert close(checks["beam.deflection"].value, deflection, 1e-4)  # type: ignore[attr-defined]


def test_beam_deflection_formula_matches_textbook() -> None:
    """20 t 吊件、4 m 跨、HW300×300：挠度应约 4 mm。"""
    outcome = check_beam(_beam())
    assert close(_by_id(outcome)["beam.deflection"].value, 4.06, 0.02)  # type: ignore[attr-defined]


def test_beam_cantilever_udl() -> None:
    outcome = check_beam(_beam(support="cantilever", total_load=Q(100, "kN")))
    checks = _by_id(outcome)
    q = 100_000.0 / 4.0
    moment = q * 4.0**2 / 2.0
    sigma = moment * 1000.0 / W_MM3
    assert close(checks["beam.bending"].value, sigma, 1e-6)  # type: ignore[attr-defined]


def test_beam_point_mid_moment() -> None:
    outcome = check_beam(_beam(load_type="point_mid"))
    checks = _by_id(outcome)
    moment = 200_000.0 * 4.0 / 4.0
    assert close(checks["beam.bending"].value, moment * 1000.0 / W_MM3, 1e-6)  # type: ignore[attr-defined]


def test_beam_deflection_limit_drives_verdict() -> None:
    """跨度 8 m 时挠度先崩：应判 FAIL 且控制项为挠度。"""
    outcome = check_beam(_beam(span=Q(8000, "mm"), load_type="point_mid", total_load=Q(200, "kN")))
    checks = _by_id(outcome)
    assert checks["beam.deflection"].verdict is Verdict.FAIL  # type: ignore[attr-defined]
    deflection = checks["beam.deflection"]  # type: ignore[attr-defined]
    assert deflection.ratio is not None and deflection.ratio > 1.0


def test_beam_without_fy_is_na_not_fail() -> None:
    outcome = check_beam(_beam(fy=None))
    assert _by_id(outcome)["beam.bending"].verdict is Verdict.NA  # type: ignore[attr-defined]


def test_beam_invalid_support_combination() -> None:
    with pytest.raises(InfeasibleSectionError):
        check_beam(_beam(support="simply_supported", load_type="point_tip"))


# ---------------------------------------------------------------- 索具

def test_rope_break_force_formula() -> None:
    spec = RopeSpec(diameter=Q(20, "mm"), rated_strength=Q(1770, "MPa"), k_prime=0.356)
    expected = 0.356 * 20**2 * 1770  # N
    assert close(float(rope_break_force(spec).to("N").magnitude), expected, 1e-12)


def test_branch_force_with_angle() -> None:
    total = Q(682, "kN")
    force = branch_force(total, SlingArrangement(branches=4, angle_deg=45.0))
    expected = 682_000 / (4 * math.cos(math.radians(45.0)))
    assert close(float(force.to("N").magnitude), expected, 1e-12)


def test_branch_force_single_vertical() -> None:
    force = branch_force(Q(100, "kN"), SlingArrangement(branches=1, angle_deg=0.0))
    assert close(float(force.to("kN").magnitude), 100.0, 1e-12)


def test_select_from_table_takes_next_size_up() -> None:
    options = [SelectionOption("25t", 25.0), SelectionOption("35t", 35.0)]
    assert select_from_table(24.1, options).name == "25t"
    assert select_from_table(26.0, options).name == "35t"


def test_select_over_table_raises() -> None:
    options = [SelectionOption("25t", 25.0)]
    with pytest.raises(OutOfTableError):
        select_from_table(40.0, options)


def test_rigging_full_chain() -> None:
    outcome = check_rigging(
        total_load=Q(682, "kN"),
        arrangement=SlingArrangement(branches=4, angle_deg=45.0),
        rope=RopeSpec(diameter=Q(20, "mm"), rated_strength=Q(1770, "MPa")),
        shackle_options=[SelectionOption("25t", 25.0), SelectionOption("35t", 35.0)],
    )
    checks = _by_id(outcome)
    assert "rigging.rope" in checks
    # 252kN 破断 < 241.2×6=1447kN 需求
    assert checks["rigging.rope"].verdict is Verdict.FAIL  # type: ignore[attr-defined]
    assert checks["rigging.shackle"].verdict is Verdict.PASS  # type: ignore[attr-defined]


def test_rigging_warns_on_large_angle() -> None:
    outcome = check_rigging(
        total_load=Q(100, "kN"), arrangement=SlingArrangement(branches=2, angle_deg=65.0)
    )
    assert any("60°" in warning for warning in outcome.warnings)


# ---------------------------------------------------------------- 吊车（查表，不插值）

ROWS = [
    CapacityRow(boom_len=11.6, radius=3.0, rated_load=70.0),
    CapacityRow(boom_len=11.6, radius=4.0, rated_load=54.0),
    CapacityRow(boom_len=11.6, radius=5.0, rated_load=47.0),
    CapacityRow(boom_len=44.5, radius=3.0, rated_load=70.0),
    CapacityRow(boom_len=44.5, radius=12.0, rated_load=9.0),
    CapacityRow(boom_len=44.5, radius=14.0, rated_load=7.5),
]


def test_lookup_hits_grid_exactly() -> None:
    result = lookup_capacity(ROWS, boom_len=44.5, radius=12.0)
    assert result.rated_load == 9.0
    assert result.radius_rounded is False
    assert result.boom_rounded is False


def test_lookup_rounds_radius_up_not_interpolates() -> None:
    """原厂说明第 7 条：幅度与表不符时取下一档，绝不插值。"""
    result = lookup_capacity(ROWS, boom_len=44.5, radius=12.5)
    assert result.used_radius == 14.0
    assert result.rated_load == 7.5
    assert result.radius_rounded is True


def test_lookup_rounds_boom_up() -> None:
    result = lookup_capacity(ROWS, boom_len=30.0, radius=12.0)
    assert result.used_boom_len == 44.5
    assert result.boom_rounded is True


def test_lookup_refuses_beyond_table() -> None:
    with pytest.raises(OutOfTableError):
        lookup_capacity(ROWS, boom_len=44.5, radius=20.0)
    with pytest.raises(OutOfTableError):
        lookup_capacity(ROWS, boom_len=60.0, radius=10.0)


def test_jib_installed_reduces_main_boom_rating() -> None:
    """原厂说明第 8 条：副臂在作业状态时主臂额定减少 2000 kg。"""
    result = lookup_capacity(ROWS, boom_len=44.5, radius=12.0, jib_installed=True)
    assert result.adjusted_load == 7.0
    assert result.adjustments


def test_load_ratio_includes_hook_mass() -> None:
    ratio = load_ratio(
        payload=60.0, hook_mass=0.6, rigging=2.0, dynamic_factor=1.1, rated_load=76.0
    )
    assert close(ratio, (60 + 0.6 + 2 * 1.1) / 76, 1e-12)


def test_front_region_requires_fifth_outrigger() -> None:
    with pytest.raises(InfeasibleSectionError):
        check_working_region(region="前方", fifth_outrigger=False)
    check_working_region(region="前方", fifth_outrigger=True)
    check_working_region(region="360", fifth_outrigger=False)


def test_outrigger_symmetric_equal() -> None:
    reactions = outrigger_reactions(100.0, OutriggerLayout(lx=8.0, ly=6.0))
    assert all(close(value, 25.0, 1e-12) for value in reactions.values())


def test_outrigger_offset_favours_one_side() -> None:
    reactions = outrigger_reactions(100.0, OutriggerLayout(lx=8.0, ly=6.0, ex=2.0, ey=0.0))
    assert reactions["右前"] > reactions["左前"]
    assert close(sum(reactions.values()), 100.0, 1e-12)


def test_outrigger_offset_beyond_base_raises() -> None:
    with pytest.raises(InfeasibleSectionError):
        outrigger_reactions(100.0, OutriggerLayout(lx=8.0, ly=6.0, ex=5.0))


def test_ground_pressure() -> None:
    assert close(ground_pressure(20.0, 8.0), 2.5, 1e-12)

# ---------------------------------------------------------------- 有限元

def _frame(elements: int = 4, udl: float = 10_000.0) -> tuple[list, list, list]:
    """简支梁：4 m 跨、HW300×300、均布 10 kN/m。"""
    length_m = 4.0
    nodes = [FrameNode(x=length_m * i / elements, y=0.0) for i in range(elements + 1)]
    els = [
        FrameElement(
            i=i,
            j=i + 1,
            e_modulus=E_MPA * 1e6,
            area=1e-2,
            inertia=I_MM4 * 1e-12,
            udl=udl,
        )
        for i in range(elements)
    ]
    supports = [
        Support(node=0, fix_ux=True, fix_uy=True),
        Support(node=elements, fix_uy=True),
    ]
    return nodes, els, supports


def test_fea_simply_supported_udl_matches_analytic() -> None:
    length = 4.0
    w = 10_000.0  # N/m
    nodes, elements, supports = _frame(8)
    result = solve_frame(nodes, elements, supports, [])

    expected = 5 * w * length**4 / (384 * E_MPA * 1e6 * I_MM4 * 1e-12)
    assert close(result.max_deflection, expected, 1e-6)

    total_reaction = sum(value[1] for value in result.reactions.values())
    assert close(total_reaction, w * length, 1e-9)


def test_fea_max_moment_matches_analytic() -> None:
    """简支梁均布：Mmax = wL²/8（w=10 kN/m, L=4m → 20 kN·m）。"""
    nodes, elements, supports = _frame(8)
    result = solve_frame(nodes, elements, supports, [])
    assert close(result.max_moment, 10_000.0 * 4.0**2 / 8.0, 1e-6)


def test_fea_reactions_are_half_each() -> None:
    nodes, elements, supports = _frame(4)
    result = solve_frame(nodes, elements, supports, [])
    assert close(result.reactions[0][1], 20_000.0, 1e-9)
    assert close(result.reactions[4][1], 20_000.0, 1e-9)


def test_fea_point_load_on_simply_supported() -> None:
    nodes, elements, supports = _frame(4, udl=0.0)
    result = solve_frame(nodes, elements, supports, [NodalLoad(node=2, fy=-100_000.0)])
    assert close(result.reactions[0][1] + result.reactions[4][1], 100_000.0, 1e-9)
    assert close(result.reactions[0][1], 50_000.0, 1e-6)


def test_fea_mechanism_raises() -> None:
    from liftcalc.core.errors import SingularSystemError

    nodes = [FrameNode(0.0, 0.0), FrameNode(4.0, 0.0)]
    elements = [
        FrameElement(i=0, j=1, e_modulus=E_MPA * 1e6, area=1e-2, inertia=I_MM4 * 1e-12, udl=1e3)
    ]
    with pytest.raises(SingularSystemError):
        solve_frame(nodes, elements, [], [])


# ---------------------------------------------------------------- 规范

def test_slenderness() -> None:
    value = slenderness(effective_length=Q(4000, "mm"), radius_of_gyration=Q(130.5, "mm"))
    assert close(value, 4000 / 130.5, 1e-12)


def test_slenderness_limit_check() -> None:
    result = check_slenderness(effective_length=Q(4000, "mm"), radius_of_gyration=Q(130.5, "mm"))
    assert result.ok is True
    assert result.limit == 150.0
    assert "TBD-核定" in result.source
