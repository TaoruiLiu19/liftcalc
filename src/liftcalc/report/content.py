"""Engineering content shared by the HTML and Word reports."""

import re
from dataclasses import dataclass
from itertools import groupby
from math import ceil, floor

from liftcalc.core.result import ComputationResult, Verdict
from liftcalc.crane.capability import DUAL_LIMIT
from liftcalc.drawing.primitives import Figure


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: list[tuple[str, ...]]
    widths: tuple[float, ...] = ()


@dataclass(frozen=True)
class Section:
    title: str
    blocks: list[str | Table | Figure]


@dataclass(frozen=True)
class Report:
    title: str
    status: str
    overview: str
    information: list[tuple[str, str]]
    sections: list[Section]


VERDICTS = {Verdict.PASS: "满足", Verdict.FAIL: "不满足", Verdict.NA: "待核或仅供记录"}


def number(value, unit="", *, precision=3):
    return "—" if value is None else f"{float(value):.{precision}f}".rstrip("0").rstrip(".") + unit


def percent(value):
    return "—" if value is None else f"{value:.2%}"


def bound(value, *, lower=False):
    rounded = floor(value * 1000) if lower else ceil(value * 1000)
    return number(rounded / 1000, " m")


def coordinates(values):
    return "（" + "，".join(number(value) for value in values) + "）"


def attribution(meta):
    return [(label, meta[key]) for label, key in (
        ("工程名称", "project"), ("设计人", "author"), ("日期", "date"),
    ) if meta.get(key)]


def performance_citation(reference, document=None):
    if not reference:
        return ""
    source, _, page = reference.partition("#page=")
    imported = re.fullmatch(r".+\.csv(?: 第([^页]+)页)?", source, flags=re.IGNORECASE)
    if imported:
        source = document or ""
        page = imported[1] or ""
    if not source or source.lower().endswith(".csv"):
        return "原厂起重性能表" + (f"第 {page} 页" if page else "（资料名称待核）")
    if source.startswith(("https://", "http://")):
        return f"{source}#page={page}" if page else source
    name = source[:-4] if source.lower().endswith(".pdf") else source
    return f"《{name}》" + (f"第 {page} 页" if page else "")


def load_section(load):
    cg = load["cg"]
    rows = [
        ("吊物尺寸（长 × 宽 × 高）", " × ".join(number(load[key]) for key in (
            "length_m", "width_m", "height_m")) + " m"),
        ("吊物质量", number(load["weight_t"], " t")),
        ("重心相对形心（x，y，z）", coordinates(cg[key] for key in "xyz") + " m"),
        ("吊点内缩", number(load["lug_inset_m"], " m")),
        ("吊物底面离地高度", number(load["clearance_m"], " m")),
        ("顶面至吊钩中心竖向距离", number(load["sling_height_m"], " m") +
         ("（按最短吊索与水平面成 60° 推算）" if load["sling_height_derived"] else "（输入）")),
    ]
    if load.get("height_source") == "输入":
        height = number(load["hook_height_m"], " m") + "（指定值）"
    else:
        values = [load[key] for key in ("clearance_m", "height_m", "sling_height_m")]
        height = " + ".join(number(v) for v in values) + " = " + number(load["required_lift_height_m"], " m")
    rows.append(("所需吊钩中心离地高度", height))
    blocks = [
        "吊物按长方体处理。坐标原点为形心，x 沿长向且正向远离起重机，y 沿宽向，z 向上。单钩位于重心的铅垂线上。",
        Table(("项目", "取值"), rows, (.38, .62)),
    ]
    if load.get("slings"):
        blocks += [
            "各索仅受拉。名义拉力按竖向分担反力除以吊索与竖直方向夹角的余弦计算。"
            "表列静力上下限按各索分别求取，尚需结合额定承载和现场条件核对索具选型。",
            Table(("索号与位置", "水平距离 (m)", "与竖直夹角 (°)", "竖向分担比例", "名义拉力 (kN)", "静力范围 (kN)"), [
                (f"{s['index']} {s['name']}", number(s["run"]), number(s["angle_deg"], precision=1),
                 percent(s["share"]), number(s["force_t"] * 9.80665, precision=2),
                 f"{s['equilibrium_min_kn']:.2f} 至 {s['equilibrium_max_kn']:.2f}"
                 if s.get("equilibrium_min_kn") is not None else "—")
                for s in load["slings"]
            ], (.15, .15, .19, .15, .16, .20)),
        ]
    return Section("吊物与重心", blocks)


