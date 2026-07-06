@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\scan_nvr_lukow.ps1" %*
pause
