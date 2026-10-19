@echo off
REM Build SadakSaarthi.exe (the double-click launcher) into the project root.
REM Uses the C# 5 compiler that ships with Windows (.NET Framework 4), so nothing has to be installed.
setlocal
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
  echo [x] The .NET Framework 4 C# compiler was not found under %WINDIR%\Microsoft.NET.
  exit /b 1
)
set "OUT=%~dp0..\..\SadakSaarthi.exe"
"%CSC%" /nologo /target:exe /optimize+ /out:"%OUT%" "%~dp0launcher\SadakSaarthi.cs"
if errorlevel 1 (
  echo [x] Build failed.
  exit /b 1
)
for %%F in ("%OUT%") do echo Built %%~fF  (%%~zF bytes)
exit /b 0
