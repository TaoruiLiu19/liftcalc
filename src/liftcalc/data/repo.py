"""只读数据仓储（设计 §3.2：内核不认识数据库）。"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from liftcalc.core.errors import DataError

Row = dict[str, Any]

DEFAULT_DB = Path("data") / "liftcalc.sqlite"


@dataclass(frozen=True)
class Repo:
    db_path: Path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if not self.db_path.exists():
            raise DataError(f"数据库不存在：{self.db_path}（先运行 liftcalc data build）")
        conn = sqlite3.connect(f"{self.db_path.resolve().as_uri()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[Row]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def sections(self) -> list[Row]:
        return self._rows("SELECT * FROM steel_section ORDER BY family, designation")

    def materials(self) -> list[Row]:
        return self._rows("SELECT * FROM material ORDER BY grade, thickness_max")

    def material(self, grade: str) -> Row:
        rows = self._rows("SELECT * FROM material WHERE grade = ? ORDER BY thickness_max LIMIT 1", (grade,))
        if not rows:
            raise DataError(f"材质库中没有牌号 {grade}")
        return rows[0]

    def meta(self) -> dict[str, str]:
        return {row["key"]: row["value"] for row in self._rows("SELECT key, value FROM meta")}

    def crane_model(self, brand: str, model: str) -> Row:
        rows = self._rows("SELECT * FROM crane_model WHERE brand = ? AND model = ?", (brand, model))
        if not rows:
            raise DataError(f"机型库中没有 {brand} {model}")
        return rows[0]

    def workbench_models(self) -> list[Row]:
        rows = self._rows("""
            SELECT m.brand, m.model, m.tonnage_class AS tonnage_class_t, m.hook_main_t,
                   cfg.name AS config, cfg.boom_len, MAX(c.rated_load) AS max_rated_t
              FROM crane_model m JOIN crane_config cfg ON cfg.model_id=m.id
              JOIN crane_capacity c ON c.config_id=cfg.id
             GROUP BY m.id, cfg.name, cfg.boom_len
             ORDER BY m.brand, m.model, cfg.name, cfg.boom_len
        """)
        hooks = {}
        for hook in self.main_hooks():
            hooks.setdefault((hook["brand"], hook["model"]), []).append(hook)
        configs: dict[tuple[str, str, str], Row] = {}
        for row in rows:
            brand, model, name = row["brand"], row["model"], row["config"]
            key = brand, model, name
            if key not in configs:
                configs[key] = {
                    "brand": brand, "model": model, "config": name,
                    "tonnage_class_t": row["tonnage_class_t"], "hook_main_t": row["hook_main_t"],
                    "main_hooks": hooks.get((brand, model), []), "booms": [], "boom_ratings": [],
                }
            config = configs[key]
            config["booms"].append(row["boom_len"])
            config["boom_ratings"].append({"boom_m": row["boom_len"], "max_rated_t": row["max_rated_t"]})
        return list(configs.values())

    def main_hooks(self, brand: str | None = None, model: str | None = None) -> list[Row]:
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='crane_main_hook'").fetchone():
                return []  # Catalogs built before individual main hooks were recorded.
            query = """SELECT m.brand, m.model, h.mass_t, h.rated_t, h.is_default,
                              m.source_doc || '#page=' || h.source_page AS source_ref
                         FROM crane_main_hook h JOIN crane_model m ON m.id=h.model_id"""
            clauses = []
            params = []
            if brand is not None:
                clauses.append("m.brand=?")
                params.append(brand)
            if model is not None:
                clauses.append("m.model=?")
                params.append(model)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            return [dict(row) for row in conn.execute(query + " ORDER BY h.is_default DESC, h.rated_t DESC, h.mass_t DESC", params)]

    def model_capacity(self, brand: str, model: str) -> list[Row]:
        sql = """
            SELECT cfg.boom_len AS boom_len, cfg.name AS config_name, c.radius AS radius, c.rated_load AS rated_load,
                   c.boom_angle_deg AS boom_angle, c.lift_height_m AS lift_height, c.source_ref
              FROM crane_capacity c
              JOIN crane_config cfg ON cfg.id = c.config_id
              JOIN crane_model m ON m.id = cfg.model_id
             WHERE m.brand = ? AND m.model = ?
             ORDER BY cfg.boom_len, c.radius
        """
        return self._rows(sql, (brand, model))
    def capacity(self, brand: str, model: str, config: str, boom_len: float) -> list[tuple[float, float]]:
        sql = """
            SELECT c.radius, c.rated_load
              FROM crane_capacity c
              JOIN crane_config cfg ON cfg.id = c.config_id
              JOIN crane_model m ON m.id = cfg.model_id
             WHERE m.brand = ? AND m.model = ? AND cfg.name = ? AND cfg.boom_len = ?
             ORDER BY c.radius
        """
        rows = self._rows(sql, (brand, model, config, boom_len))
        return [(float(row["radius"]), float(row["rated_load"])) for row in rows]
