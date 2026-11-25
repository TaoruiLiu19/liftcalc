"""Place annotation text in clear space and keep auxiliary strokes out of its lettering."""
from __future__ import annotations

import math
from dataclasses import replace

from liftcalc.drawing.primitives import ALIGN_CENTER, ALIGN_RIGHT, Circle, Figure, Line, Polyline, Text
from liftcalc.drawing.sheet import Rect, overlaps
from liftcalc.drawing.style import LAYER_CENTER, LAYER_DIM, LAYER_HIDDEN, LAYER_NOTE, LAYER_THIN

Point = tuple[float, float]
AUXILIARY_LAYERS = (LAYER_CENTER, LAYER_DIM, LAYER_HIDDEN, LAYER_NOTE, LAYER_THIN)
LABEL_GAP = .65


def _bounds(a: Point, b: Point) -> Rect:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def _edges(item: Line | Polyline):
    if isinstance(item, Line):
        yield (item.x1, item.y1), (item.x2, item.y2)
    elif item.points:
        end = (*item.points, item.points[0]) if item.closed else item.points
        yield from zip(end, end[1:])


def _box_interval(a: Point, b: Point, box: Rect) -> tuple[float, float] | None:
    """Return the parameter interval inside a rectangular box."""
    enter, leave = 0.0, 1.0
    for index, origin in enumerate(a):
        low, high = box[index], box[index+2]
        delta = b[index] - origin
        if abs(delta) < 1e-10:
            if origin < low or origin > high:
                return None
            continue
        first, last = sorted(((low-origin)/delta, (high-origin)/delta))
        enter, leave = max(enter, first), min(leave, last)
        if enter >= leave:
            return None
    return enter, leave


def stroke_text_interval(a: Point, b: Point, text: Text, gap: float = LABEL_GAP):
    """Intersect a stroke with the actual rotated text box, including its clearance."""
    if not text.content or not overlaps(_bounds(a,b),text.bbox(),margin=gap):
        return None
    angle = math.radians(text.angle)
    cosine, sine = math.cos(angle), math.sin(angle)
    width = text.width
    left = -width if text.align == ALIGN_RIGHT else -width/2 if text.align == ALIGN_CENTER else 0

    def local(p: Point) -> Point:
        dx, dy = p[0]-text.x, p[1]-text.y
        return cosine*dx+sine*dy, -sine*dx+cosine*dy

    return _box_interval(local(a),local(b),(left-gap,-text.height-gap,left+width+gap,gap))


def place_label(figure: Figure, candidates, *, bounds: Rect | None = None) -> Text | None:
    """Select the first candidate clear of text, outlines and linework already drawn."""
    occupied = [item.bbox() for item in figure.primitives if isinstance(item, Text) and item.content]
    circles = [item for item in figure.primitives if isinstance(item, Circle)]
    strokes = [(_bounds(a,b),a,b) for item in figure.primitives if isinstance(item,(Line,Polyline))
               for a,b in _edges(item)]
    for label in candidates:
        left,bottom,right,top = box = label.bbox()
        if bounds and (left < bounds[0] or bottom < bounds[1] or right > bounds[2] or top > bounds[3]):
            continue
        if any(overlaps(box, other, margin=1.1) for other in occupied):
            continue
        if any(math.hypot(max(left-c.cx,c.cx-right,0),max(bottom-c.cy,c.cy-top,0)) < c.r+LABEL_GAP
               and math.hypot(max(abs(left-c.cx),abs(right-c.cx)),max(abs(bottom-c.cy),abs(top-c.cy))) > c.r-LABEL_GAP
               for c in circles):
            continue
        if any(overlaps(box,edge,margin=LABEL_GAP) and stroke_text_interval(a,b,label)
               for edge,a,b in strokes):
            continue
        return label
    return None


def nearby_labels(text: Text):
    yield text
    for step in (4,8,12,18,26,38,55):
        for dx,dy in ((0,step),(0,-step),(-step,0),(step,0),(-step,step),
                      (step,step),(-step,-step),(step,-step)):
            yield replace(text,x=text.x+dx,y=text.y+dy)


def clear_annotation_lines(figure: Figure) -> None:
    """Split auxiliary strokes around label boxes while preserving solid object outlines."""
    labels = [(item.bbox(),item) for item in figure.primitives if isinstance(item, Text) and item.content]
    result = []
    for item in figure.primitives:
        if not isinstance(item,(Line,Polyline)) or item.layer not in AUXILIARY_LAYERS:
            result.append(item)
            continue
        visible = []
        changed = False
        for a,b in _edges(item):
            edge = _bounds(a,b)
            intervals = sorted(cut for box,text in labels if overlaps(edge,box,margin=LABEL_GAP)
                               and (cut := stroke_text_interval(a,b,text)))
            if not intervals:
                visible.append(Line(*a,*b,item.layer))
                continue
            changed = True
            at = 0.0
            dx,dy = b[0]-a[0],b[1]-a[1]
            for start,end in (*intervals,(1.0,1.0)):
                if start > at:
                    visible.append(Line(a[0]+dx*at,a[1]+dy*at,a[0]+dx*start,a[1]+dy*start,item.layer))
                at = max(at,end)
        result.extend(visible if changed else [item])
    figure.primitives[:] = result
