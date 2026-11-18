"""版本与输入指纹（设计 §5.5）。

`input_digest` 让每份计算书都能反查到唯一输入。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from liftcalc import __version__


def engine_version() -> str:
    return __version__


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def data_version_of(db_path: Path) -> str:
    if not db_path.exists():
        return ""
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'data_version'").fetchone()
    return str(row[0]) if row else ""
