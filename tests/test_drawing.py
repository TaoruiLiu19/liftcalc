"""绘图层测试：版面、尺寸链、三端一致性。

这些断言是补上的缺口——原来绘图没有任何测试，重复代码、缺失的尺寸箭头、
写死的"1:100"都没被发现。
"""

from __future__ import annotations

import ast
import math
import re
from pathlib import Path

import pytest

from liftcalc.core.result import ComputationResult
from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.drawing.figures import elevation_figure, figures_for
from liftcalc.drawing.primitives import (
    ALIGN_CENTER,
    Circle,
    Figure,
    Image,
    Line,
    Polyline,
    Text,
    item_bbox,
)
from liftcalc.drawing.sheet import Sheet, overlaps
from liftcalc.drawing.style import SCALE_LADDER

PACK = Path(__file__).resolve().parents[1] / "src" / "liftcalc" / "data" / "pack"
SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Repo:
    path = tmp_path_factory.mktemp("db") / "drawing.sqlite"
    build_db(PACK, path, "test")
    return Repo(path)


def _case(model: str = "QY70K-1", **overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "kind": "crane.capability",
        "mode": "single",
        "payload": 10.0,
        "hook_mass": 0.616,
        "rigging": 0.3,
        "crane": {"brand": "徐工", "model": model},
    }
    case.update(overrides)
    return case


def _dual(**overrides: object) -> dict[str, object]:
    case = _case(
        mode="dual",
        payload=20.0,
        left_share=0.6,
        asynchronism=1.1,
        second={"brand": "徐工", "model": "QY70K-1"},
    )
    case.update(overrides)
    return case


def _texts(figure: Figure) -> list[str]:
    return [item.content for item in figure.primitives if isinstance(item, Text)]


def _paper_size(figure: Figure) -> tuple[float, float]:
    return figure.meta.get("paper", (figure.width, figure.height))


# ---------------------------------------------------------------------------
# 图元与文字约定
# ---------------------------------------------------------------------------
def test_text_bbox_follows_alignment_and_rotation() -> None:
    left = Text(x=10, y=20, content="AB", height=3)
    center = Text(x=10, y=20, content="AB", height=3, align=ALIGN_CENTER)
    rotated = Text(x=10, y=20, content="AB", height=3, align=ALIGN_CENTER, angle=90)

    x0, y0, _x1, y1 = left.bbox()
    assert x0 == pytest.approx(10)
    assert y1 == pytest.approx(20)
    assert y0 == pytest.approx(17)

    width = left.bbox()[2] - left.bbox()[0]
    assert center.bbox()[0] == pytest.approx(left.bbox()[0] - width / 2)   # 居中左移半个字宽
    assert center.bbox()[2] - center.bbox()[0] == pytest.approx(width)     # 字宽不变

    rx0, ry0, rx1, ry1 = rotated.bbox()
    assert rx0 == pytest.approx(10, abs=1e-9)          # 旋转后字框在锚点右侧
    assert rx1 == pytest.approx(10 + 3, abs=1e-9)
    assert (rx1 - rx0) == pytest.approx(3, abs=1e-9)
    assert (ry1 - ry0) > 3                            # 竖向展开


def test_figure_bbox_skips_layers() -> None:
    figure = Figure(title="t", width=10, height=10)
    figure.add(Line(x1=0, y1=0, x2=10, y2=10, layer="OUTLINE"))
    figure.add(Line(x1=-5, y1=-5, x2=5, y2=5, layer="NOTE"))
    assert figure.bbox()[0] == pytest.approx(-5)
    assert figure.bbox(skip_layers=("NOTE",))[0] == pytest.approx(0)


def test_no_duplicate_top_level_functions() -> None:
    """回归：figures.py 曾经把 _arrow 和整段立面代码各写了两遍。"""
    for path in (SRC / "liftcalc" / "drawing").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
        duplicates = {name for name in names if names.count(name) > 1}
        assert not duplicates, f"{path.name} 有重复定义的函数：{duplicates}"


# ---------------------------------------------------------------------------
# 立面图内容
# ---------------------------------------------------------------------------
CHAIN_LABELS = ("R=", "f=", "g=", "H=", "Hz=", "h0=", "h1=", "h2=", "h3=", "L=", "a=", "E=")


@pytest.mark.parametrize("model", ["QY70K-1", "QY100H-3", "QY130H-1", "QAY200"])
def test_elevation_has_dimension_chain(repo: Repo, model: str) -> None:
    figure = elevation_figure(elevation_result(repo, model))
    assert figure is not None
    joined = " ".join(_texts(figure))
    for label in CHAIN_LABELS:
        # 尺寸线太短时只写数值（尺寸链惯例），两种形式都算存在
        value = label.split("=", 1)[1]
        assert label in joined or value in joined, f"{model} 立面图缺尺寸 {label}"


