@echo off
REM SADAKSAARTHI local demo launcher (Windows). Run from anywhere:
REM
REM   scripts\start_demo.bat                 backend only. It serves the built dashboard and /field at http://127.0.0.1:8000/
REM                                           (one process, one port, no Node needed). Build the UI once: scripts\build-ui.bat
REM   scripts\start_demo.bat dev             also start the Vite dev server (http://127.0.0.1:5173/) for editing the dashboard
REM   scripts\start_demo.bat camera          also start the AI camera on webcam 0
REM   scripts\start_demo.bat camera clip.mp4 ... or on a video file
REM
REM It checks the setup first, reuses a backend that is already running, waits until the server answers, then opens the browser.
setlocal EnableExtensions
set "ROOT=%~dp0.."
pushd "%ROOT%" & set "ROOT=%CD%" & popd
set "PATH=%ProgramFiles%\nodejs;%PATH%"
set "DEV=0"
set "CAM=0"
set "CAMSRC=0"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="dev" (
  set "DEV=1"
) else if /i "%~1"=="camera" (
  set "CAM=1"
) else (
  set "CAM=1"
  set "CAMSRC=%~1"
)
shift
goto parse
:parsed

echo.
echo === SADAKSAARTHI local demo ===

if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo [x] backend\.venv is missing. Create it:  cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

set "UI_OK=1"
if not exist "%ROOT%\backend\static_dash\index.html" set "UI_OK=0"
if "%UI_OK%"=="0" if "%DEV%"=="0" (
  echo [x] backend\static_dash is missing, so the backend has no dashboard to serve.
  echo     Run scripts\build-ui.bat once, or start with:  scripts\start_demo.bat dev
  exit /b 1
)
if "%UI_OK%"=="1" (
  powershell -NoProfile -Command "$n=(Get-ChildItem '%ROOT%\dashboard\src','%ROOT%\dashboard\public','%ROOT%\dashboard\index.html' -Recurse -File | Sort-Object LastWriteTime | Select-Object -Last 1).LastWriteTime; $b=(Get-Item '%ROOT%\backend\static_dash\index.html').LastWriteTime; if ($n -gt $b) { exit 2 }" >nul 2>&1
  if errorlevel 2 echo [!] The packaged UI is older than the dashboard source. Run scripts\build-ui.bat to refresh it.
)

REM ---- backend ----------------------------------------------------------------
call :health 8000
if "%HEALTH%"=="200" (
  echo [ok] backend already running on :8000, reusing it.
) else (
  netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
  if not errorlevel 1 (
    echo [x] Port 8000 is taken by something that is not this backend. Close it and retry.
    exit /b 1
  )
  echo Starting backend...
  start "SADAKSAARTHI backend" /D "%ROOT%\backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
  call :wait 8000 90 /health
  if errorlevel 1 (
    echo [x] The backend did not answer within 90 s. Read the "SADAKSAARTHI backend" window for the error.
    exit /b 1
  )
  echo [ok] backend is up.
)

REM ---- dashboard dev server (optional) -----------------------------------------
set "OPEN=http://127.0.0.1:8000/"
if "%DEV%"=="1" (
  call :health 5173
  if "%HEALTH%"=="200" (
    echo [ok] dashboard dev server already running on :5173, reusing it.
  ) else (
    echo Starting dashboard dev server...
    start "SADAKSAARTHI dashboard (dev)" /D "%ROOT%\dashboard" cmd /k "npm.cmd run dev"
    call :wait 5173 60 /
    if errorlevel 1 (
      echo [x] The dev server did not answer within 60 s. Read its window for the error.
      exit /b 1
    )
    echo [ok] dashboard dev server is up.
  )
  set "OPEN=http://127.0.0.1:5173/"
)

REM ---- AI camera (optional) ----------------------------------------------------
if "%CAM%"=="1" (
  echo Starting AI camera on %CAMSRC% ...
  start "SADAKSAARTHI AI camera" /D "%ROOT%" cmd /k "set PYTHONPATH=ai&& backend\.venv\Scripts\python.exe -m urbansense_ai.run_camera --source %CAMSRC% --lat 28.6328 --lon 77.2195"
)

echo.
echo Dashboard : %OPEN%
echo Phone lens: http://127.0.0.1:8000/field
echo API docs  : http://127.0.0.1:8000/docs
echo Login     : admin@urbansense.local  (demo password: UrbanSense@2026)
echo Jury walk : docs\JURY_8MIN.md  (use the local URL above while Azure is down)
echo Close the "SADAKSAARTHI ..." windows to stop.
start "" "%OPEN%"
exit /b 0

REM ---- helpers -----------------------------------------------------------------
:health
set "HEALTH=000"
for /f %%c in ('curl.exe -s -o nul -m 3 -w "%%{http_code}" http://127.0.0.1:%1/health 2^>nul') do set "HEALTH=%%c"
exit /b 0

:wait
REM :wait <port> <seconds> <path>  -> errorlevel 1 if the port never answers 200
set /a TRIES=%2/2
:waitloop
set "CODE=000"
for /f %%c in ('curl.exe -s -o nul -m 2 -w "%%{http_code}" http://127.0.0.1:%1%3 2^>nul') do set "CODE=%%c"
if "%CODE%"=="200" exit /b 0
set /a TRIES-=1
if %TRIES% LEQ 0 exit /b 1
ping -n 3 127.0.0.1 >nul
goto waitloop
