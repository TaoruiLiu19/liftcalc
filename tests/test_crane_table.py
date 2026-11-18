"""性能表录入模板与校验器测试（安全相关，必须拦得住错表）。"""

from __future__ import annotations

import csv
from pathlib import Path

from liftcalc.data.crane_table import (
    CAPACITY_COLUMNS,
    CapacityRow,
    load_capacity_csv,
    validate_capacity,
    write_template,
)


def _rows(*triples: tuple[float, float, float]) -> list[CapacityRow]:
    return [CapacityRow(boom_len=b, radius=r, rated_load=q) for b, r, q in triples]


def test_good_table_passes() -> None:
    rows = _rows(
        (11.6, 3.0, 70.0), (11.6, 4.0, 54.0), (11.6, 5.0, 47.0),
        (11.6, 6.0, 38.0), (11.6, 7.0, 30.0),
        (44.5, 3.0, 70.0), (44.5, 12.0, 9.0), (44.5, 14.0, 7.5),
        (44.5, 16.0, 6.5), (44.5, 18.0, 5.6),
    )
    report = validate_capacity("QY70K-1", rows, tonnage_class=70.0)
    assert report.ok, report.errors


def test_radius_must_increase() -> None:
    rows = _rows((11.6, 3.0, 70.0), (11.6, 4.0, 54.0), (11.6, 3.5, 50.0))
    report = validate_capacity("X", rows)
    assert not report.ok
    assert any("递增" in issue for issue in report.errors)


def test_rated_load_must_not_increase() -> None:
    rows = _rows((11.6, 3.0, 70.0), (11.6, 4.0, 54.0), (11.6, 5.0, 60.0))
    report = validate_capacity("X", rows)
    assert not report.ok
    assert any("回增" in issue for issue in report.errors)


def test_rated_load_over_tonnage_is_error() -> None:
    rows = _rows((11.6, 3.0, 80.0), (11.6, 4.0, 54.0))
    report = validate_capacity("X", rows, tonnage_class=70.0)
    assert not report.ok
    assert any("超过吨级" in issue for issue in report.errors)


def test_duplicate_row_is_error() -> None:
    rows = _rows((11.6, 3.0, 70.0), (11.6, 3.0, 68.0))
    report = validate_capacity("X", rows)
    assert not report.ok
    assert any("重复" in issue for issue in report.errors)


def test_exact_model_metadata_is_read() -> None:
    rows = _rows((11.6, 3.0, 70.0), (11.6, 4.0, 54.0))
    report = validate_capacity("X", rows, tonnage_class=70.0)
    assert report.rows == 2
    assert report.booms == 1


def test_template_roundtrip(tmp_path: Path) -> None:
    path = write_template(
        tmp_path / "T.capacity.csv",
        model="T",
        booms=[11.6, 44.5],
        radii=[3.0, 4.0, 5.0],
    )
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and list(rows[0].keys()) == CAPACITY_COLUMNS
    assert len(rows) == 6

    # 填入数值后应能读回
    for index, row in enumerate(rows):
        row["rated_load_t"] = str(70 - index)
        row["source_page"] = "1"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CAPACITY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    model, loaded = load_capacity_csv(path)
    assert model == "T"
    assert len(loaded) == 6
    assert loaded[0].rated_load == 70

def test_end_angle_mismatch_is_error() -> None:
    """首/末行仰角与表头最大/最小仰角不一致 → 说明漏录或多录了行。"""
    rows = [
        CapacityRow(11.6, 3.0, 70.0, boom_angle=71.5, boom_max_angle=71.5, boom_min_angle=29.8),
        CapacityRow(11.6, 4.0, 54.0, boom_angle=66.0, boom_max_angle=71.5, boom_min_angle=29.8),
        CapacityRow(11.6, 5.0, 47.0, boom_angle=60.3, boom_max_angle=71.5, boom_min_angle=29.8),
    ]
    report = validate_capacity("X", rows)
    assert not report.ok
    assert any("末行仰角" in issue for issue in report.errors)


def test_end_angle_match_passes() -> None:
    rows = [
        CapacityRow(11.6, 3.0, 70.0, boom_angle=71.5, boom_max_angle=71.5, boom_min_angle=29.8),
        CapacityRow(11.6, 4.0, 54.0, boom_angle=66.0, boom_max_angle=71.5, boom_min_angle=29.8),
        CapacityRow(11.6, 5.0, 47.0, boom_angle=29.8, boom_max_angle=71.5, boom_min_angle=29.8),
    ]
    report = validate_capacity("X", rows)
    assert report.ok, report.errors