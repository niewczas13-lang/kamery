$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location (Join-Path $Root "apps\web")

npm run dev -- --host 127.0.0.1
