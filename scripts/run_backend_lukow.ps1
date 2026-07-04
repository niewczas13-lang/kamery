$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root
$Python = Get-LukowPython -Root $Root

& $Python -m ezviz_panel.backend runserver --host 127.0.0.1 --port 8000
