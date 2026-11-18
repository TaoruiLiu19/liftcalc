"""QY130H-1（130 t）表Ⅰ转录：配重 30 t，支腿全伸，全方位作业。

源：徐工70~500吨汽车吊参数表.pdf 第 4 页上半表。
该表数值单位为吨（原表标头写 kg，但数值 130 对应 130 t 整机额定，按 t 录入）。
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(r"D:\学习日志\吊装\liftcalc\src\liftcalc\data\pack\crane")
MODEL = "QY130H-1"
PAGE = "4"
CONFIG = "配重30t"
NOTE = "配重30t，支腿全伸，全方位作业；原表无逐格仰角与起升高度"

DATA: dict[float, list[tuple[float, float]]] = {
    13.0: [(3, 130), (3.5, 122), (4, 112), (4.5, 103), (5, 96), (6, 83), (7, 65), (8, 56), (9, 43), (10, 40)],
    17.4: [(3.5, 80), (4, 80), (4.5, 80), (5, 78), (6, 73.2), (7, 65), (8, 56), (9, 45), (10, 41), (12, 32), (14, 25)],
    21.8: [(3.5, 76.5), (4, 75.8), (4.5, 73), (5, 72), (6, 71), (7, 62.5), (8, 58), (9, 48),
           (10, 41), (12, 31.5), (14, 25), (16, 20), (18, 16.6)],
    26.13: [(4, 60), (4.5, 60), (5, 60), (6, 56), (7, 52), (8, 50), (9, 45), (10, 40),
            (12, 31), (14, 25), (16, 20), (18, 16.5), (20, 14), (22, 11.7)],
    30.5: [(4.5, 53), (5, 53), (6, 53), (7, 48), (8, 44), (9, 41), (10, 39), (12, 31),
           (14, 25), (16, 20), (18, 16.5), (20, 14), (22, 11.8), (24, 9.8), (26, 8.1), (28, 6.7)],
    34.88: [(5, 35), (6, 35), (7, 35), (8, 35), (9, 34), (10, 32), (12, 30), (14, 25.5),
            (16, 21), (18, 17.3), (20, 14.5), (22, 12.3), (24, 10.5), (26, 9.2), (28, 7.7),
            (30, 6.5), (32, 5.5)],
    39.3: [(6, 33), (7, 33), (8, 31.5), (9, 29), (10, 28.8), (12, 26.5), (14, 24.5), (16, 20),
           (18, 18), (20, 15.5), (22, 13), (24, 11.5), (26, 9), (28, 8), (30, 7), (32, 6),
           (34, 5), (36, 4)],
    43.6: [(7, 25), (8, 25), (9, 24.5), (10, 23.3), (12, 22), (14, 21), (16, 20), (18, 16.3),
           (20, 13), (22, 11.2), (24, 10), (26, 8.5), (28, 7.2), (30, 7), (32, 6.8), (34, 6),
           (36, 5), (38, 4)],
    48.0: [(8, 20), (9, 20), (10, 20), (12, 19), (14, 18), (16, 16.3), (18, 15.8), (20, 14),
           (22, 11.2), (24, 10), (26, 9), (28, 8), (30, 7.5), (32, 6.8), (34, 6.3), (36, 5.5),
           (38, 5.0), (40, 4), (42, 3.3), (44, 3)],
}


def main() -> None:
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
        for boom in sorted(DATA):
            for radius, load in DATA[boom]:
                writer.writerow([f"{boom:g}", f"{radius:g}", f"{load:g}",
                                 "", "", "", "", "", PAGE, NOTE, CONFIG])
                total += 1
    print(f"已写入 {path.name}：{total} 行")

    models = OUT / "models.csv"
    with models.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not any(row["model"] == MODEL for row in rows):
        rows.append({
            "model": MODEL, "brand": "徐工", "tonnage_class_t": "130",
            "crane_type": "truck", "counterweight_t": "30", "hook_main_t": "",
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
        rows = DATA[boom]
        radii = [r for r, _ in rows]
        loads = [q for _, q in rows]
        if radii != sorted(radii) or len(set(radii)) != len(radii):
            problems.append(f"{boom:g} m：幅度非严格递增")
        if loads != sorted(loads, reverse=True):
            problems.append(f"{boom:g} m：起重量非单调不增")
        if max(loads) > 130:
            problems.append(f"{boom:g} m：起重量超过 130 t")
    if problems:
        print("自检未通过：")
        for item in problems:
            print("  ✗", item)
        raise SystemExit(1)
    print(f"自检通过：{len(DATA)} 个臂长、{total} 格")


if __name__ == "__main__":
    main()
