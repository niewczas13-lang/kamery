param(
    [switch]$IncludeDiagnosticStreams
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root

Assert-LukowCommand -Name "docker" -InstallHint "Zainstaluj i uruchom Docker Desktop."
Ensure-LukowFfmpeg -InstallIfMissing

if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-Host "Brak .venv. Uruchamiam setup bez promptu admina..."
    & (Join-Path $PSScriptRoot "setup_lukow.ps1") -NoAdminPrompt
}

$Python = Get-LukowPython -Root $Root
& $Python -m ezviz_panel.backend init-db
Ensure-LukowCameraSeed -Root $Root

if (Test-LukowSecretTemplate -Root $Root) {
    throw "secrets.local.env ma placeholdery. Uzupelnij verification codes przed testem streamow."
}

Write-Host "Renderuje runtime go2rtc..."
$renderOutput = & $Python -m ezviz_panel.backend go2rtc-render-runtime --include-unstable-streams --include-diagnostic-streams 2>&1
$renderOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    throw "Render go2rtc nie powiodl sie."
}
if (($renderOutput | Out-String) -match "Streams:\s*0") {
    throw "go2rtc wygenerowal 0 streamow. Sprawdz seed kamer i secrets.local.env."
}

Write-Host "Uruchamiam go2rtc..."
docker compose up -d --force-recreate go2rtc

$deadline = (Get-Date).AddSeconds(35)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $port = Test-NetConnection -ComputerName 127.0.0.1 -Port 8554 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($port) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Host "go2rtc nie otworzyl portu RTSP 8554. Sanitizowane logi:"
    & (Join-Path $PSScriptRoot "go2rtc_logs_sanitized.ps1") -Tail 120
    throw "go2rtc nie jest gotowy do testu."
}

if ($IncludeDiagnosticStreams) {
    & (Join-Path $PSScriptRoot "root_cause_stream_lab.ps1") -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly
} else {
    & (Join-Path $PSScriptRoot "root_cause_stream_lab.ps1") -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly -StableOnly
}
