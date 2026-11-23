"""吊物尺寸、重心、四索受力、双机按重心分载。

这组断言把"重心偏心 → 四根索力不均""双机按重心分载"变成可复算的数字，
避免又退回到"按方框示意 + 60/40 拍脑袋"。
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from docx import Document

from liftcalc.core.errors import InfeasibleSectionError
from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.drawing.figures import elevation_figure, figures_for
from liftcalc.drawing.primitives import Circle, Text, item_bbox
from liftcalc.drawing.style import LAYER_CENTER, LAYER_RIGGING
from liftcalc.lifting import load_geometry as G
from liftcalc.report.render import render_report
from liftcalc.services.calc import run_case

PACK = Path(__file__).resolve().parents[1] / "src" / "liftcalc" / "data" / "pack"


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Repo:
    path = tmp_path_factory.mktemp("db-load") / "load.sqlite"
    build_db(PACK, path, "test")
    return Repo(path)


def _shape(**overrides: object) -> G.LoadShape:
    base: dict[str, object] = dict(length=6.0, width=3.0, height=2.5, sling_height=4.0)
    base.update(overrides)
    return G.LoadShape(**base)  # type: ignore[arg-type]


def _case(**overrides: object) -> dict[str, object]:
    case: dict[str, object] = {
        "kind": "crane.capability",
        "payload": 10.0,
        "hook_mass": 0.616,
        "rigging": 0.3,
        "crane": {"brand": "徐工", "model": "QY70K-1"},
        "load": {
            "length_m": 6.0,
            "width_m": 3.0,
            "height_m": 2.5,
            "cg": {"x": 0.4, "y": 0.2, "z": 0.3},
            "sling_height_m": 4.0,
        },
    }
    case.update(overrides)
    return case


# ---------------------------------------------------------------------------
# 几何与索力
# ---------------------------------------------------------------------------
def test_lugs_sit_on_the_top_face_corners() -> None:
    lugs = G.lugs(_shape())
    assert [(lug.name, lug.x, lug.y, lug.z) for lug in lugs] == [
        ("远前", 3.0, 1.5, 1.25),
        ("近前", -3.0, 1.5, 1.25),
        ("远后", 3.0, -1.5, 1.25),
        ("近后", -3.0, -1.5, 1.25),
    ]
    inset = G.lugs(_shape(lug_inset=0.5))
    assert inset[0].x == pytest.approx(2.5) and inset[0].y == pytest.approx(1.0)


def test_centred_load_has_four_equal_slings() -> None:
    report = G.sling_report(_shape(), weight_t=10.0)
    assert [round(item.share, 6) for item in report.slings] == [0.25] * 4
    assert max(item.force_t for item in report.slings) == pytest.approx(
        min(item.force_t for item in report.slings)
    )
    # 竖向分量之和等于吊重
    vertical = sum(item.force_t * math.cos(math.radians(item.angle_deg))
                   for item in report.slings)
    assert vertical == pytest.approx(10.0)


def test_eccentric_cg_makes_four_sling_forces_unequal() -> None:
    report = G.sling_report(_shape(cg_x=0.4, cg_y=0.3), weight_t=10.0)
    forces = [item.force_t for item in report.slings]
    assert len(set(round(value, 6) for value in forces)) == 4      # 四根各不相同
    assert report.max_force_t > report.min_force_t
    # 重心偏向 +x 一侧：远侧的两根比近侧的受力大
    assert report.slings[0].force_t > report.slings[1].force_t     # 远前 > 近前
    assert report.slings[0].force_t > report.slings[3].force_t     # 远前 > 近后
    vertical = sum(item.force_t * math.cos(math.radians(item.angle_deg))
                   for item in report.slings)
    assert vertical == pytest.approx(10.0)
    assert sum(item.share for item in report.slings) == pytest.approx(1.0)


def test_sling_angle_uses_real_geometry() -> None:
    # 吊点水平跨距 3.354 m、吊索高 4 m → atan(3.354/4) = 40.0°
    report = G.sling_report(_shape(), weight_t=10.0)
    assert report.slings[0].angle_deg == pytest.approx(
        math.degrees(math.atan2(math.hypot(3.0, 1.5), 4.0))
    )
    assert report.slings[0].length == pytest.approx(math.hypot(math.hypot(3.0, 1.5), 4.0))


def test_offset_hook_lengths_balance_horizontal_forces() -> None:
    shape = _shape(cg_x=-0.8, cg_y=0.3, cg_z=0.25, lug_inset=0.2, sling_height=None)
    report = G.sling_report(shape, weight_t=10)
    runs = [math.hypot(lug.x - shape.cg_x, lug.y - shape.cg_y) for lug in G.lugs(shape)]
    assert report.sling_height == pytest.approx(min(runs) * math.sqrt(3))
    assert [s.length for s in report.slings] == pytest.approx([math.hypot(r, report.sling_height) for r in runs])
    for axis in ("x", "y"):
        hook = getattr(shape, "cg_" + axis)
        assert sum(s.force_t * (hook - getattr(s, axis)) / s.length for s in report.slings) == pytest.approx(0)


def test_default_sling_height_is_sixty_degrees_to_horizontal() -> None:
    report = G.sling_report(_shape(sling_height=None), weight_t=10.0)
    assert report.derived_height is True
    assert report.slings[0].angle_deg == pytest.approx(30.0)
    assert report.sling_height == pytest.approx(math.hypot(3.0, 1.5) * math.sqrt(3))


def test_cg_outside_the_lug_rectangle_is_refused() -> None:
    with pytest.raises(InfeasibleSectionError):
        G.sling_report(_shape(cg_x=3.2), weight_t=10.0)
    with pytest.raises(InfeasibleSectionError):
        G.sling_report(_shape(cg_y=1.6), weight_t=10.0)


def test_cg_must_stay_inside_the_load() -> None:
    with pytest.raises(InfeasibleSectionError):
        G.sling_report(_shape(cg_x=3.5), weight_t=10.0)


def test_required_lift_height_adds_clearance_height_and_sling() -> None:
    assert G.required_lift_height(_shape(), clearance=1.0) == pytest.approx(1.0 + 2.5 + 4.0)


# ---------------------------------------------------------------------------
# 双机分载
# ---------------------------------------------------------------------------
def test_dual_split_follows_the_cg() -> None:
    split = G.dual_split(_shape(cg_x=1.2))
    assert split.left_x == pytest.approx(-3.0) and split.right_x == pytest.approx(3.0)
    assert split.left_share == pytest.approx((3.0 - 1.2) / 6.0)
    assert split.right_share == pytest.approx(1 - split.left_share)
    assert split.basis == "cg"
    centred = G.dual_split(_shape())
    assert centred.left_share == pytest.approx(0.5)


def test_dual_split_uses_requested_points() -> None:
    split = G.dual_split(_shape(cg_x=1.0), left_x=-2.0, right_x=2.0)
    assert split.left_share == pytest.approx((2.0 - 1.0) / 4.0)


def test_dual_split_refuses_cg_outside_hooks() -> None:
    with pytest.raises(InfeasibleSectionError):
        G.dual_split(_shape(cg_x=2.5), left_x=-2.0, right_x=2.0)


def test_fallback_split_is_sixty_forty() -> None:
    split = G.fallback_split()
    assert (split.left_share, split.right_share) == (0.6, 0.4)
    assert split.basis == "ratio"


# ---------------------------------------------------------------------------
# 端到端：case → aux / 图纸 / 计算书
# ---------------------------------------------------------------------------
def test_case_reports_load_and_derived_height(repo: Repo) -> None:
    result = run_case(_case(), repo)
    load = result.aux["load"]
    assert load["length_m"] == 6.0 and load["width_m"] == 3.0
    assert load["required_lift_height_m"] == pytest.approx(7.5)
    assert load["sling_height_m"] == pytest.approx(4.0)
    assert len(load["slings"]) == 4
    ids = {check.id for check in result.checks}
    assert {"load.cg", "load.sling"} <= ids
    # 性能表有起升高度列 → 用推算值参与查表
    assert any(check.id == "capability.lift_height" for check in result.checks)


def test_derived_height_is_not_checked_without_chart_data(repo: Repo) -> None:
    """性能表没有起升高度列时，只出数值并提示，不能把整个结论判成资料不足。"""
    result = run_case(_case(crane={"brand": "徐工", "model": "XCT100_1"}), repo)
    assert all(check.id != "capability.lift_height" for check in result.checks)
    assert any("没有起升高度列" in warning for warning in result.warnings)
    assert result.aux["load"]["required_lift_height_m"] > 0


def test_dual_load_split_follows_cg(repo: Repo) -> None:
    dual = _case(
        mode="dual",
        payload=20.0,
        second={"brand": "徐工", "model": "QY70K-1"},
        asynchronism=1.1,
    )
    dual["load"] = {"length_m": 8.0, "width_m": 3.0, "height_m": 2.0,
                    "cg": {"x": 1.2}, "sling_height_m": 3.0}
    result = run_case(dual, repo)
    cap = result.aux["capability"]
    assert cap["split"]["basis"] == "cg"
    assert cap["left_share"] == pytest.approx((4.0 - 1.2) / 8.0)
    # 重心偏向右机（+x）一侧，右机分到的荷载更大
    assert cap["right"]["required"] > cap["left"]["required"]
    assert any(check.id == "dual.split" for check in result.checks)


def test_dual_load_split_falls_back_to_sixty_forty(repo: Repo) -> None:
    dual = _case(
        mode="dual",
        payload=20.0,
        second={"brand": "徐工", "model": "QY70K-1"},
    )
    dual.pop("load")
    result = run_case(dual, repo)
    cap = result.aux["capability"]
    assert cap["split"]["basis"] == "ratio"
    assert cap["left_share"] == pytest.approx(0.6)


def test_explicit_left_share_still_wins(repo: Repo) -> None:
    dual = _case(mode="dual", payload=20.0, left_share=0.7,
                 second={"brand": "徐工", "model": "QY70K-1"})
    result = run_case(dual, repo)
    assert result.aux["capability"]["left_share"] == pytest.approx(0.7)


def test_elevation_draws_cg_and_sling_table(repo: Repo) -> None:
    result = run_case(_case(), repo)
    figure = elevation_figure(result)
    assert figure is not None
    texts = " ".join(item.content for item in figure.primitives if isinstance(item, Text))
    for expected in ("吊物与吊索", "重心G", "所需起升高度", "吊物 L×B×H", "索1 远前"):
        assert expected in texts, expected
    # 吊物按真实尺寸：h2 是真实高度、g 是真实长度
    assert "h2=2.50 m" in texts and "g=6.00 m" in texts
    assert f"{result.aux['load']['slings'][0]['force_t']*9.80665:.2f} kN" in texts
    assert figure.meta["load_bottom"] == pytest.approx(1.0)
    model = figure.meta["model"]
    assert model.cg[0] == pytest.approx(model.radius)
    assert model.load_center[0] == pytest.approx(model.radius - 0.4)


def test_load_figure_has_axes_and_cg(repo: Repo) -> None:
    result = run_case(_case(), repo)
    figures = {figure.title: figure for figure in figures_for(result)}
    load_figure = figures["吊物与重心三维示意"]
    hook = next(p for p in load_figure.primitives if isinstance(p, Circle) and p.layer == LAYER_RIGGING and p.r == 2.2)
    cg = next(p for p in load_figure.primitives if isinstance(p, Circle) and p.layer == LAYER_CENTER)
    assert hook.cx == pytest.approx(cg.cx)
    assert hook.cy > cg.cy
    texts = " ".join(item.content for item in load_figure.primitives
                     if isinstance(item, Text))
    for expected in ("x（长度，远离吊车）", "y（宽度 B=3.00 m）", "z（竖向）", "重心 G",
                     "L=6.00 m", "H=2.50 m", "吊钩"):
        assert expected in texts, expected
    for item in load_figure.primitives:
        box = item_bbox(item)
        if box is not None:
            assert box[0] >= -0.01 and box[1] >= -0.01
            assert box[2] <= load_figure.width + 0.01
            assert box[3] <= load_figure.height + 0.01


def test_report_has_load_and_cg_section(repo: Repo, tmp_path: Path) -> None:
    case = _case()
    result = run_case(case, repo)
    path = render_report(result, tmp_path / "book.docx", case_payload=case)
    document = Document(path)
    headings = [paragraph.text for paragraph in document.paragraphs
                if paragraph.style.name.startswith("Heading")]
    assert "3.1 吊物与重心" in headings
    assert sum("反查详细计算过程" in heading for heading in headings) == 1
    tables = [[[cell.text for cell in row.cells] for row in table.rows]
              for table in document.tables]
    joined = "\n".join(
        [paragraph.text for paragraph in document.paragraphs]
        + [cell for table in tables for row in table for cell in row]
    )
    assert "吊索" in joined and "重心相对形心" in joined
    assert any("与竖直夹角 (°)" in row for table in tables for row in table[:1])


def test_dual_report_shows_split(repo: Repo, tmp_path: Path) -> None:
    dual = _case(mode="dual", payload=20.0,
                 second={"brand": "徐工", "model": "QY70K-1"})
    dual["load"] = {"length_m": 8.0, "width_m": 3.0, "height_m": 2.0,
                    "cg": {"x": 1.2}, "sling_height_m": 3.0}
    result = run_case(dual, repo)
    path = render_report(result, tmp_path / "dual.docx", case_payload=dual)
    document = Document(path)
    headings = [paragraph.text for paragraph in document.paragraphs
                if paragraph.style.name.startswith("Heading")]
    assert "3.1.1 双机抬吊的负荷分配" in headings
    joined = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "按重心位置分配" in joined


@pytest.mark.parametrize("ex,ey", [(0,0),(.8,-.45),(-1.7,.79)])
def test_four_sling_bounds_are_attainable_in_equilibrium(ex,ey):
    shape = G.LoadShape(length=4, width=2, height=1, sling_height=3, cg_x=ex, cg_y=ey)
    report = G.sling_report(shape, 10)
    # From the two side moments, all solutions depend on the far-front share u.
    right,front = (1+ex/2)/2,(1+ey)/2
    ends = (max(0,right+front-1),min(right,front))
    tensions = []
    for u in ends:
        shares = (u,front-u,right-u,1-right-front+u)
        assert min(shares) >= -1e-12
        assert sum(s.x*q for s,q in zip(report.slings,shares)) == pytest.approx(ex)
        assert sum(s.y*q for s,q in zip(report.slings,shares)) == pytest.approx(ey)
        tensions.append([98.0665*q/math.cos(math.radians(s.angle_deg))
                         for s,q in zip(report.slings,shares)])
    for sling,limits in zip(report.slings,zip(*tensions)):
        assert sling.equilibrium_min_kn == pytest.approx(min(limits))
        assert sling.equilibrium_max_kn == pytest.approx(max(limits))
        assert min(limits) <= sling.force_t*9.80665 <= max(limits)