def elevation_result(repo: Repo, model: str) -> ComputationResult:
    from liftcalc.services.calc import run_case

    return run_case(_case(model), repo)


def test_elevation_stays_inside_the_sheet(repo: Repo) -> None:
    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    width, height = _paper_size(figure)
    for item in figure.primitives:
        box = item_bbox(item)
        if box is None:
            continue
        assert box[0] >= -0.01 and box[2] <= width + 0.01, f"{item} 超出图幅宽度"
        assert box[1] >= -0.01 and box[3] <= height + 0.01, f"{item} 超出图幅高度"


def test_elevation_does_not_collide_with_furniture(repo: Repo) -> None:
    """几何图元（不是包围盒）不得压到标题栏/说明/性能表。"""
    for model in ("QY70K-1", "QAY200", "QY130H-1"):
        figure = elevation_figure(elevation_result(repo, model))
        assert figure is not None
        start, end = figure.meta["geometry_span"]
        geometry = figure.primitives[start:end]
        for rect in figure.meta["reserved"]:
            for item in geometry:
                box = item_bbox(item)
                if box is None:
                    continue
                assert not overlaps(box, rect), f"{model}: {item} 压到图面块 {rect}"


def test_scale_matches_title_block_and_geometry(repo: Repo) -> None:
    result = elevation_result(repo, "QY70K-1")
    figure = elevation_figure(result)
    assert figure is not None
    denom = figure.meta["scale_denom"]
    assert denom in SCALE_LADDER
    assert figure.meta["scale"] == pytest.approx(1000.0 / denom)

    joined = " ".join(_texts(figure))
    assert f"1:{denom}" in joined                       # 标题栏与说明里的比例一致

    # 用 R 尺寸线长度反推比例：R 米 → R*scale mm（±0.2 mm）
    radius = float(result.aux["capability"]["max_radius"])
    lengths = [
        abs(item.x2 - item.x1)
        for item in figure.primitives
        if isinstance(item, Line) and item.layer == "DIM" and abs(item.y1 - item.y2) < 1e-9
    ]
    assert any(abs(length - radius * figure.meta["scale"]) < 0.2 for length in lengths), (
        "找不到与 R 等长的尺寸线"
    )


def test_derived_angle_is_flagged(repo: Repo) -> None:
    """QY130H-1 的性能表没有仰角列，图示仰角是反算的，必须带"≈"和说明。"""
    figure = elevation_figure(elevation_result(repo, "QY130H-1"))
    assert figure is not None
    assert figure.meta["derived_angle"] is True
    joined = " ".join(_texts(figure))
    assert "≈a=" in joined
    assert "无仰角列" in joined


def test_dual_mode_reports_second_crane(repo: Repo) -> None:
    from liftcalc.services.calc import run_case

    figure = elevation_figure(run_case(_dual(), repo))
    assert figure is not None
    joined = " ".join(_texts(figure))
    assert "辅吊最远" in joined and "双机抬吊" in joined


def test_goods_sit_at_requested_clearance(repo: Repo) -> None:
    from liftcalc.services.calc import run_case

    result = run_case(_case(clearance_m=2.0, load_height_m=4.0, load_width_m=3.0), repo)
    figure = elevation_figure(result)
    assert figure is not None
    assert figure.meta["load_bottom"] == pytest.approx(2.0)
    assert "h1=2.00" in " ".join(_texts(figure))


def test_lift_height_above_tip_is_clamped(repo: Repo) -> None:
    """净空要得比臂端还高时，吊钩收到臂端极限，并在说明里讲清楚。"""
    from liftcalc.services.calc import run_case

    result = run_case(_case(clearance_m=40.0), repo)
    figure = elevation_figure(result)
    assert figure is not None
    assert figure.meta["hook_h"] < 30.0
    assert "臂端极限" in " ".join(_texts(figure))


# ---------------------------------------------------------------------------
# 三种输出
# ---------------------------------------------------------------------------
def test_svg_uses_alignment_and_rotation(repo: Repo) -> None:
    from liftcalc.drawing.svg import to_svg

    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    svg = to_svg(figure)
    assert 'text-anchor="middle"' in svg                # 居中尺寸文字
    assert "rotate(90" in svg or "rotate(-90" in svg     # 竖排尺寸文字
    assert "stroke-width" in svg


