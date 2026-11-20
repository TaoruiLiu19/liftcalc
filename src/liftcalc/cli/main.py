"""命令行入口（设计 §14）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from liftcalc import __version__
from liftcalc.core.errors import LiftcalcError
from liftcalc.core.result import ComputationResult, Verdict
from liftcalc.data import crane_table
from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.data.validate import validate_db
from liftcalc.drawing.dxf import to_dxf
from liftcalc.drawing.figures import figures_for
from liftcalc.drawing.svg import to_svg
from liftcalc.report.render import render_report
from liftcalc.services.calc import parse_case, run_case
from liftcalc.services.cases import CASE_MODELS
from liftcalc.services.compare import compare

app = typer.Typer(add_completion=False, help="本地离线吊装计算（自用学习）")
data_app = typer.Typer(help="数据打包与校验")
app.add_typer(data_app, name="data")

EXIT_CODES = {"2": 2, "3": 3, "4": 4, "5": 5}


def _fail(exc: LiftcalcError) -> None:
    typer.echo(json.dumps(exc.to_dict(), ensure_ascii=False), err=True)
    prefix = exc.code.split("-")[-1][0]
    raise typer.Exit(EXIT_CODES.get(prefix, 5))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_result(result: ComputationResult, out: Path | None) -> None:
    payload = result.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out is None:
        typer.echo(text)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.echo(f"已写入 {out}")
    if result.verdict is Verdict.FAIL:
        raise typer.Exit(1)
    if result.kind == "crane.capability" and result.verdict is Verdict.NA:
        typer.echo(f"资料不足：{result.aux['capability']['explanation']}", err=True)
        raise typer.Exit(6)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"liftcalc {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True),
) -> None:
    """liftcalc —— 本地离线吊装计算后端。"""


@app.command("calc")
def calc(
    case_path: Path = typer.Option(..., "--in", "-i", help="case.json 路径"),
    out: Path | None = typer.Option(None, "--out", "-o", help="result.json 输出路径"),
    db: Path | None = typer.Option(None, "--db", help="数据仓库路径（steel/材质需要）"),
) -> None:
    """执行一次计算。"""
    try:
        payload = _load_json(case_path)
        repo = Repo(db) if db is not None else None
        result = run_case(payload, repo)
    except LiftcalcError as exc:
        _fail(exc)
        return
    _emit_result(result, out)


@app.command("report")
def report(
    result_path: Path = typer.Option(..., "--in", "-i", help="result.json 路径"),
    out: Path = typer.Option(..., "--out", "-o", help="docx 输出路径"),
    case_path: Path | None = typer.Option(None, "--case", help="case.json（用于附录快照）"),
    title: str = typer.Option("吊装计算书", "--title", help="计算书标题"),
) -> None:
    """由 result.json 生成计算书。"""
    result = ComputationResult.model_validate(_load_json(result_path))
    snapshot = _load_json(case_path) if case_path is not None else None
    path = render_report(result, out, title=title, case_payload=snapshot)
    typer.echo(f"已写入 {path}")


@app.command("draw")
def draw(
    result_path: Path = typer.Option(..., "--in", "-i", help="result.json 路径"),
    out: Path = typer.Option(..., "--out", "-o", help="输出文件路径"),
    fmt: str = typer.Option("svg", "--format", help="svg 或 dxf"),
) -> None:
    """由 result.json 生成简图。"""
    result = ComputationResult.model_validate(_load_json(result_path))
    fmt = fmt.lower()
    if fmt not in {"svg", "dxf"}:
        typer.echo(f"不支持的格式：{fmt}", err=True)
        raise typer.Exit(2)
    # DXF 不支持位图块，车身改画矢量简图；SVG 贴原版车身素材
    figures = figures_for(result)
    if not figures:
        typer.echo("该结果没有可用图形", err=True)
        raise typer.Exit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    for index, figure in enumerate(figures, start=1):
        target = out if len(figures) == 1 else out.with_name(f"{out.stem}-{index}{out.suffix}")
        if fmt == "svg":
            target.write_text(to_svg(figure), encoding="utf-8")
        else:
            to_dxf(figure, target)
        typer.echo(f"已写入 {target}（{figure.title}）")


@data_app.command("build")
def data_build(
    pack: Path = typer.Option(Path("src/liftcalc/data/pack"), "--pack", help="数据包目录"),
    out: Path = typer.Option(Path("data/liftcalc.sqlite"), "--out", help="输出数据库"),
    data_version: str = typer.Option("2026.11", "--data-version", help="数据版本戳"),
) -> None:
    """从 CSV/YAML 数据包构建 SQLite。"""
    try:
        stats = build_db(pack, out, data_version)
    except LiftcalcError as exc:
        _fail(exc)
        return
    typer.echo(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))


@data_app.command("validate")
def data_validate(
    db: Path = typer.Option(Path("data/liftcalc.sqlite"), "--db", help="数据库路径"),
) -> None:
    """校验数据完整性与单调性。"""
    report_obj = validate_db(db)
    typer.echo(json.dumps(report_obj.as_dict(), ensure_ascii=False, indent=2))
    if not report_obj.ok:
        raise typer.Exit(3)


@data_app.command("crane-template")
def crane_template(
    model: str = typer.Option(..., "--model", help="机型，如 QY70K-1"),
    booms: str = typer.Option(..., "--booms", help="臂长列表，逗号分隔"),
    radii: str = typer.Option(..., "--radii", help="幅度列表，逗号分隔"),
    out: Path = typer.Option(..., "--out", help="输出目录"),
) -> None:
    """生成性能表录入模板（空格点，逐格填）。"""
    boom_values = [float(item) for item in booms.split(",") if item.strip()]
    radius_values = [float(item) for item in radii.split(",") if item.strip()]
    path = crane_table.write_template(
        out / f"{model}.capacity.csv", model=model, booms=boom_values, radii=radius_values
    )
    typer.echo(f"已写入 {path}（{len(boom_values) * len(radius_values)} 行待填）")


@data_app.command("crane-validate")
def crane_validate(
    path: Path = typer.Option(..., "--path", help="性能表 CSV"),
    tonnage: float = typer.Option(0.0, "--tonnage", help="吨级（用于上限校验）"),
) -> None:
    """校验性能表：幅度递增、额定值不增、不超吨级。"""
    try:
        model, rows = crane_table.load_capacity_csv(path)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    report = crane_table.validate_capacity(model, rows, tonnage_class=tonnage or None)
    typer.echo(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    if not report.ok:
        raise typer.Exit(3)


@app.command("capability")
def capability_cmd(
    model: str = typer.Option(..., "--model", help="机型，如 QY70K-1"),
    payload: float = typer.Option(..., "--payload", help="吊件重量 t"),
    hook: float = typer.Option(0.0, "--hook", help="吊钩重量 t"),
    rigging: float = typer.Option(0.0, "--rigging", help="索具重量 t"),
    dynamic_factor: float = typer.Option(1.1, "--dynamic-factor"),
    brand: str = typer.Option("徐工", "--brand"),
    mode: str = typer.Option("single", "--mode", help="single 或 dual"),
    second_model: str | None = typer.Option(None, "--second-model", help="双机时的第二台机型"),
    second_brand: str = typer.Option("徐工", "--second-brand"),
    left_share: float | None = typer.Option(
        None, "--left-share", help="主吊承担比例（不给时按重心位置分配，无重心信息则兜底 0.6）"
    ),
    asynchronism: float = typer.Option(1.0, "--asynchronism", help="不同步系数"),
    target_radius: float | None = typer.Option(None, "--target-radius", "--radius", help="单机指定作业幅度 m"),
    config: str | None = typer.Option(None, "--config", help="限定单机性能表配置，传入完整配置名"),
    required_height: float | None = typer.Option(
        None, "--required-height", help="手动指定所需起升高度 m（默认由吊物高+吊索高推算）"
    ),
    load_length: float | None = typer.Option(
        None, "--load-length", "--load-width", help="吊物长 m（立面内、沿幅度方向）"
    ),
    load_depth: float | None = typer.Option(None, "--load-depth", help="吊物宽 m（垂直立面方向）"),
    load_height: float | None = typer.Option(None, "--load-height", help="吊物高 m"),
    cg_x: float | None = typer.Option(None, "--cg-x", help="重心相对形心的 x 偏心 m（沿长度，指向远离吊车为正）"),
    cg_y: float | None = typer.Option(None, "--cg-y", help="重心相对形心的 y 偏心 m（沿宽度）"),
    cg_z: float | None = typer.Option(None, "--cg-z", help="重心相对形心的 z 偏心 m（向上为正）"),
    sling_height: float | None = typer.Option(None, "--sling-height", help="吊索竖直高度 m（吊钩中心到吊点）"),
    lug_inset: float | None = typer.Option(None, "--lug-inset", help="吊点自顶面四角向内收进 m"),
    dual_left_x: float | None = typer.Option(None, "--dual-left-x", help="双机左吊点在吊物上的 x 坐标 m"),
    dual_right_x: float | None = typer.Option(None, "--dual-right-x", help="双机右吊点在吊物上的 x 坐标 m"),
    clearance: float | None = typer.Option(None, "--clearance", help="吊物底距地净空 m"),
    limit: float | None = typer.Option(None, "--limit", help="负荷率上限（默认单机 0.9 / 双机 0.8）"),
    out: Path | None = typer.Option(None, "--out", "-o"),
    db: Path = typer.Option(Path("data/liftcalc.sqlite"), "--db"),
) -> None:
    """反查：给定吊重，能不能吊、最远多少米、多高。"""
    case: dict[str, Any] = {
        "kind": "crane.capability",
        "mode": mode,
        "payload": payload,
        "hook_mass": hook,
        "rigging": rigging,
        "dynamic_factor": dynamic_factor,
        "crane": {"brand": brand, "model": model},
        "asynchronism": asynchronism,
        "target_radius": target_radius,
        "config": config,
    }
    if left_share is not None:
        case["left_share"] = left_share
    if limit is not None:
        case["limit"] = limit
    if required_height is not None:
        case["required_lift_height"] = required_height
    load_fields = (load_length, load_depth, load_height, cg_x, cg_y, cg_z,
                   sling_height, lug_inset, clearance)
    if any(value is not None for value in load_fields):
        case["load"] = {
            "length_m": 3.2 if load_length is None else load_length,
            "width_m": (3.2 if load_length is None else load_length) if load_depth is None else load_depth,
            "height_m": 3.8 if load_height is None else load_height,
            "cg": {"x": cg_x or 0.0, "y": cg_y or 0.0, "z": cg_z or 0.0},
            "lug_inset_m": lug_inset or 0.0,
        }
        if sling_height is not None:
            case["load"]["sling_height_m"] = sling_height
        case["clearance_m"] = 1.0 if clearance is None else clearance
    elif clearance is not None:
        case["clearance_m"] = clearance
    if dual_left_x is not None or dual_right_x is not None:
        case["dual"] = {"left_point_x_m": dual_left_x, "right_point_x_m": dual_right_x}
    if mode == "dual":
        case["second"] = {"brand": second_brand, "model": second_model or model}
    try:
        result = run_case(case, Repo(db))
    except LiftcalcError as exc:
        _fail(exc)
        return
    _emit_result(result, out)

@app.command("render")
def render_png_cmd(
    result_path: Path = typer.Option(..., "--in", "-i", help="结果 JSON"),
    out_dir: Path = typer.Option(..., "--out", "-o", help="输出目录"),
) -> None:
    """把结果渲染成 PNG（无 CAD 时看图用）。"""
    from liftcalc.drawing.png import to_png

    result = ComputationResult.model_validate(_load_json(result_path))
    figures = figures_for(result)
    if not figures:
        typer.echo("该结果没有可用图形", err=True)
        raise typer.Exit(2)
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, figure in enumerate(figures, start=1):
        target = to_png(figure, out_dir / f"{result_path.stem}-{index}.png")
        typer.echo(f"已写入 {target}（{figure.title}）")


@app.command("schema")
def schema(
    out: Path = typer.Option(Path("schemas"), "--out", help="输出目录"),
) -> None:
    """导出 JSON Schema（前端据此生成类型）。"""
    out.mkdir(parents=True, exist_ok=True)
    for kind, model in CASE_MODELS.items():
        path = out / f"{kind.replace('.', '_')}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        typer.echo(f"已写入 {path}")


@app.command("compare")
def compare_cmd(
    case_path: Path = typer.Option(..., "--case", help="case.json 路径"),
    oracle_path: Path = typer.Option(..., "--oracle", help="原程序结果 oracle.json"),
    out: Path = typer.Option(..., "--out", "-o", help="diff.md 输出路径"),
    db: Path | None = typer.Option(None, "--db", help="数据仓库路径"),
) -> None:
    """与原程序结果对拍，输出分级差异报告。"""
    try:
        payload = _load_json(case_path)
        repo = Repo(db) if db is not None else None
        result = run_case(payload, repo)
    except LiftcalcError as exc:
        _fail(exc)
        return

    oracle = _load_json(oracle_path)
    report_obj = compare(result, oracle)
    markdown = report_obj.as_markdown(case_name=case_path.stem, source=str(oracle.get("source", "")))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    typer.echo(f"已写入 {out}（{report_obj.worst}）")
    if report_obj.worst in {"BLOCKING", "HIGH"}:
        raise typer.Exit(1)


@app.command("selftest")
def selftest(
    offline: bool = typer.Option(True, "--offline/--online", help="断网自检"),
) -> None:
    """不依赖数据库的最小自检（发布前必跑）。"""
    payload = {
        "kind": "lifting_eye.check",
        "units": {"length": "mm", "force": "kN", "stress": "MPa"},
        "meta": {"project": "selftest", "part": "eye"},
        "geometry": {"plate_t": 30, "plate_b": 300, "plate_h": 400, "hole_d": 80, "hole_edge": 120},
        "material": {"grade": "Q355B", "fy": 355},
        "load": {"design": 500, "dynamic_factor": 1.1, "angle_deg": 5},
    }
    try:
        parse_case(payload)
        result = run_case(payload)
    except LiftcalcError as exc:
        _fail(exc)
        return
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "offline": offline,
                "checks": len(result.checks),
                "verdict": result.verdict.value,
                "utilization": result.utilization,
            },
            ensure_ascii=False,
        )
    )


def run() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
