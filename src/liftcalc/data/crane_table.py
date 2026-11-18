"""吊车性能表的录入模板与校验。

数据来源是原厂性能表（扫描件），只能人工转录。因此校验必须严格：
一张表里任何一个数字错了，负荷率就会错，而负荷率错就是安全问题。

校验分两级：
- **错误**：结构性矛盾（幅度不递增、额定值回增、重复行、超吨位），拒绝入库
- **警告**：可疑但不一定错（点数太少、跨臂长交叉、仰角不单调），需人工确认
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CAPACITY_COLUMNS = [
    "boom_len_m",
    "radius_m",
    "rated_load_t",
    "boom_angle_deg",
    "boom_max_angle_deg",
    "boom_min_angle_deg",
    "lift_height_m",
    "parts_of_line",
    "source_page",
    "note",
    "config",
]
MODEL_COLUMNS = [
    "model",
    "brand",
    "tonnage_class_t",
    "crane_type",
    "counterweight_t",
    "hook_main_t",
    "hook_aux_t",
    "max_outrigger_reaction_kN",
    "self_weight_t",
    "source_doc",
    "source_page",
]

TOL = 1e-9


@dataclass
class CapacityRow:
    boom_len: float
    radius: float
    rated_load: float
    boom_angle: float | None = None
    boom_max_angle: float | None = None
    boom_min_angle: float | None = None
    lift_height: float | None = None
    parts_of_line: float | None = None
    source_page: str = ""
    note: str = ""
    config: str = ""


@dataclass
class TableReport:
    model: str
    rows: int = 0
    booms: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "ok": self.ok,
            "rows": self.rows,
            "booms": self.booms,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _f(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    return float(text)


def load_capacity_csv(path: Path) -> tuple[str, list[CapacityRow]]:
    model = path.name.split(".")[0]
    rows: list[CapacityRow] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return model, rows
        missing = [name for name in ("boom_len_m", "radius_m", "rated_load_t") if name not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path.name} 缺少列：{missing}")
        for raw in reader:
            boom = _f(raw.get("boom_len_m"))
            radius = _f(raw.get("radius_m"))
            rated = _f(raw.get("rated_load_t"))
            if boom is None and radius is None and rated is None:
                continue  # 空行
            if boom is None or radius is None or rated is None:
                raise ValueError(f"{path.name} 存在不完整的行：{raw}")
            rows.append(
                CapacityRow(
                    boom_len=boom,
                    radius=radius,
                    rated_load=rated,
                    boom_angle=_f(raw.get("boom_angle_deg")),
                    boom_max_angle=_f(raw.get("boom_max_angle_deg")),
                    boom_min_angle=_f(raw.get("boom_min_angle_deg")),
                    lift_height=_f(raw.get("lift_height_m")),
                    parts_of_line=_f(raw.get("parts_of_line")),
                    source_page=(raw.get("source_page") or "").strip(),
                    config=(raw.get("config") or "").strip(),
                    note=(raw.get("note") or "").strip(),
                )
            )
    return model, rows


def validate_capacity(
    model: str, rows: list[CapacityRow], *, tonnage_class: float | None = None
) -> TableReport:
    report = TableReport(model=model, rows=len(rows))

    if not rows:
        report.errors.append("性能表为空")
        return report

    booms: dict[tuple[str, float], list[CapacityRow]] = {}
    for row in rows:
        if row.boom_len <= 0 or row.radius <= 0:
            report.errors.append(f"臂长或幅度不为正：{row.boom_len},{row.radius}")
            continue
        if row.rated_load <= 0:
            report.errors.append(f"{row.boom_len:g} m / {row.radius:g} m 的额定起重量不为正")
            continue
        booms.setdefault((row.config, row.boom_len), []).append(row)

    report.booms = len(booms)
    seen: set[tuple[str, float, float]] = set()

    for config_label, boom_len in sorted(booms):
        series = booms[(config_label, boom_len)]  # 保持文件顺序：才能发现"录乱了"
        label = f"{config_label}·{boom_len:g} m 臂" if config_label else f"{boom_len:g} m 臂"

        for row in series:
            key = (row.config, round(row.boom_len, 6), round(row.radius, 6))
            if key in seen:
                report.errors.append(f"{label}：幅度 {row.radius:g} m 重复出现")
            seen.add(key)

        if len(series) < 5:
            report.warnings.append(f"{label}：只有 {len(series)} 个格点，过少")

        previous_radius = -1.0
        previous_load = float("inf")
        previous_angle = float("inf")
        previous_height = float("inf")
        for row in series:
            if row.radius <= previous_radius + TOL:
                report.errors.append(f"{label}：幅度未严格递增（{row.radius:g}）")
            if row.rated_load > previous_load + TOL:
                report.errors.append(
                    f"{label}：幅度 {row.radius:g} m 处额定值回增（{row.rated_load:g} > {previous_load:g}）"
                )
            if row.boom_angle is not None and row.boom_angle > previous_angle + 0.6:
                report.warnings.append(
                    f"{label}：幅度 {row.radius:g} m 处仰角不降反升（{row.boom_angle:g}°）"
                )
            if row.lift_height is not None and row.lift_height > previous_height + 0.6:
                report.warnings.append(
                    f"{label}：幅度 {row.radius:g} m 处起升高度不降反升（{row.lift_height:g} m）"
                )
            if tonnage_class is not None and row.rated_load > tonnage_class * 1.02:
                report.errors.append(
                    f"{label}：幅度 {row.radius:g} m 处额定值 {row.rated_load:g} t 超过吨级 {tonnage_class:g} t"
                )
            if previous_radius > 0 and row.radius - previous_radius > 2.0 + TOL:
                report.warnings.append(
                    f"{label}：幅度由 {previous_radius:g} 跳到 {row.radius:g} m，间隔偏大"
                )
            if row.boom_angle is not None:
                previous_angle = row.boom_angle
            if row.lift_height is not None:
                previous_height = row.lift_height
            previous_radius, previous_load = row.radius, row.rated_load

        smallest = min(row.radius for row in series)
        if smallest > 4.0:
            report.warnings.append(f"{label}：最小幅度为 {smallest:g} m，请确认是否漏录小幅度")

        if not all(row.source_page for row in series):
            report.warnings.append(f"{label}：存在未填页码的行")

    # 首/末行仰角必须与表头声明的最大/最小仰角一致（抄错行最有效的拦截）
    for config_label, boom_len in sorted(booms):
        series = booms[(config_label, boom_len)]
        declared_max = next((row.boom_max_angle for row in series if row.boom_max_angle is not None), None)
        declared_min = next((row.boom_min_angle for row in series if row.boom_min_angle is not None), None)
        if (declared_max is not None and series[0].boom_angle is not None
                and abs(series[0].boom_angle - declared_max) > 0.05):
            report.errors.append(
                    f"{boom_len:g} m 臂：首行仰角 {series[0].boom_angle:g}° 与表头最大仰角 "
                    f"{declared_max:g}° 不一致（疑似漏录/多录行）"
                )
        if (declared_min is not None and series[-1].boom_angle is not None
                and abs(series[-1].boom_angle - declared_min) > 0.05):
            report.errors.append(
                    f"{boom_len:g} m 臂：末行仰角 {series[-1].boom_angle:g}° 与表头最小仰角 "
                    f"{declared_min:g}° 不一致（疑似漏录/多录行）"
                )
    return report


def load_model_meta(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return {(row.get("model") or "").strip(): row for row in reader if row.get("model")}


def write_template(path: Path, *, model: str, booms: list[float], radii: list[float]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CAPACITY_COLUMNS)
        for boom in booms:
            for radius in radii:
                writer.writerow([f"{boom:g}", f"{radius:g}", "", "", "", "", "", "", "", "", ""])
    return path


def rows_to_capacity(rows: list[CapacityRow]) -> list[dict[str, Any]]:
    """转成数据库写入用的字典（单位：t、m）。"""
    return [
        {
            "boom_len": row.boom_len,
            "radius": row.radius,
            "rated_load": row.rated_load,
            "boom_angle": row.boom_angle,
            "lift_height": row.lift_height,
            "parts_of_line": row.parts_of_line,
            "source_page": row.source_page,
            "note": row.note,
        }
        for row in rows
    ]
