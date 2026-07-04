$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root
Ensure-LukowFfmpeg -InstallIfMissing

Write-Host ""
Write-Host "FFmpeg gotowy. Mozesz uruchomic TEST_STREAMY_LUKOW.bat."
