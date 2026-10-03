@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1" %*
if errorlevel 1 (
    echo Failed to start the application.
    echo See the error above and the logs folder for details.
    if /I not "%~1"=="-CheckOnly" pause
    exit /b 1
)
endlocal