def _single_checks(cap, case, load, checks):
    total, limit = cap["required"], cap["limit"]
    records = cap.get("records", [])
    rated = cap.get("rated_load")
    hook_rating = cap.get("hook_rated_t")
    rows = []
    if hook_rating is not None and all(key in case for key in ("payload", "rigging", "dynamic_factor")):
        demand = case["payload"] + case["rigging"] * case["dynamic_factor"]
        rows.append(("主吊钩组承载", number(demand, " t"), "≤ " + number(hook_rating, " t"),
                     "不满足" if demand > hook_rating + 1e-9 else "满足"))
    else:
        rows.append(("主吊钩组承载", number(cap.get("hook_mass"), " t") + "（吊钩组质量）", "额定起重量", "待核"))
    if rated:
        rows.append(("起重性能表负荷率", f"{number(total)} ÷ {number(rated)} = {percent(cap['utilization'])}",
                     "≤ " + percent(limit), "满足"))
    elif cap.get("closest_utilization") is not None:
        rows.append(("最有利表档负荷率", percent(cap["closest_utilization"]), "≤ " + percent(limit), "不满足"))
    else:
        reasons = {record["reason"] for record in records}
        rows.append(("起重性能表负荷率", "已核对表列候选", "≤ " + percent(limit),
                     "不满足" if reasons == {"负荷率超限"} else "见候选表"))
    height = next((check for check in checks if check.id == "capability.lift_height"), None)
    if height is not None:
        demand, available = height.inputs["required"], height.inputs["available"]
        rows.append(("起升高度", number(available, " m"), "≥ " + number(demand, " m"), VERDICTS[height.verdict]))
    elif load:
        target = load.get("hook_height_m", load.get("required_lift_height_m"))
        height_failures = [row["lift_height"] for row in records if row["reason"] == "起升高度不足"]
        if height_failures and {row["reason"] for row in records} == {"起升高度不足"}:
            rows.append(("起升高度", number(max(height_failures), " m") + "（候选最大值）",
                         "≥ " + number(target, " m"), "不满足"))
        else:
            rows.append(("起升高度", "缺少已采用工况的校核结果", "≥ " + number(target, " m"), "待核"))
    blocks = []
    if rated:
        adopted = next((row for row in records
                        if (row["config"], row["boom_len"], row["radius"])
                        == (cap.get("config"), cap["boom_len"], cap["max_radius"])), {})
        blocks.append(
            f"采用{cap.get('config') or '所选机型工况'}，起重臂长度 {number(cap['boom_len'], ' m')}，"
            f"表列工作幅度 {number(cap['max_radius'], ' m')}，额定总起重量 {number(rated, ' t')}。"
        )
        if adopted.get("source_ref"):
            blocks.append(f"采用表档出处为 {performance_citation(adopted['source_ref'], cap.get('source_doc'))}。")
    elif cap.get("shortfall_t") is not None:
        blocks.append(f"最有利表档工作幅度 {number(cap['closest_radius'], ' m')}。计算总起重量超过该档允许值 "
                      f"{number(cap['shortfall_t'], ' t')}。")
    if cap.get("hook_source_ref"):
        blocks.append(f"主吊钩组资料出处为 {performance_citation(cap['hook_source_ref'])}。")
    blocks.append(Table(("校核项目", "计算或表列值", "判据", "判定"), rows, (.24, .37, .22, .17)))
    return Section("采用工况与逐项校核", blocks)


