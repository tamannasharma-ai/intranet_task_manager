@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\configure-groq.ps1"
set "setupResult=%errorlevel%"
echo.
pause
exit /b %setupResult%
