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
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
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

    def model_capacity(self, brand: str, model: str) -> list[Row]:
        sql = """
            SELECT cfg.boom_len AS boom_len, cfg.name AS config_name, c.radius AS radius, c.rated_load AS rated_load,
                   c.boom_angle_deg AS boom_angle, c.lift_height_m AS lift_height
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