def _candidate_section(cap):
    groups = {}
    for row in cap.get("records", []):
        groups.setdefault((row["config"], row["boom_len"]), []).append(row)
    rows = []
    for (config, boom), group in groups.items():
        selected = next((row for row in reversed(group) if row["reason"] == "满足"), None)
        if selected:
            other = next((row for row in group if row["radius"] > selected["radius"]), None)
        else:
            other = max(group, key=lambda row: row["rated_load"])
        reason = f"{number(other['radius'], ' m')} {other['reason']}" if other else "—"
        rows.append((config or "默认", number(boom), number(selected["radius"]) if selected else "—", reason))
    if not rows:
        return None
    return Section("候选性能表工况", [
        "指定工作幅度时，每组工况与臂长向外取可覆盖的表档。反查时记录通过的最大表列幅度"
        "及其后的首个表档。没有通过表档的组记录额定起重量最大的候选及其判定。",
        Table(("性能表工况", "臂长 (m)", "通过幅度 (m)", "其余代表表档及判定"), rows, (.36, .14, .18, .32)),
    ])


def design_report(result: ComputationResult, *, title=None, case_payload=None, figure=None):
    case = result.aux.get("case") or case_payload or {}
    meta = (case_payload or case).get("meta") or {}
    cap, load = result.aux.get("capability") or {}, result.aux.get("load") or {}
    information = attribution(meta)
    if result.data_version:
        information.append(("性能资料版本" if cap else "资料版本", result.data_version))
    if result.input_digest:
        information.append(("计算编号", result.input_digest[:8].upper()))
    if not cap:
        if title is None:
            title = "工程校核计算书"
        checks = [
            Section(check.title, [*[text for text in (check.substituted, check.source) if text],
                                  Table(("计算值", "限值", "利用率", "判定"), [(
                                      number(check.value, f" {check.unit}".rstrip()),
                                      number(check.limit, f" {check.unit}".rstrip()),
                                      percent(check.ratio), VERDICTS[check.verdict])]), *check.notes])
            for check in result.checks
        ]
        if result.warnings:
            checks.append(Section("待复核事项", result.warnings))
        return Report(title, VERDICTS[result.verdict], "校核对象与计算判据见各分项记录。", information, checks)

    dual = cap.get("mode") == "dual"
    title = title or ("双机静态抬吊校核计算书" if dual else "单机吊装设计计算书")
    crane = case.get("crane") or {}
    target = cap.get("target_radius")
    information += [
        ("起重机", " ".join(filter(None, (crane.get("brand"), crane.get("model", cap.get("model")))))),
        ("工作目的", f"校核指定工作幅度 {number(target, ' m')}" if target is not None else "反查最大工作幅度"),
    ]
    status = cap.get("status") or ("满足" if cap["ok"] else "不满足")
    if not dual and status == "满足" and (
        cap.get("hook_rated_t") is None or (load and not any(
            check.id == "capability.lift_height" for check in result.checks
        ))
    ):
        status = "表列承载满足，另有待核"
    overview = (cap.get("explanation") or "双机静态分载条件及分别采用的性能表工况见正文。")
    overview = overview.replace("并绘制立面", "").replace("；", "。")
    payload = case.get("payload", load.get("weight_t"))
    hook = cap.get("hook_mass", case.get("hook_mass"))
    rigging, factor = case.get("rigging"), case.get("dynamic_factor")
    composition = [
        ("吊物质量", number(payload, " t")), ("吊钩组质量", number(hook, " t")),
        ("吊具及索具质量", number(rigging, " t")), ("索具动载系数", number(factor)),
        ("计算总起重量", number(cap["required"], " t")),
    ]
    if all(value is not None for value in (payload, hook, rigging, factor)):
        composition.append(("代入式", f"{number(payload)} + {number(hook)} + {number(rigging)} × "
                            f"{number(factor)} = {number(cap['required'], ' t')}"))
    sections = [Section("校核依据与计算条件", [
        "起重能力取自所选机型的原厂起重性能表。吊物、吊钩组及索具参数取自本次工况输入和已采用的机型资料。",
        f"计算总起重量为吊物质量、吊钩组质量及计入动载系数的吊具和索具质量之和。"
        f"本次采用的负荷率上限为 {percent(cap['limit'])}。",
        Table(("项目", "计算取值"), composition, (.43, .57)),
    ])]
    if load:
        sections.append(load_section(load))
    if dual:
        split = cap["split"]
        basis = ("按重心位置分配。两吊点长向坐标为 "
                 f"{number(split['left_x'])} m 和 {number(split['right_x'])} m。"
                 if split["basis"] == "cg" else "按输入条件采用默认分载比例。")
        sections.append(Section("双机抬吊的负荷分配", [
            basis + f"放大前的计算总起重量乘不同步系数 {number(cap['asynchronism'])} 后，按比例分配至两机。",
            Table(("机组", "分担比例", "计算总起重量 (t)", "最大工作幅度 (m)", "负荷率", "判定"), [
                (f"{label} {side['model']}", percent(split[key+"_share"]), number(side["required"]),
                 number(side["max_radius"]), percent(side["utilization"]), "满足" if side["ok"] else "不满足")
                for key, label in (("left", "主吊"), ("right", "辅吊")) for side in (cap[key],)
            ]),
        ]))
    else:
        sections.append(_single_checks(cap, case, load, result.checks))
        candidates = _candidate_section(cap)
        if candidates:
            sections.append(candidates)
    sections.append(Section("审查结论与待核事项", [
        f"本次校核判定为{status}。{overview.rstrip('。')}。",
        *dict.fromkeys([*result.warnings, *load.get("notes", [])]),
        "实车配重、支腿状态、作业方位、吊点与索具承载及场地条件由工程审查确认。",
    ]))
    if figure is not None:
        sections.append(Section("附图", [figure]))
    return Report(title, status, overview.rstrip("。") + "。", information, sections)


