@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src"
set "PY=.venv\Scripts\python.exe"
set "PYW=.venv\Scripts\pythonw.exe"

if not exist "%PY%" (
    echo Creating the Python environment ^(first run^)...
    py -3 -m venv .venv 2>nul || python -m venv .venv || goto :nopython
)

"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" || goto :oldpython
if not exist "%PYW%" set "PYW=%PY%"

rem Runtime needs: bottle + pillow (browser mode). Native window needs pywebview (.NET).
"%PY%" -c "import bottle, PIL, liftcalc.dusk" >nul 2>&1
if errorlevel 1 (
    echo Installing runtime dependencies ^(first run needs network^)...
    "%PY%" -m pip install --no-cache-dir --disable-pip-version-check bottle pillow || goto :pipfail
)

start "" "%PYW%" -m liftcalc.dusk
exit /b 0

:nopython
echo.
echo Python 3.12+ was not found.
echo Install it from https://www.python.org/ and run this file again.
pause
exit /b 1

:oldpython
echo.
echo This workbench needs Python 3.12 or newer.
echo Delete the .venv folder and run this file again.
pause
exit /b 1

:pipfail
echo.
echo Dependency installation failed. Check the network, then run:
echo   .venv\Scripts\python.exe -m pip install --no-cache-dir bottle pillow
pause
exit /b 1
