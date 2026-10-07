@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 goto nopython

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto oldpython

if not exist ".venv\Scripts\python.exe" (
  echo Setting up FormDueBoard for the first time...
  python -m venv .venv
  if errorlevel 1 goto failed
)
call ".venv\Scripts\activate.bat"
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto failed
python -m formdueboard
goto end

:nopython
echo FormDueBoard needs Python 3.11 or newer, and python was not found.
echo Install it from https://www.python.org/downloads/ and then double-click this launcher again.
exit /b 1

:oldpython
echo FormDueBoard needs Python 3.11 or newer. This machine has:
python --version
echo Install a newer Python from https://www.python.org/downloads/
exit /b 1

:failed
echo FormDueBoard could not finish setup.
exit /b 1

:end
endlocal