def transfer_report(case, result, drawings, meta, chart_sources=()):
    information = attribution(meta)
    geometry = Table(("项目", "取值"), [
        ("吊物尺寸（长 × 宽 × 高）", " × ".join(number(v) for v in (case.length, case.width, case.height)) + " m"),
        ("吊物质量", number(case.mass, " t")),
        ("重心 G", coordinates(case.cg) + " m"),
        ("吊点 A 和 B", " / ".join(coordinates(lug) for lug in case.lugs) + " m"),
        ("起吊与落位姿态（X，Y，纵轴方向角）",
         " / ".join(f"（{number(x, ' m')}，{number(y, ' m')}，{number(yaw, '°')}）"
                    for x, y, yaw in (case.start, case.end))),
        ("载荷放大系数", number(case.factor)),
        ("每台起重机负荷率上限", percent(DUAL_LIMIT)),
        ("要求的水平净距", number(case.plan_clearance, " m")),
        *((f"{tag} 机占地与起重臂包络",
           f"{number(c.footprint_length)} × {number(c.footprint_width)} m，"
           f"起重臂水平包络半宽 {number(c.boom_buffer, ' m')}")
          for tag, c in zip("AB", case.cranes)),
        *((f"障碍物 {i}", f"场地中心 {coordinates((x, y))} m，禁入半径 {number(radius, ' m')}")
          for i, (x, y, radius) in enumerate(case.obstacles, 1)),
    ], (.48, .52))
    sections = [Section("校核范围与输入条件", [
        "按水平刚体、两个固定吊点及两根竖向吊索进行静力分载。转运校核覆盖工作幅度、负荷率和水平净距。"
        "起升高度、起升与下放过程以及支腿地基承载需另行核对。",
        "吊点与重心采用以吊物形心为原点的局部坐标。起吊、落位和障碍物采用场地坐标，纵轴方向角从场地 X 轴逆时针量取。",
        geometry,
    ])]
    if not drawings:
        sections[0].blocks.append(Table(("机组", "指定机型", "性能表工况"), [
            (tag, f"{c.brand} {c.model}", c.config or "自动选择")
            for tag, c in zip("AB", case.cranes)
        ], (.20, .35, .45)))
        sections.append(Section("未生成可用轨迹的原因", [result["summary"], *result["reasons"]]))
        return Report("双机抬吊上轨设计计算书", "未生成可用轨迹", result["summary"], information, sections)

    segments = result["segments"]
    status = ("不通过" if any(s["unsafe"] for s in segments) else
              "待核" if any(s["unknown"] for s in segments) else "所列校核满足")
    clearance = result["clearance"]
    overview = (f"水平净距下界 {bound(clearance['lower_m'], lower=True)}，控制位置为 P{clearance['leg']-1} 至 "
                f"P{clearance['leg']}，涉及{clearance['pair']}。")
    if len(chart_sources) == 2 and chart_sources[0] and chart_sources[0] == chart_sources[1]:
        citations = [f"A、B 两机原厂性能表出处均为 {chart_sources[0]}。"]
    else:
        citations = [f"{tag} 机原厂性能表出处为 {source}。" for tag, source in zip("AB", chart_sources) if source]
    sections.append(Section("静力分载与起重机工况", [
        "在两吊点连线上，以重心投影至对侧吊点的距离除以两吊点间距，得到本侧分担比例。"
        "各机计算总起重量为分担吊物质量与本侧吊索具质量之和乘载荷放大系数，再加本机主吊钩组质量。",
        Table(("机组与机型", "分载与计算总起重量", "采用工况与臂长", "回转中心与轴向"), [
            (f"{tag} {c.brand} {c.model}",
             f"{percent(share)} · {number(share*case.mass, ' t')} / {number(gross, ' t')}",
             f"{c.config} · {number(c.boom, ' m')}",
             coordinates(c.center) + f" m · {number(c.heading)}°")
            for tag, c, share, gross in zip("AB", case.cranes, result["shares"], result["loads"])
        ], (.22, .25, .30, .23)),
        *citations,
        Table(("机组", "吊物分担质量 (t)", "吊索具质量 (t)", "主吊钩组质量 (t)", "主吊钩组额定起重量 (t)"), [
            (tag, number(share*case.mass), number(c.rigging), number(c.hook), number(c.hook_rating))
            for tag, c, share in zip("AB", case.cranes, result["shares"])
        ], (.12, .22, .2, .21, .25)),
    ]))
    sections.append(Section("转运路径与分段校核", [
        overview,
        "各段按工作幅度包络查同一组工况和臂长。区间内存在较大表列幅度时向外取档。",
        Table(("区段", "A 机幅度上界 / 负荷率", "B 机幅度上界 / 负荷率", "判定"), [
            (f"P{leg-1} 至 P{leg}", *(
                bound(max(s["radii"][i][1] for s in group)) + " / " +
                percent(max((s["ratios"][i] for s in group if s["ratios"][i] is not None), default=None))
                for i in (0, 1)),
             "不通过" if any(s["unsafe"] for s in group) else
             "待核" if any(s["unknown"] for s in group) else "满足")
            for leg, grouped in groupby(segments, key=lambda s: s["leg"]) for group in (list(grouped),)
        ], (.17, .32, .32, .19)),
    ]))
    issues = {}
    for segment in segments:
        for key, label in (("unsafe", "不通过"), ("unknown", "待核")):
            for reason in segment[key]:
                issue = (segment["leg"], label, reason)
                evidence = (segment.get("evidence") or {}).get(reason, {})
                ranges = issues.setdefault(issue, [])
                if ranges and ranges[-1][1] == segment["start"]:
                    start, _, previous = ranges[-1]
                    ranges[-1] = (start, segment["end"], previous or evidence)
                else:
                    ranges.append((segment["start"], segment["end"], evidence))
    if issues:
        sections.append(Section("不通过与待核证据", [Table(("区段与进度", "校核问题", "记录与数值"), [
            (f"P{leg-1} 至 P{leg} · {percent(start)} 至 {percent(end)}",
             f"{label} · {reason}",
             (f"{percent(evidence['progress'])}　" if evidence.get("progress") is not None else "")
             + (evidence.get("text") or "详见对应区段的校核条件。"))
            for (leg, label, reason), ranges in issues.items() for start, end, evidence in ranges
        ], (.23, .31, .46))]))
    sections.append(Section("审查结论与待核事项", [
        f"本次转运方案判定为{status}。{overview}",
        "复核时应核对两机实际配重、支腿状态及允许作业方位，确认现场边界与障碍物位置，并校核两机起重臂和吊具的三维净距。",
    ]))
    sections.append(Section("起吊与转运图纸", list(drawings)))
    return Report("双机抬吊上轨设计计算书", status, overview, information, sections)
