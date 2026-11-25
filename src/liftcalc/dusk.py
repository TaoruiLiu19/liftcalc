"""Single-crane workbench host.

三种跑法，同一套界面（``dusk_static``）：

* **原生窗口**：pywebview + WebView2（需要 pythonnet 能托管 .NET）。默认（auto）
  只要 ``import clr`` 能过就用它。
* **独立窗口（默认回退）**：起一个只监听 127.0.0.1 的小服务，用 Edge/Chrome 的
  ``--app=URL`` 打开。没有地址栏和标签页，观感接近桌面窗口，但不依赖 .NET。
* **浏览器标签页**：同一个服务，用默认浏览器打开。

浏览器模式下，前端的 ``window.pywebview.api`` 由注入的 fetch 桥接实现，导出走
``/download/<token>/<fmt>``；原生窗口直接用 pywebview 的 js_api。

环境变量：
    LIFTCALC_UI=auto|app|browser|native   选跑法（默认 auto）
    LIFTCALC_NO_BROWSER=1            只起服务、不开窗口（调接口/排查用）
    LIFTCALC_LOG=<path>              致命错误日志路径
"""
from __future__ import annotations

import base64
import contextlib
import json
import os
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
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

UI_ENV = "LIFTCALC_UI"
FORMATS = ("dxf", "svg", "png", "docx")


def _log_path() -> Path:
    raw = os.environ.get("LIFTCALC_LOG")
    if raw:
        return Path(raw)
    return Path(tempfile.gettempdir()) / "liftcalc-error.log"


def _say(text: str) -> None:
    """pythonw 下没有控制台，print 不能把启动流程带崩。"""
    with contextlib.suppress(Exception):
        print(text, flush=True)


def _report_fatal(exc: BaseException, title: str = "Liftcalc 启动失败", note: str = "") -> None:
    """无控制台时也要让用户看到错误：写日志 + 弹窗。"""
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log = _log_path()
    try:
        log.write_text(detail, encoding="utf-8")
        tail = f"\n\n详细信息已写入：{log}"
    except OSError:
        tail = ""
    message = f"{type(exc).__name__}: {exc}{tail}"
    if note:
        message = f"{note}\n\n{message}"
    try:
        import ctypes

        # MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST：别让弹窗躲在别的窗口后面
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10 | 0x10000 | 0x40000)
    except Exception:  # pragma: no cover - 非 Windows 或没有 user32
        print(message)


class DesktopApi:
    def __init__(self, repo: Repo):
        self._repo = repo
        self._window = None
        self._lock = RLock()
        self._snapshot = None
        self._transfer_sheets = {}

    def models(self):
        return self._repo.workbench_models()

    def calculate(self, case):
        if case.get("kind") == "rail.transfer":
            from liftcalc.crane.transfer import DUAL_LIMIT, RouteTooLong, Transfer, TransferSearchError, plan_transfer
            from liftcalc.drawing.transfer import sheets

            inputs = Transfer.model_validate(case["transfer"])
            try:
                inputs, result = plan_transfer(inputs, self._repo, diagnostics=True)
            except (TransferSearchError, RouteTooLong) as exc:
                with self._lock:
                    self._transfer_sheets = {}
                return {"status": "unplanned", "summary": str(exc),
                        "reasons": list(exc.reasons) if isinstance(exc, TransferSearchError) else []}
            drawings = sheets(inputs, result)
            tokens = [uuid.uuid4().hex for _ in drawings]
            previews = [dict(id=token, title=sheet.title, kind=sheet.meta["kind"], svg=to_svg(sheet, margin=0))
                        for token, sheet in zip(tokens, drawings, strict=True)]
            with self._lock:
                self._transfer_sheets = dict(zip(tokens, drawings, strict=True))
            return {**result, "status": "planned", "poses": inputs.route,
                    "required_clearance": inputs.plan_clearance, "load_limit": DUAL_LIMIT,
                    "stations": [dict(center=c.center, heading=c.heading) for c in inputs.cranes],
                    "drawings": previews}
        if case.get("kind") != "crane.capability" or case.get("mode", "single") != "single":
            raise ValueError("此工作台仅支持单机")
        if not 0 < float(case.get("limit", .9)) <= 1 or not float(case["payload"]) > 0:
            raise ValueError("吊物质量须为正，负荷率上限须在 (0, 1] 内")
        result = run_case(case, self._repo)
        sheet = elevation_figure(result)
        token = uuid.uuid4().hex
        with self._lock:
            self._snapshot = token, result, sheet
        return {"id": token, "cap": result.aux["capability"], "warnings": result.warnings,
                "load": result.aux.get("load"),
                "svg": to_svg(sheet, margin=0) if sheet else None,
                "scale": sheet.meta["scale_denom"] if sheet else None}

    def _get(self, token):
        with self._lock:
            if token in self._transfer_sheets:
                return None, self._transfer_sheets[token]
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

    def render(self, token: str, fmt: str) -> tuple[bytes, str]:
        """导出文件的字节内容（原生保存对话框和浏览器下载共用）。"""
        result, sheet = self._get(token)
        if fmt not in FORMATS or (result is None and fmt == "docx") or (not sheet and fmt != "docx"):
            raise ValueError("不支持该导出")
        name = f"liftcalc-{token[:8]}.{fmt}"
        if fmt == "docx":
            with TemporaryDirectory() as tmp:
                path = render_report(result, Path(tmp) / "result.docx")
                return path.read_bytes(), name
        if fmt == "svg":
            return to_svg(sheet, margin=0).encode("utf-8"), name
        if fmt == "dxf":
            with TemporaryDirectory() as tmp:
                path = to_dxf(sheet, Path(tmp) / "result.dxf")
                return path.read_bytes(), name
        from liftcalc.drawing.png import to_png

        with TemporaryDirectory() as tmp:
            path = to_png(sheet, Path(tmp) / "result.png")
            return path.read_bytes(), name

    def export(self, token, fmt):
        import webview

        data, name = self.render(token, fmt)
        dest = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=name, file_types=(f"{fmt.upper()} (*.{fmt})",)
        )
        if not dest:
            return False
        path = Path(dest if isinstance(dest, str) else dest[0])
        path.write_bytes(data)
        return True


