@echo off
REM One click: build the dashboard, run the backend tests, and write the Azure App Service zip to dist\azure\.
REM It never deploys. At the end it prints the exact command to deploy the zip yourself.
REM
REM   deploy\azure\package-azure.bat                 build + test + package
REM   deploy\azure\package-azure.bat --skip-tests    build + package (use only when you just ran the tests)
setlocal
set "ROOT=%~dp0..\.."
pushd "%ROOT%" & set "ROOT=%CD%" & popd
set "PY=%ROOT%\backend\.venv\Scripts\python.exe"
set "SKIP_TESTS=0"
if /i "%~1"=="--skip-tests" set "SKIP_TESTS=1"

if not exist "%PY%" (
  echo [x] backend\.venv is missing. Create it once: cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

echo [1/3] Building the dashboard...
call "%ROOT%\scripts\build-ui.bat"
if errorlevel 1 (
  echo [x] The dashboard build failed. Nothing was packaged.
  exit /b 1
)

echo.
echo [2/3] Backend tests...
if "%SKIP_TESTS%"=="1" (
  echo     skipped
) else (
  call :tests
  if errorlevel 1 exit /b 1
)

echo.
echo [3/3] Packaging for Azure...
"%PY%" "%~dp0make_package.py"
if errorlevel 1 exit /b 1
exit /b 0

:tests
pushd "%ROOT%\backend"
"%PY%" -m pytest -q --no-header -p no:cacheprovider
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" (
  echo [x] Tests failed. Nothing was packaged.
  exit /b 1
)
exit /b 0
