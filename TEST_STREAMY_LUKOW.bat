@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test_streamy_lukow.ps1" %*
pause
