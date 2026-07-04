@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop_lukow_panel.ps1" %*
exit /b %ERRORLEVEL%
