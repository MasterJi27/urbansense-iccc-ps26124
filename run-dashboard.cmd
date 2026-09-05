@echo off
cd /d "%~dp0dashboard"
set "PATH=C:\Program Files\nodejs;%PATH%"
call "%ProgramFiles%\nodejs\npm.cmd" run dev
pause
