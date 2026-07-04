param(
    [string]$Config = "cameras.local.yml",
    [string]$CameraId = "",
    [int]$Timeout = 8,
    [string]$Output = "",
    [string]$SecretsEnvFile = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

if (-not $Output) {
    if ($CameraId) {
        $Output = Join-Path "probe-results" "$CameraId.json"
    } else {
        $Output = Join-Path "probe-results" "all.json"
    }
}

if (-not $SecretsEnvFile) {
    $DefaultSecrets = "C:\Users\Pawel Z\OneDrive\Documents\kamery podgląd\config\secrets.local.env"
    if (Test-Path -LiteralPath $DefaultSecrets) {
        $SecretsEnvFile = $DefaultSecrets
    }
}

$ProbeArgs = @(
    "-m", "ezviz_panel.camera_probe",
    "run",
    "--config", $Config,
    "--timeout", "$Timeout",
    "--output", $Output
)

if ($CameraId) {
    $ProbeArgs += @("--camera-id", $CameraId)
}

if ($SecretsEnvFile) {
    $ProbeArgs += @("--secrets-env-file", $SecretsEnvFile)
}

& $Python @ProbeArgs
