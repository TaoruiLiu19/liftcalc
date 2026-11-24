import math

import pytest

from liftcalc.drawing.body import MAIN_WINCH, MAIN_WINCH_RADIUS
from liftcalc.drawing.figures import (
    BOOM_JOINTS, LIFT_SHEAVE_RADIUS, ElevationModel, _Paper, _boom_half, _draw_hook_block, _draw_load, _draw_rope,
)
from liftcalc.drawing.primitives import Figure, Line, Polyline


@pytest.mark.parametrize("length,angle,radius", [(25.98, 67.6, 10), (32, 56, 17), (18, 42, 14)])
def test_hook_and_head_share_a_vertical_load_line(length, angle, radius):
    model = ElevationModel(length, angle, radius, 8, 3, 4)
    paper = _Paper(8, 120, 20)
    sheet = Figure("", 300, 420)
    _draw_rope(sheet, paper, model)
    rope = [item for item in sheet.primitives if item.layer == "RIGGING"]
    assert len(rope) >= 8
    points = [item.points if isinstance(item, Polyline) else ((item.x1, item.y1), (item.x2, item.y2))
              for item in rope]
    assert math.dist(points[0][0], paper(*MAIN_WINCH)) == pytest.approx(MAIN_WINCH_RADIUS * paper.s)
    assert all(a[-1] == pytest.approx(b[0]) for a, b in zip(points[-6:], points[-5:], strict=False))
    spans = [span for span in points[-6:] if len(span) == 2 and span[0][0] == pytest.approx(span[1][0])]
    hook_x, _ = paper(*model.hook_seat)
    assert len(spans) == 2
    assert sorted(a[0] for a, _ in spans) == pytest.approx(
        [hook_x - LIFT_SHEAVE_RADIUS * paper.s, hook_x + LIFT_SHEAVE_RADIUS * paper.s]
    )
    assert all(min(a[1], b[1]) == pytest.approx(paper(*model.block_sheave)[1]) for a, b in spans)
    assert math.dist(model.hinge, model.tip) == pytest.approx(length)
    _draw_hook_block(sheet, paper, model)
    hook = sheet.primitives[-1]
    seat = paper(*model.hook_seat)
    assert isinstance(hook, Polyline) and seat in hook.points
    load_start = len(sheet.primitives)
    _draw_load(sheet, paper, model)
    slings = [item for item in sheet.primitives[load_start:] if isinstance(item, Line) and item.layer == "RIGGING"]
    assert len(slings) == 2 and all((line.x1, line.y1) == seat for line in slings)


def test_telescoping_sections_narrow_at_every_collar():
    widths = [_boom_half(start) for start in (0, *BOOM_JOINTS)]
    assert all(outer > inner > 0 for outer, inner in zip(widths, widths[1:]))


def test_shallow_boom_shows_the_overlapped_rope_as_dashes():
    paper = _Paper(8, 200, 20)
    sheet = Figure("", 300, 420)
    _draw_rope(sheet, paper, ElevationModel(25.98, 29.2, 22, 8, 3, 4))
    rope = [item for item in sheet.primitives if item.layer == "RIGGING"]
    feed = rope[:-6]
    assert len(feed) > 2
    assert any(math.dist((a.x2, a.y2), (b.x1, b.y1)) > .5 for a, b in zip(feed, feed[1:]))
