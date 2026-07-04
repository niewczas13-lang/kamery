param(
    [switch]$SkipDocker,
    [switch]$SkipFrigate,
    [switch]$WithFrigate,
    [switch]$SkipFrontend,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root

if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-Host "Brak .venv. Uruchamiam setup bez promptu admina..."
    & (Join-Path $PSScriptRoot "setup_lukow.ps1") -NoAdminPrompt
}

$Python = Get-LukowPython -Root $Root
& $Python -m ezviz_panel.backend init-db
Ensure-LukowCameraSeed -Root $Root

$go2rtcReady = $false
if (Test-LukowSecretTemplate -Root $Root) {
    Write-Host "secrets.local.env ma placeholdery. Uzupelnij verification codes i uruchom START ponownie."
} else {
    & $Python -m ezviz_panel.backend go2rtc-render-runtime
    $go2rtcReady = Test-Path -LiteralPath (Join-Path $Root "runtime\config\go2rtc\go2rtc.yaml")
}

if ($WithFrigate -and -not $SkipFrigate) {
    & $Python -m ezviz_panel.backend frigate-render-runtime
}

if (-not $SkipDocker) {
    Assert-LukowCommand -Name "docker" -InstallHint "Zainstaluj i uruchom Docker Desktop."
    if ($go2rtcReady) {
        if ($WithFrigate -and -not $SkipFrigate) {
            docker compose up -d --force-recreate go2rtc frigate
        } else {
            docker compose up -d --force-recreate go2rtc
        }
    } else {
        Write-Host "Pominieto docker compose: brak gotowego runtime/config/go2rtc/go2rtc.yaml."
    }
}

$backendScript = Join-Path $Root "scripts\run_backend_lukow.ps1"
Start-Process powershell -WorkingDirectory $Root -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $backendScript
)

if (-not $SkipFrontend) {
    $frontendScript = Join-Path $Root "scripts\run_frontend_lukow.ps1"
    Start-Process powershell -WorkingDirectory $Root -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $frontendScript
    )
}

if ($OpenBrowser) {
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:5173"
}

Write-Host ""
Write-Host "Panel startuje."
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "go2rtc:   http://127.0.0.1:1984"
if ($WithFrigate -and -not $SkipFrigate) {
    Write-Host "Frigate:  http://127.0.0.1:5000"
} else {
    Write-Host "Frigate/NVR pominiety. Start NVR: START_NVR_LUKOW.bat"
}