def test_dxf_text_matches_primitive(repo: Repo, tmp_path: Path) -> None:
    import ezdxf

    from liftcalc.drawing.dxf import to_dxf

    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    path = to_dxf(figure, tmp_path / "elevation.dxf")
    doc = ezdxf.readfile(path)
    texts = [entity for entity in doc.modelspace() if entity.dxftype() == "TEXT"]
    assert len(texts) == len([p for p in figure.primitives if isinstance(p, Text)])

    rotated = [entity for entity in texts if abs(float(entity.dxf.rotation)) > 1e-6]
    assert rotated, "竖排尺寸文字应有 rotation"
    centered = [entity for entity in texts if int(entity.dxf.halign) == 1]
    assert centered, "居中文字应使用 halign=CENTER"
    layers = {entity.dxf.layer for entity in texts}
    assert {"DIM", "TEXT", "NOTE"} <= layers


def test_dxf_has_no_raster_but_keeps_body(repo: Repo, tmp_path: Path) -> None:
    """DXF 不能放位图，所以 DXF 版本用车身边线矢量，不能是空车身。"""
    from liftcalc.drawing.dxf import to_dxf

    result = elevation_result(repo, "QY70K-1")
    raster = figures_for(result, body="image")
    vector = figures_for(result, body="vector")
    raster_elev = next(f for f in raster if f.title == "吊装立面图")
    vector_elev = next(f for f in vector if f.title == "吊装立面图")
    assert any(isinstance(item, Image) for item in raster_elev.primitives)
    assert not any(isinstance(item, Image) for item in vector_elev.primitives)
    assert any(isinstance(item, Circle) for item in vector_elev.primitives)

    path = to_dxf(raster_elev, tmp_path / "raster.dxf")
    import ezdxf

    doc = ezdxf.readfile(path)
    kinds = {entity.dxftype() for entity in doc.modelspace()}
    assert "LINE" in kinds and "LWPOLYLINE" in kinds


def test_png_written_with_expected_size(repo: Repo, tmp_path: Path) -> None:
    from PIL import Image as PILImage

    from liftcalc.drawing.png import to_png

    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    path = to_png(figure, tmp_path / "elevation.png", px_per_mm=4)
    image = PILImage.open(path)
    margin = 2 * 2 * 4          # MARGIN_MM=2 两侧
    assert image.width == pytest.approx(figure.width * 4 + margin, abs=8)
    assert image.height == pytest.approx(figure.height * 4 + margin, abs=8)


def test_arrow_heads_present(repo: Repo) -> None:
    """回归：_arrow 曾经定义了两次却从未被调用，尺寸线没有箭头。"""
    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    short = [
        item
        for item in figure.primitives
        if isinstance(item, Line) and item.layer == "DIM"
        and 0.2 < math.hypot(item.x2 - item.x1, item.y2 - item.y1) < 2.5
    ]
    assert len(short) >= 20, "尺寸箭头数量太少"


def test_no_stray_text_or_geometry_outside_content(repo: Repo) -> None:
    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    sheet = Sheet(width=figure.width, height=figure.height)
    x0, _y0, x1, _y1 = sheet.inner
    for item in figure.primitives:
        if isinstance(item, Text) and item.layer in {"DIM", "TEXT", "NOTE"}:
            box = item_bbox(item)
            assert box is not None
            assert box[0] >= x0 - 0.01 and box[2] <= x1 + 0.01, f"文字超出图框：{item.content}"


def test_every_figure_fits_its_page(repo: Repo) -> None:
    """回归：吊耳/截面图的图元以形心为原点，曾有负坐标被画到纸外。"""
    import json

    from liftcalc.services.calc import run_case

    for kind, name in (("eye", "eye-001"), ("beam", "beam-001")):
        path = Path(__file__).resolve().parents[1] / "cases" / kind / name / "case.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        for figure in figures_for(run_case(payload, repo)):
            for item in figure.primitives:
                box = item_bbox(item)
                if box is None:
                    continue
                assert box[0] >= -0.01 and box[1] >= -0.01, f"{figure.title}: {item} 超出页面"
                assert box[2] <= figure.width + 0.01 and box[3] <= figure.height + 0.01, (
                    f"{figure.title}: {item} 超出页面"
                )


def test_polyline_points_are_finite(repo: Repo) -> None:
    figure = elevation_figure(elevation_result(repo, "QY70K-1"))
    assert figure is not None
    for item in figure.primitives:
        if isinstance(item, Polyline):
            for x, y in item.points:
                assert math.isfinite(x) and math.isfinite(y)
        if isinstance(item, Text):
            assert re.search(r"[0-9A-Za-z\u4e00-\u9fff]", item.content), (
                f"空文字或无意义文字：{item.content!r}"
            )
