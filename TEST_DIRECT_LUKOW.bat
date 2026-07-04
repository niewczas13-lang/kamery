@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\root_cause_stream_lab.ps1" -DurationSeconds 120 -OnlyDirect -AllowDirectCameraRtsp -SkipNetwork -VideoOnly
pause
