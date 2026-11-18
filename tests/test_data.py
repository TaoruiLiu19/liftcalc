"""数据层测试：构建、校验、单调性拦截。"""

from __future__ import annotations

import shutil
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
