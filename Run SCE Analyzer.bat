@echo off
setlocal
cd /d "%~dp0local"

set PY=
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py

if not defined PY (
  echo.
  echo   Python was not found on this PC.
  echo   Install it from https://www.python.org/downloads/ and tick
  echo   "Add python.exe to PATH" during setup, then run this again.
  echo.
  pause
  exit /b 1
)

%PY% serve.py %*
if errorlevel 1 pause
