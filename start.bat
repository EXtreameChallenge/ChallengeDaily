@echo off
chcp 65001 >nul 2>&1
set PYTHONHOME=
set PYTHONPATH=
set PYTHONIOENCODING=utf-8
set "SCRIPT_DIR=%~dp0"

echo Starting ChallengeDaily...

cd /d "%SCRIPT_DIR%client"
set ELECTRON_IS_DEV=0
start "" "node_modules\electron\dist\electron.exe" .
