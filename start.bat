@echo off
chcp 65001 >nul 2>&1
set PYTHONHOME=
set PYTHONPATH=
set PYTHONIOENCODING=utf-8
set "SCRIPT_DIR=%~dp0"

echo Starting ChallengeDaily...

set "CLIENT_DIR=%SCRIPT_DIR%client"
set "ELECTRON_EXE=%CLIENT_DIR%\node_modules\electron\dist\electron.exe"
set "ICON_PATH=%CLIENT_DIR%\public\icon.ico"
set "SHORTCUT_PATH=%SCRIPT_DIR%ChallengeDaily.lnk"

set ELECTRON_IS_DEV=0

powershell -NoProfile -ExecutionPolicy Bypass -Command "^&{$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut('%SHORTCUT_PATH%');$sc.TargetPath='%ELECTRON_EXE%';$sc.WorkingDirectory='%CLIENT_DIR%';$sc.Arguments='.';$sc.IconLocation='%ICON_PATH%,0';$sc.WindowStyle=1;$sc.Description='ChallengeDaily - AI 智能工作日报助手';$sc.Save()}" >nul 2>&1

start "" "%SHORTCUT_PATH%"
