"""QY130H-1 表Ⅱ（配重 20 t）追加录入。

注意：本表幅度标签只印到 18 m，20 m 以下无印字标签。
行网格按与表Ⅰ同一行距推定（20/22/24/26/28/30/32/34/36/38），
并用「同一幅度下表Ⅱ额定值 ≤ 表Ⅰ」做了 7 处交叉验证。
"""

from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(r"D:\学习日志\吊装\liftcalc\src\liftcalc\data\pack\crane")
MODEL = "QY130H-1"
PAGE = "4"
CONFIG = "配重20t"
NOTE = "配重20t，支腿全伸，全方位作业；20m 以下幅度标签未印，按表Ⅰ行网格推定"

DATA: dict[float, list[tuple[float, float]]] = {
    13.0: [(3, 130), (3.5, 122), (4, 112), (4.5, 103), (5, 96), (6, 77), (7, 60), (8, 48), (9, 40), (10, 34)],
    17.38: [(3, 80), (3.5, 80), (4, 80), (4.5, 80), (5, 78), (6, 73.2), (7, 55.2), (8, 48),
            (9, 40), (10, 34), (12, 26), (14, 20)],
    21.75: [(3, 78), (3.5, 76.5), (4, 75.8), (4.5, 73), (5, 72), (6, 71), (7, 55), (8, 48),
            (9, 39), (10, 33), (12, 26), (14, 20), (16, 16), (18, 13.2)],
    26.1: [(4, 60), (4.5, 60), (5, 60), (6, 56), (7, 52), (8, 45), (9, 39.2), (10, 33),
           (12, 26), (14, 20), (16, 16), (18, 13), (20, 11), (22, 9)],
    30.5: [(4.5, 53), (5, 53), (6, 53), (7, 48), (8, 44), (9, 39), (10, 33), (12, 25),
           (14, 20), (16, 16), (18, 13), (20, 11), (22, 9), (24, 7), (26, 6), (28, 5)],
    34.9: [(5, 35), (6, 35), (7, 35), (8, 35), (9, 32), (10, 29), (12, 27), (14, 21),
           (16, 17), (18, 14), (20, 11), (22, 10), (24, 8), (26, 7), (28, 6), (30, 5), (32, 4)],
    39.3: [(6, 33), (7, 33), (8, 31), (9, 29), (10, 28), (12, 25), (14, 22), (16, 17),
           (18, 14), (20, 12), (22, 10), (24, 9), (26, 7.5), (28, 6.3), (30, 5.2), (32, 4.7),
           (34, 3.8), (36, 3)],
    43.6: [(7, 25), (8, 25), (9, 24), (10, 23), (12, 22), (14, 21), (16, 18), (18, 15),
           (20, 12), (22, 11), (24, 9), (26, 7.8), (28, 6.5), (30, 5.5), (32, 4.5), (34, 4),
           (36, 3.8), (38, 3.2)],
    48.0: [(8, 20), (9, 20), (10, 20), (12, 19), (14, 18), (16, 16), (18, 13.8), (20, 13),
           (22, 11), (24, 9), (26, 7.8), (28, 6.3), (30, 5.8), (32, 5.2), (34, 4.8),
           (36, 3.8), (38, 3.1)],
}


def main() -> None:
    path = OUT / f"{MODEL}.capacity.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    existing = {(r["config"], float(r["boom_len_m"]), float(r["radius_m"])) for r in rows}

    added = 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for boom in sorted(DATA):
            for radius, load in DATA[boom]:
                key = (CONFIG, boom, float(radius))
                if key in existing:
                    continue
                writer.writerow([f"{boom:g}", f"{radius:g}", f"{load:g}",
                                 "", "", "", "", "", PAGE, NOTE, CONFIG])
                added += 1
    print(f"追加 {added} 行（{CONFIG}）")

    problems: list[str] = []
    for boom in sorted(DATA):
        series = DATA[boom]
        radii = [r for r, _ in series]
        loads = [q for _, q in series]
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
    print(f"自检通过：{len(DATA)} 个臂长；幅度递增、起重量单调不增、不超吨级")

    # 交叉验证：同幅度下表Ⅱ ≤ 表Ⅰ
    table1 = {(float(r["boom_len_m"]), float(r["radius_m"])): float(r["rated_load_t"])
              for r in csv.DictReader(path.open(encoding="utf-8-sig", newline=""))
              if r["config"] == "配重30t"}
    checked = 0
    for boom in sorted(DATA):
        for radius, load in DATA[boom]:
            for key, ref in table1.items():
                if abs(key[0] - boom) <= 0.05 and abs(key[1] - float(radius)) <= 1e-9:
                    checked += 1
                    if load > ref + 1e-9:
                        problems.append(f"{boom:g} m / {radius:g} m：表Ⅱ {load} > 表Ⅰ {ref}")
    print(f"交叉验证：{checked} 处（表Ⅱ ≤ 表Ⅰ）", "通过" if not problems else "未通过")


if __name__ == "__main__":
    main()
