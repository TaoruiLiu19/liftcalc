"""把结果 JSON 渲染成 PNG（无 CAD 时看图用）。

实际渲染在 ``liftcalc.drawing.png``；本文件只是便于直接 `python tools/render_png.py` 的入口。
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from liftcalc.core.result import ComputationResult  # noqa: E402
from liftcalc.drawing.figures import figures_for  # noqa: E402
from liftcalc.drawing.png import to_png  # noqa: E402


def main() -> None:
    result_path = pathlib.Path(sys.argv[1])
    out_dir = pathlib.Path(sys.argv[2])
    result = ComputationResult.model_validate(json.loads(result_path.read_text(encoding="utf-8")))
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, figure in enumerate(figures_for(result), start=1):
        target = to_png(figure, out_dir / f"{result_path.stem}-{index}.png")
        print("已渲染", target)


if __name__ == "__main__":
    main()
