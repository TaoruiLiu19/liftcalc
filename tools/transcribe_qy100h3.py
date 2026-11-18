"""QY100H-3（100 t）性能表转录（源：徐工70~500吨汽车吊参数表.pdf 第 2 页）。

该页结构与 QY70K-1 不同：每个臂长只有额定起重量一个数，
没有逐格的仰角与起升高度；表头注明「带活动配重时」「支腿全伸、侧方、后方作业」。
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(r"D:\学习日志\吊装\liftcalc\src\liftcalc\data\pack\crane")
MODEL = "QY100H-3"
PAGE = "2"
NOTE = "带活动配重时；支腿全伸，侧方/后方作业；原表无逐格仰角与起升高度"

# 臂长 -> 倍率 -> [(幅度, 起重量kg)]
DATA: dict[float, tuple[int, list[tuple[float, int]]]] = {
    13.0: (14, [
        (3.0, 100000), (3.5, 93000), (4.0, 88000), (4.5, 79000), (5.0, 72000),
        (5.5, 65000), (6.0, 59000), (6.5, 54000), (7.0, 50000), (7.5, 46000),
        (8.0, 42000), (9.0, 36500), (10.0, 32000),
    ]),
    17.8: (11, [
        (3.0, 80000), (3.5, 77000), (4.0, 72000), (4.5, 67000), (5.0, 62000),
        (5.5, 58000), (6.0, 55000), (6.5, 52000), (7.0, 49000), (7.5, 45000),
        (8.0, 41000), (9.0, 35500), (10.0, 31000), (11.0, 27500), (12.0, 23500),
        (14.0, 17500),
    ]),
    22.5: (9, [
        (3.5, 62000), (4.0, 62000), (4.5, 61000), (5.0, 60000), (5.5, 56000),
        (6.0, 52000), (6.5, 48200), (7.0, 45000), (7.5, 42500), (8.0, 40500),
        (9.0, 35000), (10.0, 30500), (11.0, 26500), (12.0, 23300), (14.0, 17000),
        (16.0, 13000), (18.0, 10000),
    ]),
    27.2: (6, [
        (4.5, 42000), (5.0, 42000), (5.5, 42000), (6.0, 42000), (6.5, 40500),
        (7.0, 39000), (7.5, 37000), (8.0, 35500), (9.0, 32500), (10.0, 30000),
        (11.0, 27500), (12.0, 24500), (14.0, 18500), (16.0, 14200), (18.0, 11200),
        (20.0, 9000), (22.0, 7200),
    ]),
    31.9: (6, [
        (5.0, 40000), (5.5, 39000), (6.0, 37500), (6.5, 35800), (7.0, 34500),
        (7.5, 33000), (8.0, 31800), (9.0, 29500), (10.0, 27500), (11.0, 25700),
        (12.0, 24000), (14.0, 19500), (16.0, 15000), (18.0, 12000), (20.0, 9700),
        (22.0, 7900), (24.0, 6200), (26.0, 5000),
    ]),
    36.6: (5, [
        (6.0, 31500), (6.5, 31000), (7.0, 29500), (7.5, 28700), (8.0, 27600),
        (9.0, 25700), (10.0, 24000), (11.0, 22600), (12.0, 21200), (14.0, 18800),
        (16.0, 16000), (18.0, 12600), (20.0, 10300), (22.0, 8500), (24.0, 7000),
        (26.0, 5800), (28.0, 4900), (30.0, 3900), (32.0, 3000),
    ]),
    41.3: (5, [
        (8.0, 23500), (9.0, 22000), (10.0, 20800), (11.0, 19500), (12.0, 18900),
        (14.0, 16900), (16.0, 15200), (18.0, 13200), (20.0, 10900), (22.0, 9000),
        (24.0, 7600), (26.0, 6300), (28.0, 5200), (30.0, 4300), (32.0, 3600),
        (34.0, 2800), (36.0, 2200),
    ]),
    46.0: (3, [
        (9.0, 18500), (10.0, 17500), (11.0, 16500), (12.0, 15900), (14.0, 14500),
        (16.0, 13200), (18.0, 12000), (20.0, 11000), (22.0, 9400), (24.0, 7900),
        (26.0, 6500), (28.0, 5600), (30.0, 4800), (32.0, 3900), (34.0, 3200),
        (36.0, 2700), (38.0, 2200), (40.0, 1800),
    ]),
    50.4: (3, [
        (11.0, 14000), (12.0, 13200), (14.0, 12200), (16.0, 11200), (18.0, 10200),
        (20.0, 9300), (22.0, 8700), (24.0, 8000), (26.0, 6900), (28.0, 5800),
        (30.0, 4900), (32.0, 4200), (34.0, 3600), (36.0, 2900), (38.0, 2400),
        (40.0, 1900), (42.0, 1600),
    ]),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{MODEL}.capacity.csv"
    total = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["boom_len_m", "radius_m", "rated_load_t", "boom_angle_deg",
             "boom_max_angle_deg", "boom_min_angle_deg",
             "lift_height_m", "parts_of_line", "source_page", "note"]
        )
        for boom in sorted(DATA):
            parts, rows = DATA[boom]
            for radius, kg in rows:
                writer.writerow([f"{boom:g}", f"{radius:g}", f"{kg / 1000:g}",
                                 "", "", "", "", parts, PAGE, NOTE])
                total += 1
    print(f"已写入 {path.name}：{total} 行")

    models = OUT / "models.csv"
    with models.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not any(row["model"] == MODEL for row in rows):
        rows.append({
            "model": MODEL, "brand": "徐工", "tonnage_class_t": "100",
            "crane_type": "truck", "counterweight_t": "", "hook_main_t": "",
            "hook_aux_t": "", "max_outrigger_reaction_kN": "", "self_weight_t": "",
            "source_doc": "徐工70~500吨汽车吊参数表.pdf", "source_page": PAGE,
        })
        with models.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"已追加机型 {MODEL}")

    problems: list[str] = []
    for boom in sorted(DATA):
        parts, rows = DATA[boom]
        radii = [r for r, _ in rows]
        loads = [q for _, q in rows]
        if radii != sorted(radii) or len(set(radii)) != len(radii):
            problems.append(f"{boom:g} m 臂：幅度非严格递增")
        if loads != sorted(loads, reverse=True):
            problems.append(f"{boom:g} m 臂：起重量非单调不增")
        if max(loads) > 100000:
            problems.append(f"{boom:g} m 臂：起重量超过 100 t")
    if problems:
        print("自检未通过：")
        for item in problems:
            print("  ✗", item)
        raise SystemExit(1)
    print(f"自检通过：{len(DATA)} 个臂长、{total} 格；幅度递增、起重量单调不增、不超吨级")


if __name__ == "__main__":
    main()
