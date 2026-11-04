@echo off
REM Build the React dashboard and package it into backend\static_dash, where the backend serves it at "/" and "/field".
REM Run after changing anything under dashboard\ :   scripts\build-ui.bat
REM (Windows twin of scripts\package-dashboard.sh. It calls npm.cmd, so PowerShell's script policy does not matter.)
setlocal
set "PATH=%ProgramFiles%\nodejs;%PATH%"
pushd "%~dp0..\dashboard" || (echo [x] dashboard folder not found & exit /b 1)
where npm.cmd >nul 2>&1 || (echo [x] Node.js not found. Install it from https://nodejs.org and retry. & popd & exit /b 1)
if not exist node_modules (
  echo Installing dashboard dependencies, first run only...
  call npm.cmd ci || (echo [x] npm ci failed & popd & exit /b 1)
)
call npm.cmd run build || (echo [x] vite build failed & popd & exit /b 1)
set "DEST=%~dp0..\backend\static_dash"
if exist "%DEST%" rmdir /s /q "%DEST%"
xcopy /e /i /q /y dist "%DEST%" >nul || (echo [x] could not copy dist to backend\static_dash & popd & exit /b 1)
popd
echo.
echo UI packaged into backend\static_dash. Start the demo with scripts\start_demo.bat
exit /b 0
