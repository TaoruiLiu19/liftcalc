import math

import pytest

from liftcalc.drawing.figures import (
    BOOM_JOINTS, ElevationModel, _Paper, _boom_half, _draw_hook_block, _draw_load, _draw_rope,
)
from liftcalc.drawing.primitives import Figure, Line, Polyline


@pytest.mark.parametrize("length,angle,radius", [(25.98, 67.6, 10), (32, 56, 17), (18, 42, 14)])
def test_hook_and_head_share_a_vertical_load_line(length, angle, radius):
    model = ElevationModel(length, angle, radius, 8, 3, 4)
    paper = _Paper(8, 120, 20)
    sheet = Figure("", 300, 420)
    _draw_rope(sheet, paper, model)
    left, right = sheet.primitives
    assert left.x1 == left.x2 and right.x1 == right.x2
    assert left.x1 != right.x1
    assert (left.x1 + right.x1) / 2 == pytest.approx(paper(*model.hook_seat)[0])
    assert math.dist(model.hinge, model.tip) == pytest.approx(length)
    _draw_hook_block(sheet, paper, model)
    hook = sheet.primitives[-1]
    seat = paper(*model.hook_seat)
    assert isinstance(hook, Polyline) and seat in hook.points
    _draw_load(sheet, paper, model)
    slings = [item for item in sheet.primitives if isinstance(item, Line) and item.layer == "RIGGING"]
    assert len(slings) == 2 and all((line.x1, line.y1) == seat for line in slings)


def test_telescoping_sections_narrow_at_every_collar():
    widths = [_boom_half(start) for start in (0, *BOOM_JOINTS)]
    assert all(outer > inner > 0 for outer, inner in zip(widths, widths[1:]))
