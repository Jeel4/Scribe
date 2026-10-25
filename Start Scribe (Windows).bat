@echo off
rem Double-click to install Scribe (first run only) and start it on Windows.
rem Needs Python 3.10-3.13 and Node.js 18+ installed.
setlocal
cd /d "%~dp0"
title Scribe
echo === Scribe ===

rem ---- find Python 3.10-3.13 -------------------------------------------
set "PY="
for %%v in (3.12 3.13 3.11 3.10) do (
  if not defined PY (
    py -%%v -c "import sys" >nul 2>nul && set "PY=py -%%v"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo ERROR: Python 3.10 to 3.13 was not found.
  echo Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  goto fail
)
echo Using: %PY%

rem ---- check Node.js ----------------------------------------------------
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js was not found. Install the LTS version from https://nodejs.org/ and run this again.
  goto fail
)

rem ---- one-time install -------------------------------------------------
if exist ".venv\Scripts\python.exe" goto venv_ok
echo --- Creating Python environment
%PY% -m venv .venv
if errorlevel 1 goto fail
:venv_ok

if exist ".venv\scribe-installed.txt" goto pip_ok
echo --- Installing Python packages (first run: 5-15 minutes)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo ERROR: installing Python packages failed. See the messages above.
  goto fail
)
echo done> ".venv\scribe-installed.txt"
:pip_ok

if exist "frontend\node_modules" goto npm_ok
echo --- Installing frontend packages
pushd frontend
call npm install
if errorlevel 1 ( popd & goto fail )
popd
:npm_ok

if exist "frontend\dist\index.html" goto build_ok
echo --- Building the frontend
pushd frontend
call npm run build
if errorlevel 1 ( popd & goto fail )
popd
:build_ok

rem ---- start --------------------------------------------------------------
set "SCRIBE_PORT=5050"
echo.
echo --- Starting Scribe at http://127.0.0.1:%SCRIBE_PORT%
echo --- The browser opens by itself when it is ready. Keep this window open; close it to stop Scribe.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 300;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%SCRIBE_PORT%/api/health | Out-Null; Start-Process 'http://127.0.0.1:%SCRIBE_PORT%'; break}catch{Start-Sleep 2}}"
cd backend
"..\.venv\Scripts\python.exe" run.py
echo.
echo Scribe stopped.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
