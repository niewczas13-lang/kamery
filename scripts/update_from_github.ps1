param(
    [string]$RepoUrl = "https://github.com/niewczas13-lang/kamery.git",
    [string]$Branch = "main",
    [switch]$RestartServices
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root
Assert-LukowCommand -Name "git" -InstallHint "Zainstaluj Git for Windows."

if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
    Write-Host "Brak .git - inicjalizuje lokalny checkout pod update z GitHuba."
    git init
    git remote add origin $RepoUrl
} else {
    $remote = git remote
    if ($remote -contains "origin") {
        git remote set-url origin $RepoUrl
    } else {
        git remote add origin $RepoUrl
    }
}

Write-Host "Pobieram $RepoUrl ($Branch)..."
git fetch origin $Branch
git checkout -B $Branch
git reset --hard "origin/$Branch"

Write-Host "Aktualizuje zaleznosci i runtime..."
& (Join-Path $PSScriptRoot "setup_lukow.ps1") -NoAdminPrompt

if ($RestartServices) {
    if (Test-Path -LiteralPath (Join-Path $Root "runtime\config\go2rtc\go2rtc.yaml")) {
        docker compose up -d go2rtc
    }
    if (Test-Path -LiteralPath (Join-Path $Root "runtime\config\frigate\config.yml")) {
        docker compose up -d frigate
    }
}

Write-Host ""
Write-Host "Update zakonczony. Start: START_PANEL_LUKOW.bat"
