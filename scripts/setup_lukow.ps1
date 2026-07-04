param(
    [switch]$SkipNodeInstall,
    [switch]$SkipDockerCheck,
    [switch]$NoAdminPrompt
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root

Assert-LukowCommand -Name "git" -InstallHint "Zainstaluj Git for Windows."
Assert-LukowCommand -Name "python" -InstallHint "Zainstaluj Python 3.11+ i zaznacz Add to PATH."
if (-not $SkipNodeInstall) {
    Assert-LukowCommand -Name "npm" -InstallHint "Zainstaluj Node.js LTS."
}
if (-not $SkipDockerCheck) {
    Assert-LukowCommand -Name "docker" -InstallHint "Zainstaluj Docker Desktop i uruchom go przed startem panelu."
}
Ensure-LukowFfmpeg -InstallIfMissing

if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-Host "Tworze .venv..."
    python -m venv .venv
}

$Python = Get-LukowPython -Root $Root
Write-Host "Instaluje backend Python..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -e .

if (-not $SkipNodeInstall) {
    Write-Host "Instaluje frontend..."
    Push-Location (Join-Path $Root "apps\web")
    npm install
    Pop-Location
}

Write-Host "Inicjalizuje baze..."
& $Python -m ezviz_panel.backend init-db
Ensure-LukowCameraSeed -Root $Root

if (-not $env:ADMIN_PASSWORD -and -not $NoAdminPrompt) {
    Write-Host "Ustaw haslo admina panelu lokalnego."
    $secure = Read-Host "Haslo admina" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $env:ADMIN_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

if ($env:ADMIN_PASSWORD) {
    $adminUsername = if ($env:ADMIN_USERNAME) { $env:ADMIN_USERNAME } else { "admin" }
    & $Python -m ezviz_panel.backend create-admin --username $adminUsername --password-env ADMIN_PASSWORD
} else {
    Write-Host "Pominieto tworzenie admina: ustaw ADMIN_PASSWORD w .env albo uruchom INSTALL_LUKOW.bat bez -NoAdminPrompt."
}

if (Test-LukowSecretTemplate -Root $Root) {
    Write-Host "secrets.local.env ma placeholdery. Uzupelnij verification codes przed renderem go2rtc."
} else {
    Write-Host "Renderuje go2rtc runtime..."
    & $Python -m ezviz_panel.backend go2rtc-render-runtime --include-unstable-streams --include-diagnostic-streams
}

Write-Host "Renderuje Frigate runtime..."
& $Python -m ezviz_panel.backend frigate-render-runtime

Write-Host ""
Write-Host "Setup zakonczony. Start panelu: START_PANEL_LUKOW.bat"
Write-Host "Frontend: http://127.0.0.1:5173"
Write-Host "Backend:  http://127.0.0.1:8000"