class BrowserApi(DesktopApi):
    """浏览器模式：保存改由下载路由完成，这里只校验。"""

    def export(self, token, fmt):
        self._get(token)
        if fmt not in FORMATS:
            raise ValueError("不支持该导出")
        return True


# ===========================================================================
# 原生窗口
# ===========================================================================
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


_NETFX_CONFIG = """<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <startup useLegacyV2RuntimeActivationPolicy="true">
    <supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.8"/>
  </startup>
  <runtime>
    <loadFromRemoteSources enabled="true"/>
  </runtime>
</configuration>
"""


def _ensure_netfx_config() -> bool:
    """给真正承载 CLR 的 python.exe / pythonw.exe 补一个 host 配置。

    .NET Framework 把「非 ASCII 路径」上的程序集当成网络位置，`Assembly.LoadFrom`
    直接抛 `NotSupportedException (0x80131515)`。pythonnet 用 LoadFrom 加载
    `Python.Runtime.dll`、pywebview 用 AddReference(绝对路径) 加载 WebView2 的
    DLL，所以中文项目路径下原生窗口必然起不来。host 配置里打开
    `loadFromRemoteSources` 即可，不用搬家、也不用改代码。
    """
    targets = {
        Path(sys.base_prefix) / "python.exe",
        Path(sys.base_prefix) / "pythonw.exe",
        Path(sys.executable),
        Path(sys.executable).with_name("pythonw.exe"),
    }
    ready = False
    for exe in targets:
        if not exe.is_file():
            continue
        cfg = exe.parent / (exe.name + ".config")
        try:
            if cfg.is_file():
                text = cfg.read_text(encoding="utf-8", errors="replace")
                if "loadFromRemoteSources" in text:
                    ready = True
                continue          # 已有别的配置就绝不覆盖
            cfg.write_text(_NETFX_CONFIG, encoding="utf-8")
            ready = True
        except OSError:
            continue
    return ready


def _ascii_package_host() -> Path | None:
    """找一个纯 ASCII、可写的目录放 pythonnet 的副本。"""
    bases: list[str] = []
    override = os.environ.get("LIFTCALC_ASCII_DIR")
    if override:
        bases.append(override)
    for key in ("PUBLIC", "PROGRAMDATA"):
        raw = os.environ.get(key)
        if raw:
            bases.append(os.path.join(raw, "liftcalc"))
    bases.append(r"C:\Windows\Temp\liftcalc")
    for base in bases:
        candidate = Path(base)
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            continue
    return None


