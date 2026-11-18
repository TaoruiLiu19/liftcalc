"""QAY200（200 t，全地面）主臂性能表转录（源：徐工70~500吨汽车吊参数表.pdf 第 7 页）。

单位：吨。12 个臂长 × 34 个幅度。
表尾给出吊臂仰角区间（按臂长）、吊钩自重、倍率与伸缩方式。
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(r"D:\学习日志\吊装\liftcalc\src\liftcalc\data\pack\crane")
MODEL = "QAY200"
PAGE = "7"
NOTE = "主臂工况；单位吨；原表无逐格仰角与起升高度"

RAW = """
13.8|3:200,3.5:185,4:170,4.5:153.6,5:138.2,6:114.7,7:97.4,8:84.2,9:73.8,10:65.4
18.1|3.5:120,4:118,4.5:115,5:110,6:105,7:98.4,8:85.3,9:74.9,10:66.5,11:59.5,12:53.3,14:43.5
22.5|4:115,4.5:112,5:104.5,6:92.5,7:84,8:73.5,9:68,10:61,11:57,12:53,14:44.6,16:36.5,18:29.9
26.8|4:98,4.5:95,5:91,6:85,7:78,8:72.5,9:65.5,10:58,11:53,12:48,14:43,16:37.4,18:30.7,20:25.6,22:21.7
31.2|4.5:78,5:75,6:72.5,7:68,8:63,9:57,10:53,11:49,12:47,14:42,16:37,18:31.7,20:26.6,22:22.6,24:19.4,26:16.8
35.5|5:61,6:60,7:57,8:52,9:48,10:45,11:42,12:40,14:35,16:31,18:28,20:25.5,22:22.5,24:20.5,26:19.2,28:17.2,30:15.3,32:13.4
39.9|6:50,7:48.5,8:45.2,9:43.2,10:40.6,11:38.2,12:36.2,14:31.6,16:28.5,18:25.8,20:23.5,22:21.8,24:19.5,26:18.3,28:16.1,30:14.2,32:12.6,34:11.2,36:9.9
44.2|7:41,8:39,9:37,10:35,11:33.8,12:32.5,14:28.9,16:26,18:23.5,20:21.2,22:19.2,24:17.6,26:16.5,28:15.2,30:14.2,32:13,34:11.6,36:11.2,38:10.3,40:9.3,42:8.3
48.5|8:32.5,9:32,10:31,11:30,12:28.6,14:26,16:23.6,18:21.6,20:19.6,22:18,24:16.5,26:15.2,28:14,30:13,32:12,34:11.2,36:10.5,38:9.6,40:8.8,42:7.9,44:7.1
52.9|9:26.5,10:26,11:25.5,12:24.8,14:23.2,16:21.4,18:19.6,20:18.1,22:16.8,24:15.5,26:14.5,28:13.4,30:12.2,32:11.5,34:10.5,36:9.6,38:8.8,40:8.4,42:7.8,44:7.5,46:7,48:6.3
57.2|10:22.5,11:21.2,12:20,14:18.5,16:17,18:15.6,20:14.4,22:13.4,24:12.5,26:11.7,28:11,30:10.5,32:10,34:9.5,36:8.5,38:7.5,40:6.8,42:6.5,44:6.2,46:5.9,48:5.4,50:5,52:4.7
61|11:19.4,12:18.2,14:16.8,16:15.5,18:14.5,20:13.5,22:12.5,24:11.5,26:10.8,28:10,30:9.2,32:8.5,34:7.8,36:7.2,38:6.8,40:6.2,42:5.9,44:5.6,46:5.3,48:5,50:4.7,52:4.4,54:4.1,56:3.8
"""


def parse() -> dict[float, list[tuple[float, float]]]:
    data: dict[float, list[tuple[float, float]]] = {}
    for line in RAW.strip().splitlines():
        boom_text, pairs_text = line.split("|")
        pairs = []
        for item in pairs_text.split(","):
            radius_text, load_text = item.split(":")
            pairs.append((float(radius_text), float(load_text)))
        data[float(boom_text)] = pairs
    return data


def main() -> None:
    data = parse()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{MODEL}.capacity.csv"
    total = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["boom_len_m", "radius_m", "rated_load_t", "boom_angle_deg",
             "boom_max_angle_deg", "boom_min_angle_deg", "lift_height_m",
             "parts_of_line", "source_page", "note", "config"]
        )
        for boom in sorted(data):
            for radius, load in data[boom]:
                writer.writerow([f"{boom:g}", f"{radius:g}", f"{load:g}",
                                 "", "", "", "", "", PAGE, NOTE, "主臂"])
                total += 1
    print(f"已写入 {path.name}：{total} 行，{len(data)} 个臂长")

    models = OUT / "models.csv"
    with models.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not any(row["model"] == MODEL for row in rows):
        rows.append({
            "model": MODEL, "brand": "徐工", "tonnage_class_t": "200",
            "crane_type": "all_terrain", "counterweight_t": "", "hook_main_t": "2.41",
            "hook_aux_t": "1.586", "max_outrigger_reaction_kN": "", "self_weight_t": "",
            "source_doc": "徐工70~500吨汽车吊参数表.pdf", "source_page": PAGE,
            "outrigger_lx_m": "9.625", "outrigger_ly_m": "8.7",
        })
        fields = list(rows[0].keys())
        for extra in ("outrigger_lx_m", "outrigger_ly_m"):
            if extra not in fields:
                fields.append(extra)
                for row in rows:
                    row.setdefault(extra, "")
        with models.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"已追加机型 {MODEL}（自重待补，支腿 9.625×8.7）")

    problems: list[str] = []
    for boom in sorted(data):
        radii = [r for r, _ in data[boom]]
        loads = [q for _, q in data[boom]]
        if radii != sorted(radii) or len(set(radii)) != len(radii):
            problems.append(f"{boom:g} m：幅度非严格递增")
        if loads != sorted(loads, reverse=True):
            problems.append(f"{boom:g} m：起重量非单调不增")
        if max(loads) > 200:
            problems.append(f"{boom:g} m：起重量超过 200 t")
    if data[13.8][0][1] != 200:
        problems.append(f"13.8 m 臂首值 {data[13.8][0][1]} ≠ 200 t（与参数表不符）")
    if max(data) != 61 or min(data) != 13.8:
        problems.append("臂长范围不是 13.8~61 m")
    if problems:
        print("自检未通过：")
        for item in problems:
            print("  ✗", item)
        raise SystemExit(1)
    print(f"自检通过：{len(data)} 个臂长、{total} 格；臂长 13.8~61 m；13.8 m 首值 200 t")


if __name__ == "__main__":
    main()
