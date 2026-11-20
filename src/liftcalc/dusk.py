"""Single-crane desktop host. No remote services or external browser."""
import base64
import json
import os
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

from liftcalc.data.importer import build_db
from liftcalc.data.repo import Repo
from liftcalc.drawing.dxf import to_dxf
from liftcalc.drawing.figures import elevation_figure
from liftcalc.drawing.svg import to_svg
from liftcalc.report.render import render_report
from liftcalc.services.calc import run_case


class DesktopApi:
    def __init__(self, repo):
        self._repo = repo
        self._window = None
        self._lock = RLock()
        self._snapshot = None

    def models(self):
        return self._repo.workbench_models()

    def calculate(self, case):
        if case.get("kind") != "crane.capability" or case.get("mode", "single") != "single":
            raise ValueError("此工作台仅支持单机")
        if not 0 < float(case.get("limit", .9)) <= 1 or not float(case["payload"]) > 0:
            raise ValueError("吊件重量须为正，负荷率上限须在 (0, 1] 内")
        result = run_case(case, self._repo)
        sheet = elevation_figure(result)
        token = uuid.uuid4().hex
        with self._lock:
            self._snapshot = token, result, sheet
        return {"id": token, "cap": result.aux["capability"], "warnings": result.warnings,
                "svg": to_svg(sheet, margin=0) if sheet else None,
                "scale": sheet.meta["scale_denom"] if sheet else None}

    def _get(self, token):
        with self._lock:
            if not self._snapshot or token != self._snapshot[0]:
                raise ValueError("结果已变更，请重新计算")
            return self._snapshot[1:]

    def dxf(self, token):
        _, sheet = self._get(token)
        if not sheet:
            raise ValueError("无可供核图的表档")
        with TemporaryDirectory() as tmp:
            data = to_dxf(sheet, Path(tmp) / "result.dxf").read_bytes()
        return base64.b64encode(data).decode("ascii")

    def export(self, token, fmt):
        import webview

        result, sheet = self._get(token)
        if fmt not in ("dxf", "svg", "png", "docx") or (not sheet and fmt != "docx"):
            raise ValueError("不支持该导出")
        dest = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=f"liftcalc-{token[:8]}.{fmt}",
                                               file_types=(f"{fmt.upper()} (*.{fmt})",))
        if not dest:
            return False
        path = Path(dest if isinstance(dest, str) else dest[0])
        if fmt == "docx":
            render_report(result, path)
        elif fmt == "dxf":
            to_dxf(sheet, path)
        elif fmt == "svg":
            path.write_text(to_svg(sheet, margin=0), encoding="utf-8")
        else:
            from liftcalc.drawing.png import to_png
            to_png(sheet, path)
        return True


def resources():
    from bottle import Bottle, response, static_file

    app = Bottle()
    root = Path(__file__).with_name("dusk_static")
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    @app.get("/fonts/fonts.json")
    def catalog():
        response.content_type = "application/json"
        return json.dumps([{"name": ["simhei","simsun","hztxt","txt","simplex","arial","standard","amgdt"],
                            "type":"mesh","file":"simhei.ttf"}] if (fonts/"simhei.ttf").exists() else [])
    @app.get("/fonts/simhei.ttf")
    def chinese_font():
        return static_file("simhei.ttf", root=str(fonts))
    @app.get("/")
    def index():
        return static_file("index.html", root=str(root))
    @app.get("/assets/<name:path>")
    def asset(name):
        return static_file(name, root=str(root/"assets"))
    return app


def main():
    import webview

    if not Path(__file__).with_name("dusk_static").joinpath("index.html").is_file():
        raise SystemExit("缺少桌面 UI：请在 frontend 目录执行 pnpm install --frozen-lockfile 和 pnpm run build")
    with TemporaryDirectory(prefix="liftcalc-") as directory:
        db = Path(directory) / "catalog.sqlite"
        build_db(Path(__file__).parent / "data/pack", db, "bundled")
        api = DesktopApi(Repo(db))
        api._window = webview.create_window(
            "Liftcalc · 单机吊装工作台", resources(), js_api=api,
            maximized=True, width=1400, height=900, min_size=(1000, 650), background_color="#1b1d24",
        )
        try:
            webview.start(gui="edgechromium")
        except Exception as error:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"无法启动桌面视图，请检查 Microsoft Edge WebView2 运行时。\n{error}", "Liftcalc", 16)
            raise


if __name__ == "__main__":
    main()
