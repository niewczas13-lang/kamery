param(
    [int]$DurationSeconds = 120,
    [switch]$VideoOnly,
    [string[]]$Streams = @(
        "lukow_h9c_98_sub",
        "lukow_h9c_98_lens2_sub",
        "lukow_c8w_97_sub",
        "lukow_c8c_60_sub",
        "lukow_c8c_60_sub_ch1"
    )
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$OutputDir = Join-Path $Root "runtime\diagnostics"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputPath = Join-Path $OutputDir ("streams-{0}.txt" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Add-DiagnosticLine {
    param([string]$Value)
    $SafeValue = $Value -replace 'rtsp://([^:\s/]+):([^@\s]+)@', 'rtsp://$1:***@'
    Add-Content -LiteralPath $OutputPath -Encoding UTF8 -Value $SafeValue
}

Add-DiagnosticLine "EZVIZ stream diagnostics"
Add-DiagnosticLine ("Started: {0}" -f (Get-Date -Format "s"))
Add-DiagnosticLine ("DurationSeconds: {0}" -f $DurationSeconds)
Add-DiagnosticLine ("VideoOnly: {0}" -f [bool]$VideoOnly)
Add-DiagnosticLine ""

foreach ($Stream in $Streams) {
    Add-DiagnosticLine ("=== {0} ===" -f $Stream)
    $InputUrl = "rtsp://127.0.0.1:8554/$Stream"
    $FfmpegArgs = @("-rtsp_transport", "tcp", "-hide_banner", "-i", $InputUrl)
    if ($VideoOnly) {
        $FfmpegArgs += @("-map", "0:v:0", "-an")
    }
    $FfmpegArgs += @("-t", [string]$DurationSeconds, "-f", "null", "-")
    Add-DiagnosticLine ("Command: ffmpeg {0}" -f ($FfmpegArgs -join " "))
    try {
        & ffmpeg @FfmpegArgs 2>&1 | ForEach-Object { Add-DiagnosticLine ([string]$_) }
        Add-DiagnosticLine ("ExitCode: {0}" -f $LASTEXITCODE)
    } catch {
        Add-DiagnosticLine ("ERROR: {0}" -f $_.Exception.Message)
    }
    Add-DiagnosticLine ""
}

Write-Host "Saved stream diagnostics: $OutputPath"
