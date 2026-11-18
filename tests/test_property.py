"""属性测试：用 hypothesis 查单调性、对称性与量纲一致性。"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from liftcalc.core.tolerance import close
from liftcalc.core.units import Q
from liftcalc.sections import custom

SIZE = st.floats(min_value=10.0, max_value=2000.0, allow_nan=False, allow_infinity=False)
SCALE = st.floats(min_value=1.01, max_value=5.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=40, deadline=None)
@given(b=SIZE, h=SIZE, k=SCALE)
def test_rect_scaling_law(b: float, h: float, k: float) -> None:
    """几何相似缩放：A ∝ k²，I ∝ k⁴。"""
    small = custom.rect(Q(b, "mm"), Q(h, "mm"))
    large = custom.rect(Q(b * k, "mm"), Q(h * k, "mm"))
    assert close(
        float(large.area.to("mm**2").magnitude) / float(small.area.to("mm**2").magnitude),
        k * k,
        rel=1e-9,
    )
    assert close(
        float(large.ix.to("mm**4").magnitude) / float(small.ix.to("mm**4").magnitude),
        k**4,
        rel=1e-9,
    )


@settings(max_examples=30, deadline=None)
@given(b=SIZE, h=SIZE)
def test_rect_modulus_ordering(b: float, h: float) -> None:
    """Wx 与 Wy 的大小关系应与 b、h 的大小关系一致。"""
    props = custom.rect(Q(b, "mm"), Q(h, "mm"))
    wx = float(props.wx.to("mm**3").magnitude)
    wy = float(props.wy.to("mm**3").magnitude)
    if h > b:
        assert wx > wy
    elif h < b:
        assert wx < wy


@settings(max_examples=30, deadline=None)
@given(d=SIZE, t=st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False))
def test_pipe_lighter_than_bar(d: float, t: float) -> None:
    """同外径下，管比实心圆轻但惯性矩更小。"""
    if 2 * t >= d:
        return
    pipe = custom.pipe(Q(d, "mm"), Q(d - 2 * t, "mm"))
    bar = custom.round_bar(Q(d, "mm"))
    assert float(pipe.area.to("mm**2").magnitude) < float(bar.area.to("mm**2").magnitude)
    assert float(pipe.ix.to("mm**4").magnitude) < float(bar.ix.to("mm**4").magnitude)


@settings(max_examples=20, deadline=None)
@given(b=SIZE, h=SIZE)
def test_principal_moments_bracket_axis_moments(b: float, h: float) -> None:
    props = custom.rect(Q(b, "mm"), Q(h, "mm"))
    i1 = float(props.i1.to("mm**4").magnitude)
    i2 = float(props.i2.to("mm**4").magnitude)
    ix = float(props.ix.to("mm**4").magnitude)
    iy = float(props.iy.to("mm**4").magnitude)
    assert i1 >= max(ix, iy) * (1 - 1e-9)
    assert i2 <= min(ix, iy) * (1 + 1e-9)