def _prepare_dotnet_package() -> bool:
    """把 pythonnet 包放到纯 ASCII 路径，再让 `import pythonnet` 命中副本。

    .NET Framework 会把「非 ASCII 路径」上的程序集当成网络位置，`Assembly.LoadFrom`
    直接抛 `NotSupportedException (0x80131515)`——pythonnet 正是这样加载
    `Python.Runtime.dll` 的，所以中文项目路径下 `import clr` 必然失败。
    复制一份到 `%PUBLIC%\\liftcalc\\pythonnet` 即可绕开，不用改系统 Python 配置。
    """
    try:
        import importlib.util
        import shutil

        host = _ascii_package_host()
        if host is None:
            return False
        moved = False
        for package in ("pythonnet", "webview"):
            spec = importlib.util.find_spec(package)
            if spec is None or not spec.origin:
                continue
            source = Path(spec.origin).parent
            if str(source).isascii():
                continue
            target = host / package

            def stamp(folder: Path) -> tuple[int, int]:
                try:
                    return ((folder / "__init__.py").stat().st_mtime_ns,
                            sum(1 for _ in folder.rglob("*")))
                except OSError:
                    return (0, 0)

            if stamp(source) != stamp(target):
                shutil.copytree(source, target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__"))
            moved = True
        if moved:
            sys.path.insert(0, str(host))
        return moved
    except Exception:
        return False


def _prepare_native_runtime() -> None:
    # pythonnet 3.0.x 默认只按名字找 python3xx.dll；PATH 里没有就用显式路径
    dll = Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
    if dll.is_file():
        os.environ.setdefault("PYTHONNET_PYDLL", str(dll))
    if not _ensure_netfx_config():
        # 写不了 host 配置就退回「把包复制到 ASCII 路径」
        _prepare_dotnet_package()



def _native_ready() -> bool:
    """真机能托管 .NET 才走 pywebview：`import clr` 就是最直接的探针。"""
    _prepare_native_runtime()
    try:
        import clr  # noqa: F401
        import webview  # noqa: F401
    except Exception:
        return False
    return True


def _init_pythonnet() -> bool:
    """手动把 Python.Runtime 初始化到指定 DLL。

    pythonnet 3.x 的 `load()` 给 `Loader.Initialize` 传空串，于是 `Runtime.PythonDLL`
    被置空，只能靠「枚举进程模块」找 python312.dll；枚举要打开自身进程句柄，在受限
    令牌下会被拒绝。这里把 DLL 路径直接传进去，走 LoadLibrary 精确加载。
    """
    try:
        import clr_loader
        import pythonnet

        dll = Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.dll"
        if not dll.is_file():
            return False
        runtime = clr_loader.get_netfx()
        pythonnet.set_runtime(runtime)
        assembly = runtime.get_assembly(
            str(Path(pythonnet.__file__).parent / "runtime" / "Python.Runtime.dll")
        )
        initialize = assembly.get_function("Python.Runtime.Loader.Initialize")
        if initialize(str(dll).encode("utf-8")) != 0:
            return False
        pythonnet._LOADED = True
        pythonnet._LOADER_ASSEMBLY = assembly
        return True
    except Exception:
        return False


def _run_native(repo: Repo) -> None:
    """在**当前进程**里开 pywebview 原生窗口。

    pythonnet 在受限令牌下可能拿不到自身进程句柄（枚举模块那一步会被拒绝），
    所以先按常规 import clr，失败再用手动初始化把 Python DLL 路径直接交给
    Loader.Initialize，绕开模块枚举。
    """
    _prepare_native_runtime()
    try:
        import clr  # noqa: F401
    except Exception as normal_error:
        if not _init_pythonnet():
            raise normal_error from None
    import webview

    api = DesktopApi(repo)
    api._window = webview.create_window(
        "Liftcalc · 单机吊装工作台", resources(), js_api=api,
        maximized=True, width=1400, height=900, min_size=(1000, 650), background_color="#1b1d24",
    )
    storage = os.environ.get("LIFTCALC_WEBVIEW2_DATA") or str(_app_profile().parent / "webview2")

    def guard() -> None:
        """WebView2 起不来时 pywebview 可能一直挂着。

        到点还没显示，就在这个进程里直接把浏览器服务 + 独立窗口拉起来：主线程继续
        卡在 pywebview 循环里也不影响用，总比"点了没反应"强。
        """
        time.sleep(35)
        shown = False
        with contextlib.suppress(Exception):
            shown = bool(webview.windows) and webview.windows[0].events.shown.is_set()
        if shown:
            return
        with contextlib.suppress(OSError):
            _log_path().write_text(
                "原生窗口 35 秒内未显示（WebView2 初始化失败或不可用），改用独立窗口。",
                encoding="utf-8",
            )
        _run_browser(repo, window="app")

    threading.Thread(target=guard, daemon=True).start()
    webview.start(gui="edgechromium", storage_path=storage)


def _temp_base() -> str | None:
    """挑一个真能写的临时目录；都不行就交给 tempfile 自己选。"""
    for key in ("TEMP", "TMP", "LOCALAPPDATA"):
        raw = os.environ.get(key)
        if not raw:
            continue
        base = Path(raw)
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / f".liftcalc-write-{os.getpid()}"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return str(base)
        except OSError:
            continue
    return None


def _app_profile() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "liftcalc" / "app-window"
    try:
        base.mkdir(parents=True, exist_ok=True)
        probe = base / ".probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return base
    except OSError:
        fallback = Path(_temp_base() or tempfile.gettempdir()) / "liftcalc-app-window"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _find_chromium() -> Path | None:
    """Edge / Chrome 的 --app 模式：无地址栏的独立窗口，不依赖 .NET。"""
    roots = [
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    candidates = []
    for root in roots:
        if not root:
            continue
        candidates += [
            Path(root) / "Microsoft/Edge/Application/msedge.exe",
            Path(root) / "Google/Chrome/Application/chrome.exe",
        ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _open_app_window(url: str) -> bool:
    """用 Chromium 的 --app 起一个独立窗口；没有 Chromium 就返回 False。"""
    browser = _find_chromium()
    if browser is None:
        return False
    profile = _app_profile()
    args = [
        str(browser),
        f"--app={url}",
        "--window-size=1440,960",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate,msEdgeSidebarV2",
        f"--user-data-dir={profile}",
    ]
    try:
        import subprocess

        subprocess.Popen(args, close_fds=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


_BROWSER_BRIDGE = """
<script>
/* 浏览器模式：把 window.pywebview.api 桥到本机 HTTP 接口（由 liftcalc.dusk 注入） */
window.__LIFTCALC_BROWSER__ = true;
(function () {
  async function request(url, body) {
    const options = body === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
    const res = await fetch(url, options);
    const text = await res.text();
    let data;
    try { data = JSON.parse(text); } catch (e) { data = { error: text }; }
    if (!res.ok) throw new Error((data && data.error) || res.statusText || "请求失败");
    return data;
  }
  window.pywebview = { api: {
    models: () => request("/api/models"),
    calculate: (input) => request("/api/calculate", input),
    dxf: async (id) => (await request("/api/dxf", { id })).data,
    export: async (id, fmt) => {
      const info = await request("/api/export", { id, fmt });
      const link = document.createElement("a");
      link.href = info.url;
      link.download = "";
      document.body.appendChild(link);
      link.click();
      link.remove();
      return true;
    },
  }};
  const ping = () => fetch("/api/ping").catch(() => {});
  ping();
  setInterval(ping, 4000);
})();
</script>
"""


def _browser_app(api: BrowserApi, watchdog: _Watchdog):  # pragma: no cover - 需要 bottle
    from bottle import Bottle, HTTPResponse, request, response, static_file

    app = Bottle()
    root = Path(__file__).with_name("dusk_static")

    def index_html() -> str:
        html = (root / "index.html").read_text(encoding="utf-8")
        return html.replace("</body>", f"{_BROWSER_BRIDGE}</body>")

    def fail(exc: Exception):
        response.status = 400
        response.content_type = "application/json"
        return json.dumps({"error": str(exc)}, ensure_ascii=False)

    @app.get("/")
    @app.get("/index.html")
    def index():
        response.content_type = "text/html; charset=utf-8"
        return index_html()

    @app.get("/assets/<name:path>")
    def asset(name):
        return static_file(name, root=str(root / "assets"))

    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"

    @app.get("/fonts/fonts.json")
    def font_catalog():
        response.content_type = "application/json"
        if not (fonts / "simhei.ttf").exists():
            return "[]"
        return json.dumps([{"name": ["simhei", "simsun", "hztxt", "txt", "simplex",
                                     "arial", "standard", "amgdt"],
                            "type": "mesh", "file": "simhei.ttf"}])

    @app.get("/fonts/simhei.ttf")
    def font_file():
        return static_file("simhei.ttf", root=str(fonts))

    @app.get("/api/ping")
    def ping():
        watchdog.ping()
        response.content_type = "application/json"
        return '{"ok": true}'

    @app.get("/api/models")
    def models():
        watchdog.ping()
        return json.dumps(api.models(), ensure_ascii=False)

    @app.post("/api/calculate")
    def calculate():
        watchdog.ping()
        try:
            payload = request.json or {}
            response.content_type = "application/json"
            return json.dumps(api.calculate(payload), ensure_ascii=False)
        except Exception as exc:
            return fail(exc)

    @app.post("/api/dxf")
    def dxf():
        watchdog.ping()
        try:
            token = (request.json or {}).get("id", "")
            return json.dumps({"data": api.dxf(token)})
        except Exception as exc:
            return fail(exc)

    @app.post("/api/export")
    def export():
        watchdog.ping()
        try:
            body = request.json or {}
            token, fmt = body.get("id", ""), body.get("fmt", "")
            api.export(token, fmt)
            return json.dumps({"url": f"/download/{token}/{fmt}"})
        except Exception as exc:
            return fail(exc)

    @app.get("/download/<token>/<fmt>")
    def download(token, fmt):
        watchdog.ping()
        try:
            data, name = api.render(token, fmt)
        except Exception as exc:
            return fail(exc)
        return HTTPResponse(
            body=data,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
            },
        )

    return app


class _Watchdog:
    """页面关掉后自动退出：只靠页面心跳，不再占着端口。"""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout
        self.last = time.monotonic()
        self.seen = False
        self._lock = threading.Lock()

    def ping(self) -> None:
        with self._lock:
            self.last = time.monotonic()
            self.seen = True

    def watch(self) -> None:  # pragma: no cover - 后台线程
        while True:
            time.sleep(5.0)
            with self._lock:
                idle = time.monotonic() - self.last
                seen = self.seen
            if seen and idle > self.timeout:
                os._exit(0)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_browser(repo: Repo, notice: tuple[BaseException, str, str] | None = None,
                 window: str = "app") -> None:  # pragma: no cover
    from wsgiref.simple_server import WSGIRequestHandler, make_server

    if not (Path(__file__).with_name("dusk_static") / "index.html").is_file():
        raise SystemExit("缺少桌面 UI：请在 frontend 目录执行 pnpm install --frozen-lockfile 和 pnpm run build")

    api = BrowserApi(repo)
    watchdog = _Watchdog()
    app = _browser_app(api, watchdog)
    port = _free_port()

    class _Quiet(WSGIRequestHandler):
        def log_message(self, *args):  # 不刷屏
            pass

    server = make_server("127.0.0.1", port, app, handler_class=_Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=watchdog.watch, daemon=True).start()

    url = f"http://127.0.0.1:{port}/"
    with contextlib.suppress(OSError):
        _log_path().with_name("liftcalc-url.txt").write_text(url, encoding="utf-8")

    opened = False
    if os.environ.get("LIFTCALC_NO_BROWSER") == "1":
        _say("（LIFTCALC_NO_BROWSER=1：不自动打开窗口）")
        opened = True
    elif window == "app" and _open_app_window(url):
        _say(f"Liftcalc 工作台窗口已打开：{url}")
        opened = True
    elif webbrowser.open(url):
        _say(f"Liftcalc 工作台已在浏览器打开：{url}")
        opened = True
    if not opened:
        _report_fatal(RuntimeError(f"打不开浏览器窗口，请手动访问 {url}"))
    _say("关闭窗口后约 1 分钟自动退出。")
    if notice is not None:
        # 界面已经在浏览器里跑起来了，提示只作说明，不挡着用
        threading.Thread(target=_report_fatal, args=notice, daemon=True).start()
    while True:
        time.sleep(3600)


# ===========================================================================
# 入口
# ===========================================================================
def main() -> None:
    mode = os.environ.get(UI_ENV, "auto").lower()
    if not (Path(__file__).with_name("dusk_static") / "index.html").is_file():
        _report_fatal(
            RuntimeError("缺少桌面 UI（dusk_static/index.html）。请在 frontend 目录执行 pnpm run build。")
        )
        raise SystemExit(1)

    with TemporaryDirectory(prefix="liftcalc-", dir=_temp_base()) as directory:
        db = Path(directory) / "catalog.sqlite"
        build_db(Path(__file__).parent / "data/pack", db, "bundled")
        repo = Repo(db)

        if mode in ("auto", "native"):
            try:
                _run_native(repo)
                return
            except Exception as exc:
                # 原生窗口起不来也照样给一个窗口：退回 Chromium 的 --app 独立窗口
                notice = None
                if mode == "native":
                    notice = (
                        exc,
                        "Liftcalc：原生窗口不可用，已改用独立窗口",
                        "pywebview / WebView2 没能创建原生窗口，工作台已改用 Edge/Chrome 的独立窗口"
                        "（无地址栏，界面一样）。\n"
                        "只用浏览器标签页：set LIFTCALC_UI=browser。",
                    )
                else:
                    _say(f"原生窗口不可用，改用独立窗口：{type(exc).__name__}: {exc}")
                _run_browser(repo, notice, window="app")
                return
        _run_browser(repo, window="tab" if mode == "browser" else "app")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as error:  # pragma: no cover - 兜底，pythonw 下也要可见
        _report_fatal(error)
        raise
