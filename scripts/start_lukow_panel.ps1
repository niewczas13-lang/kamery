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
$PidDir = Join-Path $Root "runtime\pids"
$PanelLogDir = Join-Path $Root "runtime\logs\panel"
New-Item -ItemType Directory -Force -Path $PidDir, $PanelLogDir | Out-Null

function Start-LukowHiddenProcess {
    param(
        [string]$Name,
        [string]$PidFileName,
        [string]$ScriptPath,
        [string]$WorkingDirectory
    )
    $stdoutPath = Join-Path $PanelLogDir "$Name.out.log"
    $stderrPath = Join-Path $PanelLogDir "$Name.err.log"
    $pidPath = Join-Path $PidDir $PidFileName
    if (Test-Path -LiteralPath $stdoutPath) {
        Remove-Item -LiteralPath $stdoutPath -Force
    }
    if (Test-Path -LiteralPath $stderrPath) {
        Remove-Item -LiteralPath $stderrPath -Force
    }
    $process = Start-Process powershell -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $ScriptPath
        )
    Set-Content -LiteralPath $pidPath -Encoding ASCII -Value ([string]$process.Id)
    Write-Host ("{0} uruchomiony w tle. PID={1}, logi: {2}" -f $Name, $process.Id, $stdoutPath)
}

$stopScript = Join-Path $PSScriptRoot "stop_lukow_panel.ps1"
if (Test-Path -LiteralPath $stopScript) {
    & $stopScript -SkipDocker -Quiet
}

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
    & $Python -m ezviz_panel.backend go2rtc-render-runtime --include-unstable-streams --include-diagnostic-streams
    $go2rtcReady = Test-Path -LiteralPath (Join-Path $Root "runtime\config\go2rtc\go2rtc.yaml")
}

if (-not $SkipFrigate) {
    & $Python -m ezviz_panel.backend frigate-render-runtime
}

if (-not $SkipDocker) {
    Assert-LukowCommand -Name "docker" -InstallHint "Zainstaluj i uruchom Docker Desktop."
    if ($go2rtcReady) {
        if (-not $SkipFrigate) {
            docker compose up -d --force-recreate go2rtc frigate
        } else {
            docker compose up -d --force-recreate go2rtc
            Write-Host "Frigate/NVR pominiety na jawne zyczenie (-SkipFrigate)."
            docker compose stop frigate
        }
    } else {
        Write-Host "Pominieto docker compose: brak gotowego runtime/config/go2rtc/go2rtc.yaml."
    }
}

$backendScript = Join-Path $Root "scripts\run_backend_lukow.ps1"
Start-LukowHiddenProcess -Name "backend" -PidFileName "backend.pid" -ScriptPath $backendScript -WorkingDirectory $Root

if (-not $SkipFrontend) {
    $frontendScript = Join-Path $Root "scripts\run_frontend_lukow.ps1"
    Start-LukowHiddenProcess -Name "frontend" -PidFileName "frontend.pid" -ScriptPath $frontendScript -WorkingDirectory $Root
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
if (-not $SkipFrigate) {
    Write-Host "Frigate:  http://127.0.0.1:5000"
} else {
    Write-Host "Frigate/NVR pominiety. Start pelny: START_PANEL_LUKOW.bat albo START_NVR_LUKOW.bat"
}
