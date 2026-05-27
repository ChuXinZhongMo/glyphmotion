@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\build_windows.ps1" %*
exit /b %ERRORLEVEL%
