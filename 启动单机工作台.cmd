@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
if not exist ".venv\Scripts\python.exe" (
    py -3 -m venv .venv || python -m venv .venv || goto :failed
)
".venv\Scripts\python.exe" -c "import sys, webview, bottle, PIL, liftcalc.dusk; assert sys.version_info >= (3, 12)" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" -m pip install -e ".[desktop]" || goto :failed
)
".venv\Scripts\pythonw.exe" -m liftcalc.dusk
exit /b
:failed
echo Setup failed. Check Python 3.12+ and the installation messages above.
pause
exit /b 1
