@echo off
setlocal
rem Gesture demo. Usage: run.bat [--live] [--preview] [--camera N]  (default = test mode, no keys sent)
rem Uses the Python virtual environment .venv inside this folder (see README "Install").
rem Keep this file ASCII-only: the project path may contain Korean and spaces.

set "APP_DIR=%~dp0"
set "PY=%APP_DIR%.venv\Scripts\python.exe"
if not exist "%PY%" goto :no_python
if not exist "%APP_DIR%models\hand_landmarker.task" goto :no_model

cd /d "%APP_DIR%"
"%PY%" "%APP_DIR%run.py" %*
exit /b %ERRORLEVEL%

:no_python
echo [ERROR] Python virtual environment not found: "%PY%"
echo Run these in this folder first (see README "Install"):
echo   py -3.14 -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
exit /b 1

:no_model
echo [ERROR] Hand model not found: "%APP_DIR%models\hand_landmarker.task"
echo Run in this folder: .venv\Scripts\python.exe download_model.py
exit /b 1
