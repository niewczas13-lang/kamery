@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_ffmpeg_lukow.ps1" %*
pause
