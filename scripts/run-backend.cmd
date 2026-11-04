@echo off
REM Run only the backend (it also serves the built dashboard and /field). Same as scripts\start_demo.bat without the checks.
cd /d "%~dp0..\backend"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
