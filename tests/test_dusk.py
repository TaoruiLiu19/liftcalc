import base64
from pathlib import Path

import ezdxf
import pytest

from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.dusk import DesktopApi


def test_snapshot_can_be_replaced_without_reusing_the_old_drawing(tmp_path):
    db = tmp_path / "catalog.sqlite"
    build_db(Path(__file__).resolve().parents[1] / "src/liftcalc/data/pack", db, "test")
    api = DesktopApi(Repo(db))
    case = {"kind": "crane.capability", "payload": 10, "crane": {"model": "QY70K-1", "brand": "徐工"}}
    first = api.calculate(case)
    assert first["cap"]["status"] == "满足"
    assert first["svg"] and first["scale"]
    path = tmp_path / "snapshot.dxf"
    path.write_bytes(base64.b64decode(api.dxf(first["id"])))
    document = ezdxf.readfile(path)
    assert document.units == 4
    assert document.modelspace().query('LINE[layer=="RIGGING"]')
    second = api.calculate({**case, "target_radius": 10000})
    assert second["cap"]["status"] == "资料不足" and second["svg"] is None
    with pytest.raises(ValueError, match="结果已变更"):
        api.dxf(first["id"])
    with pytest.raises(ValueError, match="无可供核图"):
        api.dxf(second["id"])
