param(
    [int]$Tail = 200,
    [switch]$Follow,
    [string]$Service = "go2rtc",
    [string]$SecretsEnvFile = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if ($env:PYTHON -and (Get-Command $env:PYTHON -ErrorAction SilentlyContinue)) {
    $Python = $env:PYTHON
} elseif (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

if (-not $SecretsEnvFile) {
    $SecretsEnvFile = $env:EZVIZ_SECRETS_ENV_FILE
}
if (-not $SecretsEnvFile) {
    $CandidateSecrets = Join-Path $ProjectRoot "secrets.local.env"
    if (Test-Path -LiteralPath $CandidateSecrets) {
        $SecretsEnvFile = $CandidateSecrets
    }
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
