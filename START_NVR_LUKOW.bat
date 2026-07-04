@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_lukow_panel.ps1" -WithFrigate %*
exit /b %ERRORLEVEL%
