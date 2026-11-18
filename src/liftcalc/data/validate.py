"""数据校验器（设计 §6.2）。

校验不是可选项：性能表录错一格就是工程事故。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationReport:
    checked: dict[str, int] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "checked": self.checked, "issues": self.issues}


def validate_db(db_path: Path) -> ValidationReport:
    report = ValidationReport()
    if not db_path.exists():
        report.issues.append(f"数据库不存在：{db_path}")
        return report

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        sections = conn.execute("SELECT * FROM steel_section").fetchall()
        report.checked["steel_section"] = len(sections)
        for row in sections:
            label = f"{row['family']}/{row['designation']}"
            if not row["source_ref"]:
                report.issues.append(f"型钢 {label} 缺少 source_ref")
            if row["h"] is None or float(row["h"]) <= 0:
                report.issues.append(f"型钢 {label} 的 h 必须为正")
            family = str(row["family"])
            if family != "BAR" and (row["b"] is None or float(row["b"]) <= 0):
                report.issues.append(f"型钢 {label} 的 b 必须为正")
            if family in {"H", "I", "C", "T", "L"} and (row["tw"] is None or float(row["tw"]) <= 0):
                report.issues.append(f"型钢 {label} 缺少有效厚度 tw")

        materials = conn.execute("SELECT * FROM material").fetchall()
        report.checked["material"] = len(materials)
        for row in materials:
            label = f"{row['grade']}"
            if not row["source_ref"]:
                report.issues.append(f"材质 {label} 缺少 source_ref")
            if row["fy"] is None or float(row["fy"]) <= 0:
                report.issues.append(f"材质 {label} 的 fy 必须为正")
            if row["fu"] is not None and row["fy"] is not None and float(row["fu"]) < float(row["fy"]):
                report.issues.append(f"材质 {label} 的 fu 小于 fy")

        models = conn.execute("SELECT * FROM crane_model").fetchall()
        report.checked["crane_model"] = len(models)
        for row in models:
            if not row["source_doc"]:
                report.issues.append(f"机型 {row['brand']}/{row['model']} 缺少 source_doc")

        configs = conn.execute("SELECT * FROM crane_config").fetchall()
        report.checked["crane_config"] = len(configs)
        capacity_total = 0
        for config in configs:
            points = conn.execute(
                "SELECT radius, rated_load FROM crane_capacity WHERE config_id = ? ORDER BY radius",
                (config["id"],),
            ).fetchall()
            capacity_total += len(points)
            label = f"config#{config['id']}({config['name']} {config['boom_len']}m)"
            if len(points) < 2:
                report.issues.append(f"性能表 {label} 少于 2 个格点，无法插值")
                continue
            previous_radius = -1.0
            previous_load = float("inf")
            for point in points:
                radius = float(point["radius"])
                load = float(point["rated_load"])
                if radius <= previous_radius:
                    report.issues.append(f"性能表 {label} 幅度非严格递增（{radius}）")
                if load <= 0:
                    report.issues.append(f"性能表 {label} 在 {radius}m 处额定起重量不为正")
                if load > previous_load + 1e-9:
                    report.issues.append(f"性能表 {label} 在 {radius}m 处额定起重量回增（违反单调性）")
                previous_radius, previous_load = radius, load
        report.checked["crane_capacity"] = capacity_total
    finally:
        conn.close()
    return report
