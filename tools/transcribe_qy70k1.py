"""QY70K-1 性能表转录（源：徐工70~500吨汽车吊参数表.pdf 第 1 页）。

每格三个数：额定起重量 kg（原表）、主臂仰角 °、起升高度 m。
转录后用四道自检拦截抄错：单调性、首末仰角与表头一致、起升高度几何一致性。

几何一致性：起升高度 ≈ 臂长×sin(仰角) + 常数 − 臂架挠度，
故 起升高度 − 臂长×sin(仰角) 应落在 [−2.5, +1.5] m 内；
超出即说明该格至少有一个数字抄错。
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

OUT = Path(r"D:\学习日志\吊装\liftcalc\src\liftcalc\data\pack\crane")
PAGE = "1"

# 臂长 -> (倍率, 最小仰角, 最大仰角, [(幅度, 起重量kg, 仰角°, 起升高度m)])
DATA: dict[float, tuple[int, float, float, list[tuple[float, int, float, float]]]] = {
    11.60: (12, 29.8, 71.5, [
        (3.0, 70000, 71.5, 11.81),
        (3.5, 63500, 68.8, 11.58),
        (4.0, 54500, 66.0, 11.33),
        (5.0, 47000, 60.3, 10.71),
        (6.0, 38500, 54.1, 9.94),
        (7.0, 29500, 47.3, 8.97),
        (8.0, 22500, 39.5, 7.70),
        (9.0, 17800, 29.8, 5.93),
    ]),
    15.71: (9, 34.5, 73.1, [
        (4.0, 47500, 73.1, 15.84),
        (5.0, 42600, 69.2, 15.42),
        (6.0, 37000, 65.1, 14.91),
        (7.0, 28800, 60.9, 14.31),
        (8.0, 22300, 56.4, 13.60),
        (9.0, 17700, 51.7, 12.76),
        (10.0, 14400, 46.6, 11.77),
        (12.0, 9700, 34.5, 9.05),
    ]),
    19.82: (8, 31.4, 77.2, [
        (4.0, 40600, 77.2, 20.17),
        (5.0, 38500, 74.2, 19.85),
        (6.0, 34200, 71.1, 19.47),
        (7.0, 28500, 67.9, 19.02),
        (8.0, 22300, 64.7, 18.50),
        (9.0, 17600, 61.3, 17.91),
        (10.0, 14300, 57.8, 17.24),
        (12.0, 9600, 50.4, 15.59),
        (14.0, 6800, 41.9, 13.39),
        (16.0, 4800, 31.4, 10.30),
    ]),
    25.98: (6, 29.2, 79.4, [
        (5.0, 27600, 79.4, 26.31),
        (6.0, 25500, 77.1, 26.03),
        (7.0, 23500, 74.8, 25.70),
        (8.0, 21500, 72.4, 25.33),
        (9.0, 18700, 70.0, 24.91),
        (10.0, 15500, 67.6, 24.43),
        (12.0, 10800, 62.6, 23.32),
        (14.0, 7800, 57.2, 21.96),
        (16.0, 5800, 51.5, 20.30),
        (18.0, 4400, 45.3, 18.24),
        (20.0, 3300, 38.1, 15.62),
        (22.0, 2400, 29.2, 12.06),
    ]),
    32.15: (4, 36.2, 79.6, [
        (7.0, 18200, 79.6, 32.22),
        (8.0, 17500, 77.7, 31.93),
        (9.0, 16000, 75.8, 31.60),
        (10.0, 14500, 73.9, 31.23),
        (12.0, 11500, 70.1, 30.37),
        (14.0, 8500, 66.1, 29.35),
        (16.0, 6500, 61.9, 28.14),
        (18.0, 5000, 57.6, 26.72),
        (20.0, 3900, 53.0, 25.04),
        (22.0, 3000, 48.0, 23.06),
        (24.0, 2300, 42.5, 20.67),
        (26.0, 1700, 36.2, 17.71),
    ]),
    38.31: (3, 39.4, 80.0, [
        (8.0, 14100, 80.0, 38.34),
        (9.0, 14100, 78.7, 38.07),
        (10.0, 13200, 77.2, 37.76),
        (12.0, 11200, 74.0, 37.06),
        (14.0, 9000, 70.8, 36.24),
        (16.0, 6900, 67.5, 35.37),
        (18.0, 5400, 64.1, 34.16),
        (20.0, 4300, 60.5, 32.88),
        (22.0, 3400, 56.8, 31.42),
        (24.0, 2700, 52.9, 29.74),
        (26.0, 2100, 48.8, 27.80),
        (28.0, 1600, 44.3, 25.55),
        (30.0, 1200, 39.4, 22.88),
    ]),
    44.50: (3, 37.2, 79.5, [
        (10.0, 9900, 79.5, 44.22),
        (12.0, 9100, 76.8, 43.63),
        (14.0, 8100, 74.1, 42.94),
        (16.0, 7200, 71.4, 42.13),
        (18.0, 5700, 68.5, 41.21),
        (20.0, 4600, 65.6, 40.16),
        (22.0, 3700, 62.6, 38.98),
        (24.0, 3000, 59.6, 37.65),
        (26.0, 2400, 56.4, 36.15),
        (28.0, 1900, 53.0, 34.47),
        (30.0, 1500, 49.5, 32.57),
        (32.0, 1200, 45.7, 30.41),
        (34.0, 800, 41.6, 27.93),
        (36.0, 600, 37.2, 25.03),
    ]),
}

NOTE = "支腿全伸，侧方/后方作业；配重4t；额定值含吊钩吊具"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    capacity_path = OUT / "QY70K-1.capacity.csv"
    total = 0
    with capacity_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["boom_len_m", "radius_m", "rated_load_t", "boom_angle_deg",
             "boom_max_angle_deg", "boom_min_angle_deg",
             "lift_height_m", "parts_of_line", "source_page", "note"]
        )
        for boom in sorted(DATA):
            parts, min_angle, max_angle, rows = DATA[boom]
            for radius, kg, angle, height in rows:
                writer.writerow(
                    [f"{boom:g}", f"{radius:g}", f"{kg / 1000:g}", f"{angle:g}",
                     f"{max_angle:g}", f"{min_angle:g}", f"{height:g}", parts, PAGE, NOTE]
                )
                total += 1

    models_path = OUT / "models.csv"
    with models_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["model", "brand", "tonnage_class_t", "crane_type", "counterweight_t",
             "hook_main_t", "hook_aux_t", "max_outrigger_reaction_kN", "self_weight_t",
             "source_doc", "source_page"]
        )
        writer.writerow(["QY70K-1", "徐工", "70", "truck", "4.0",
                         "0.616", "0.370", "625.0", "",
                         "徐工70~500吨汽车吊参数表.pdf", PAGE])

    print(f"已写入 {capacity_path.name}：{total} 行（含起升高度）")
    print(f"已写入 {models_path.name}")

    problems: list[str] = []
    for boom in sorted(DATA):
        parts, min_angle, max_angle, rows = DATA[boom]
        first, last = rows[0], rows[-1]
        if abs(first[2] - max_angle) > 1e-9:
            problems.append(f"{boom:g} m 臂：首行仰角 {first[2]} ≠ 表头最大 {max_angle}")
        if abs(last[2] - min_angle) > 1e-9:
            problems.append(f"{boom:g} m 臂：末行仰角 {last[2]} ≠ 表头最小 {min_angle}")

        loads = [row[1] for row in rows]
        if loads != sorted(loads, reverse=True):
            problems.append(f"{boom:g} m 臂：起重量非单调不增")
        heights = [row[3] for row in rows]
        if heights != sorted(heights, reverse=True):
            problems.append(f"{boom:g} m 臂：起升高度非单调不增")
        angles = [row[2] for row in rows]
        if angles != sorted(angles, reverse=True):
            problems.append(f"{boom:g} m 臂：仰角非单调不增")
        radii = [row[0] for row in rows]
        if radii != sorted(radii):
            problems.append(f"{boom:g} m 臂：幅度非递增")

        for radius, _kg, angle, height in rows:
            delta = height - boom * math.sin(math.radians(angle))
            if not (-2.5 <= delta <= 1.5):
                problems.append(
                    f"{boom:g} m / {radius:g} m：起升高度 {height} 与臂长×sin仰角 偏差 {delta:+.2f} m，疑似抄错"
                )

    if problems:
        print("自检未通过：")
        for item in problems:
            print("  ✗", item)
        raise SystemExit(1)

    print("自检通过：单调性、首末仰角、起升高度几何一致性（77 格）")


if __name__ == "__main__":
    main()
