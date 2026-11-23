import json
from pathlib import Path

import ezdxf
import pytest

from liftcalc.crane.transfer import Transfer, analyze, clearance, segment_gap
from liftcalc.data.repo import Repo
from liftcalc.dusk import DesktopApi

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data():
    return json.loads((ROOT/"cases/rail-transfer-demo.json").read_text(encoding="utf-8"))


def test_split_and_transverse_equilibrium(data):
    case = Transfer.model_validate(data["transfer"])
    assert case.shares() == pytest.approx((.4,.6))
    case.cg = (1,.2,0)
    with pytest.raises(ValueError,match="偏离"):
        case.shares()
    case.cg = (5,0,0)
    with pytest.raises(ValueError,match="之间"):
        case.shares()


def test_mid_transfer_collision_and_exports(data, tmp_path):
    api = DesktopApi(Repo(ROOT/"data/liftcalc.sqlite"))
    case = Transfer.model_validate(data["transfer"])
    assert all(clearance(case,case.pose(t),case.obstacles[0]) > 0 for t in (0,1))
    result = api.calculate(data)
    segments = result["segments"]
    assert any("障碍1禁入区相交" in s["unsafe"] for s in segments)
    assert any("A全段可用钩高待核" in s["unknown"] for s in segments)
    assert segments[0]["start"] == 0 and segments[-1]["end"] == 1
    assert all(a["end"] == b["start"] for a,b in zip(segments,segments[1:]))
    for drawing in result["drawings"]:
        payload, name = api.render(drawing["id"], "dxf")
        path = tmp_path/name
        path.write_bytes(payload)
        doc = ezdxf.readfile(path)
        assert doc.header["$INSUNITS"] == 4 and len(doc.modelspace().query("TEXT")) >= 6


def test_no_chart_cannot_pass_and_hook_overload_is_visible(data):
    case = Transfer.model_validate(data["transfer"])
    case.cranes[0].hook_rating = 1
    case.cranes[1].boom = 123
    result = analyze(case, Repo(ROOT/"data/liftcalc.sqlite"))
    assert all("A钩载超限" in s["unsafe"] and "B幅度无表档" in s["unknown"]
               for s in result["segments"])


def test_projected_boom_gap():
    assert segment_gap((0,0),(2,2),(0,2),(2,0)) == 0
    assert segment_gap((0,0),(1,0),(2,0),(4,0)) == 1
