@echo off
REM UrbanSense jury demo starter (Windows).
REM Opens backend, dashboard, and AI camera each in its own window.
REM Run from the repo root:  scripts\start_demo.bat
REM Camera source defaults to webcam (0). Pass a video file as %1 to use it instead.
setlocal
set ROOT=%~dp0..
set CAMSRC=%1
if "%CAMSRC%"=="" set CAMSRC=0

start "UrbanSense backend" cmd /k "cd /d %ROOT%\backend && .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
timeout /t 6 >nul
start "UrbanSense dashboard" cmd /k "cd /d %ROOT%\dashboard && C:\Progra~1\nodejs\npm.cmd run dev"
start "UrbanSense AI camera" cmd /k "cd /d %ROOT% && set PYTHONPATH=ai && backend\.venv\Scripts\python.exe -m urbansense_ai.run_camera --source %CAMSRC% --lat 28.6328 --lon 77.2195"

echo Backend : http://127.0.0.1:8000/docs  (admin@urbansense.local / UrbanSense@2026)
echo Dashboard will print its URL (usually http://localhost:5173)
endlocal
