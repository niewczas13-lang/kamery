param(
    [int]$Tail = 200
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$OutputDir = Join-Path $Root "runtime\diagnostics"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputPath = Join-Path $OutputDir ("docker-{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Add-DiagnosticLine {
    param([string]$Value)
    $SafeValue = $Value -replace 'rtsp://([^:\s/]+):([^@\s]+)@', 'rtsp://$1:***@'
    Add-Content -LiteralPath $OutputPath -Encoding UTF8 -Value $SafeValue
}

function Add-Section {
    param([string]$Title)
    Add-DiagnosticLine ""
    Add-DiagnosticLine ("=== {0} ===" -f $Title)
}

function Add-CommandOutput {
    param(
        [string]$Title,
        [scriptblock]$Command
    )
    Add-Section $Title
    try {
        & $Command 2>&1 | ForEach-Object { Add-DiagnosticLine ([string]$_) }
        Add-DiagnosticLine ("ExitCode: {0}" -f $LASTEXITCODE)
    } catch {
        Add-DiagnosticLine ("ERROR: {0}" -f $_.Exception.Message)
    }
}

Add-DiagnosticLine "EZVIZ Docker diagnostics"
Add-DiagnosticLine ("Started: {0}" -f (Get-Date -Format "s"))

Add-CommandOutput "docker compose ps" { docker compose ps }
Add-CommandOutput "docker stats --no-stream" { docker stats --no-stream }

Add-Section "sanitized go2rtc logs"
$LogScript = Join-Path $PSScriptRoot "go2rtc_logs_sanitized.ps1"
if (Test-Path -LiteralPath $LogScript) {
    & $LogScript -Tail $Tail 2>&1 | ForEach-Object { Add-DiagnosticLine ([string]$_) }
} else {
    Add-DiagnosticLine "scripts/go2rtc_logs_sanitized.ps1 not found"
}

Add-Section "go2rtc health"
try {
    $Go2Rtc = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://127.0.0.1:1984/api"
    Add-DiagnosticLine ("StatusCode: {0}" -f $Go2Rtc.StatusCode)
    Add-DiagnosticLine $Go2Rtc.Content
} catch {
    Add-DiagnosticLine ("ERROR: {0}" -f $_.Exception.Message)
}

Add-Section "Frigate health"
try {
    $Frigate = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "http://127.0.0.1:5000/"
    Add-DiagnosticLine ("StatusCode: {0}" -f $Frigate.StatusCode)
    Add-DiagnosticLine $Frigate.Content
} catch {
    Add-DiagnosticLine ("ERROR: {0}" -f $_.Exception.Message)
}

Write-Host "Saved Docker diagnostics: $OutputPath"
