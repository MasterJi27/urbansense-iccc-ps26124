@echo off
REM Run the Vite dev server for the dashboard (http://127.0.0.1:5173/). It proxies /api to the backend on :8000.
cd /d "%~dp0..\dashboard"
set "PATH=%ProgramFiles%\nodejs;%PATH%"
call npm.cmd run dev
pause
