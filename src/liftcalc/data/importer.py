"""CSV → SQLite 导入器（设计 §6.3）。

规则：每条数据必须带 source_ref；空字符串一律转为 NULL。
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from liftcalc.core.errors import DataError
from liftcalc.data import crane_table

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

STEEL_COLUMNS = [
    "family", "designation", "standard", "h", "b", "tw", "tf", "r",
    "A", "Ix", "Iy", "Wx", "Wy", "rx", "ry", "J", "source_ref",
]
MATERIAL_COLUMNS = [
    "grade", "standard", "fy", "fu", "E", "G", "rho", "thickness_max", "source_ref",
]
CAPACITY_COLUMNS = [
    "brand", "model", "tonnage_class", "crane_type", "name", "boom_len",
    "counterweight", "radius", "rated_load", "source_ref",
]

_NUMERIC = {
    "h", "b", "tw", "tf", "r", "A", "Ix", "Iy", "Wx", "Wy", "rx", "ry", "J",
    "fy", "fu", "E", "G", "rho", "thickness_max",
    "tonnage_class", "boom_len", "counterweight", "radius", "rated_load",
}


@dataclass
class BuildStats:
    steel_sections: int = 0
    materials: int = 0
    crane_models: int = 0
    crane_configs: int = 0
    crane_capacities: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "steel_sections": self.steel_sections,
            "materials": self.materials,
            "crane_models": self.crane_models,
            "crane_configs": self.crane_configs,
            "crane_capacities": self.crane_capacities,
        }


def _convert(row: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        text = (value or "").strip()
        if text == "":
            out[key] = None
        elif key in _NUMERIC:
            try:
                out[key] = float(text)
            except ValueError as exc:
                raise DataError(f"字段 {key} 不是数字：{text!r}") from exc
        else:
            out[key] = text
    return out


def _read_csv(path: Path, expected: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        missing = [name for name in expected if name not in reader.fieldnames]
        if missing:
            raise DataError(f"{path.name} 缺少列：{missing}")
        return [_convert(row) for row in reader]


def _num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def build_db(pack_dir: Path, out_path: Path, data_version: str) -> BuildStats:
    stats = BuildStats()
    if out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(out_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        for row in _read_csv(pack_dir / "steel_sections.csv", STEEL_COLUMNS):
            if not row.get("source_ref"):
                raise DataError(f"型钢 {row.get('designation')} 缺少 source_ref")
            placeholders = ", ".join("?" for _ in STEEL_COLUMNS)
            conn.execute(
                f"INSERT INTO steel_section ({', '.join(STEEL_COLUMNS)}) VALUES ({placeholders})",
                [row.get(name) for name in STEEL_COLUMNS],
            )
            stats.steel_sections += 1

        for row in _read_csv(pack_dir / "materials.csv", MATERIAL_COLUMNS):
            if not row.get("source_ref"):
                raise DataError(f"材质 {row.get('grade')} 缺少 source_ref")
            placeholders = ", ".join("?" for _ in MATERIAL_COLUMNS)
            conn.execute(
                f"INSERT INTO material ({', '.join(MATERIAL_COLUMNS)}) VALUES ({placeholders})",
                [row.get(name) for name in MATERIAL_COLUMNS],
            )
            stats.materials += 1

        # 原厂性能表：一个机型一个 CSV，逐格转录后入库
        crane_dir = pack_dir / "crane"
        if crane_dir.exists():
            meta = crane_table.load_model_meta(crane_dir / "models.csv")
            for path in sorted(crane_dir.glob("*.capacity.csv")):
                model_name, capacity_rows = crane_table.load_capacity_csv(path)
                meta_row = meta.get(model_name, {})
                tonnage = _num(meta_row.get("tonnage_class_t"))
                report = crane_table.validate_capacity(
                    model_name, capacity_rows, tonnage_class=tonnage
                )
                if not report.ok:
                    raise DataError(
                        f"性能表 {model_name} 校验未通过：" + "；".join(report.errors[:5])
                    )
                if tonnage is None:
                    tonnage = max(row.rated_load for row in capacity_rows)
                brand = (meta_row.get("brand") or "未知").strip() or "未知"
                crane_type = (meta_row.get("crane_type") or "truck").strip() or "truck"
                cursor = conn.execute(
                    "INSERT INTO crane_model (brand, model, tonnage_class, crane_type, counterweight_t,"
                    " hook_main_t, hook_aux_t, max_outrigger_reaction_kN, self_weight_t,"
                    " outrigger_lx_m, outrigger_ly_m, source_doc, source_page)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        brand, model_name, tonnage, crane_type,
                        _num(meta_row.get("counterweight_t")),
                        _num(meta_row.get("hook_main_t")),
                        _num(meta_row.get("hook_aux_t")),
                        _num(meta_row.get("max_outrigger_reaction_kN")),
                        _num(meta_row.get("self_weight_t")),
                        _num(meta_row.get("outrigger_lx_m")),
                        _num(meta_row.get("outrigger_ly_m")),
                        (meta_row.get("source_doc") or path.name),
                        (meta_row.get("source_page") or ""),
                    ),
                )
                model_id = int(cursor.lastrowid or 0)
                stats.crane_models += 1
                by_boom: dict[tuple[str, float], list[crane_table.CapacityRow]] = {}
                for row in capacity_rows:
                    by_boom.setdefault((row.config, row.boom_len), []).append(row)
                for config_label, boom_len in sorted(by_boom, key=lambda key: (key[0], key[1])):
                    cursor = conn.execute(
                        "INSERT INTO crane_config (model_id, name, boom_len, counterweight) VALUES (?,?,?,?)",
                        (
                            model_id,
                            (f"{config_label}·主臂{boom_len:g}m" if config_label else f"主臂{boom_len:g}m"),
                            boom_len,
                            _num(meta_row.get("counterweight_t")),
                        ),
                    )
                    config_id = int(cursor.lastrowid or 0)
                    stats.crane_configs += 1
                    for row in sorted(by_boom[(config_label, boom_len)], key=lambda item: item.radius):
                        source_ref = (
                            f"{path.name} 第{row.source_page}页" if row.source_page else path.name
                        )
                        source_doc = meta_row.get("source_doc") or ""
                        if source_doc.startswith("https://") and row.source_page.isdecimal():
                            source_ref = f"{source_doc}#page={row.source_page}"
                        conn.execute(
                            "INSERT INTO crane_capacity (config_id, radius, rated_load, boom_angle_deg,"
                            " lift_height_m, parts_of_line, source_ref) VALUES (?,?,?,?,?,?,?)",
                            (
                                config_id, row.radius, row.rated_load, row.boom_angle,
                                row.lift_height, row.parts_of_line, source_ref,
                            ),
                        )
                        stats.crane_capacities += 1

        model_ids: dict[tuple[str, str], int] = {}
        config_ids: dict[tuple[str, str, str, float], int] = {}
        for row in _read_csv(pack_dir / "crane_capacity.csv", CAPACITY_COLUMNS):
            brand, model = str(row["brand"]), str(row["model"])
            key = (brand, model)
            if key not in model_ids:
                cursor = conn.execute(
                    "INSERT INTO crane_model (brand, model, tonnage_class, crane_type, source_doc) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (brand, model, row["tonnage_class"], row["crane_type"], row.get("source_ref") or "未注明"),
                )
                model_ids[key] = int(cursor.lastrowid or 0)
                stats.crane_models += 1
            config_key = (brand, model, str(row["name"]), float(row["boom_len"]))
            if config_key not in config_ids:
                cursor = conn.execute(
                    "INSERT INTO crane_config (model_id, name, boom_len, counterweight) VALUES (?, ?, ?, ?)",
                    (model_ids[key], row["name"], row["boom_len"], row.get("counterweight")),
                )
                config_ids[config_key] = int(cursor.lastrowid or 0)
                stats.crane_configs += 1
            conn.execute(
                "INSERT INTO crane_capacity (config_id, radius, rated_load, source_ref) VALUES (?, ?, ?, ?)",
                (config_ids[config_key], row["radius"], row["rated_load"], row.get("source_ref") or "未注明"),
            )
            stats.crane_capacities += 1

        conn.execute("INSERT INTO meta (key, value) VALUES ('data_version', ?)", (data_version,))
        conn.execute("INSERT INTO meta (key, value) VALUES ('built_from', ?)", (str(pack_dir),))
        conn.commit()
    finally:
        conn.close()
    return stats
