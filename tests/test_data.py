"""数据层测试：构建、校验、单调性拦截。"""

from __future__ import annotations

import csv
import shutil
import sqlite3
from pathlib import Path

from liftcalc.data.importer import build_db
from liftcalc.data.validate import validate_db

PACK = Path(__file__).resolve().parents[1] / "src" / "liftcalc" / "data" / "pack"


def test_build_and_validate_shipped_pack(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    stats = build_db(PACK, db, "2026.11")
    assert stats.steel_sections > 0
    assert stats.materials > 0
    assert db.exists()

    report = validate_db(db)
    assert report.ok, report.issues
    assert report.checked["steel_section"] == stats.steel_sections


NEW_MODELS = [
    "QAY300", "XCT130L8_1", "ZTC250A", "STC1000C7-8", "STC1300C7-8",
    "STC1300C8-8", "STC800C5-8", "STC500C5-8", "STC250C5-8",
    "STC400T5-6", "STC350C5-1",
]


def test_new_models_carry_spec_metadata(tmp_path: Path) -> None:
    """11 款新增机型的自重、支腿跨距和来源备注必须来自规格书。"""
    db = tmp_path / "meta.sqlite"
    build_db(PACK, db, "test")
    with sqlite3.connect(db) as conn:
        rows = {
            row[0]: row
            for row in conn.execute(
                "SELECT model, self_weight_t, outrigger_lx_m, outrigger_ly_m, "
                "max_outrigger_reaction_kN FROM crane_model"
            )
        }
    for model in NEW_MODELS:
        row = rows[model]
        assert row[1] > 0 and row[2] > 0 and row[3] > 0, f"{model} 缺自重/支腿跨距"
    assert rows["XCT130L8_1"][4] == 1068

    with (PACK / "crane" / "models.csv").open(encoding="utf-8-sig", newline="") as f:
        meta = {row["model"]: row for row in csv.DictReader(f)}
    for model in NEW_MODELS:
        assert meta[model]["metadata_note"], f"{model} 缺数据口径说明"


def test_counterweight_is_per_config(tmp_path: Path) -> None:
    """多配重机型逐 config 取配重，不能把某一档写成全机型统一值。"""
    db = tmp_path / "cw.sqlite"
    build_db(PACK, db, "test")
    with sqlite3.connect(db) as conn:
        def weights(model: str) -> set[float]:
            return {row[0] for row in conn.execute(
                "SELECT DISTINCT cfg.counterweight FROM crane_config cfg "
                "JOIN crane_model m ON m.id=cfg.model_id WHERE m.model=?", (model,)
            ) if row[0] is not None}
        assert weights("STC800C5-8") == {16.0, 18.0, 20.0}
        assert weights("STC1000C7-8") == {25.0, 36.0}
        assert 98.2 in weights("QAY300")


def test_monotonic_violation_is_caught(tmp_path: Path) -> None:
    """额定起重量随幅度回增必须报错。"""
    pack = tmp_path / "pack"
    shutil.copytree(PACK, pack)
    (pack / "crane_capacity.csv").write_text(
        "brand,model,tonnage_class,crane_type,name,boom_len,counterweight,radius,rated_load,source_ref\n"
        "DEMO,DEMO-100,100,crawler,主臂,50,,10,60,测试\n"
        "DEMO,DEMO-100,100,crawler,主臂,50,,12,70,测试\n",
        encoding="utf-8",
    )
    db = tmp_path / "bad.sqlite"
    build_db(pack, db, "test")
    report = validate_db(db)
    assert not report.ok
    assert any("单调" in issue or "回增" in issue for issue in report.issues)


def test_missing_source_ref_is_caught(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    shutil.copytree(PACK, pack)
    (pack / "steel_sections.csv").write_text(
        "family,designation,standard,h,b,tw,tf,r,A,Ix,Iy,Wx,Wy,rx,ry,J,source_ref\n"
        "H,NO-SOURCE,GB/T 11263-2017,200,200,8,12,13,,,,,,,,,\n",
        encoding="utf-8",
    )
    db = tmp_path / "nosrc.sqlite"
    try:
        build_db(pack, db, "test")
    except Exception as exc:
        assert "source_ref" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("导入器应拒绝缺少 source_ref 的数据")
