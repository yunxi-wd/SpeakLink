@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
"%~dp0runtime\python\python.exe" -B "%~dp0launcher.py"
if errorlevel 1 pause
endlocal
