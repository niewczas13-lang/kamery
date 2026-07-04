param(
    [int]$Tail = 200,
    [switch]$Follow,
    [string]$Service = "go2rtc",
    [string]$SecretsEnvFile = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }

if (-not $SecretsEnvFile) {
    $SecretsEnvFile = $env:EZVIZ_SECRETS_ENV_FILE
}

$DockerArgs = @("compose", "logs", "--no-color", "--tail", "$Tail")
if ($Follow) {
    $DockerArgs += "--follow"
}
$DockerArgs += $Service

$SanitizerArgs = @("-m", "ezviz_panel.backend.log_sanitizer")
if ($SecretsEnvFile) {
    $SanitizerArgs += @("--secrets-env-file", $SecretsEnvFile)
}

& docker @DockerArgs | & $Python @SanitizerArgs
