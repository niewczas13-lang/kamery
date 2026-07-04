function Get-LukowProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Import-LukowDotEnv {
    param([string]$Root)
    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        return
    }
    foreach ($rawLine in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        $line = [string]$rawLine
        if (-not $line -or $line.TrimStart().StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $separator = $line.IndexOf("=")
        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim().Trim('"').Trim("'")
        if ($key) {
            Set-Item -Path "Env:$key" -Value $value
        }
    }
}

function Initialize-LukowEnvironment {
    param([string]$Root)

    $runtimeDirs = @(
        "runtime\db",
        "runtime\config\go2rtc",
        "runtime\config\frigate",
        "runtime\media\frigate",
        "runtime\cache\frigate",
        "runtime\logs\go2rtc",
        "runtime\diagnostics",
        "runtime\tmp",
        "runtime\snapshots"
    )
    foreach ($relativePath in $runtimeDirs) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root $relativePath) | Out-Null
    }

    $envPath = Join-Path $Root ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        $secret = "local-" + ([guid]::NewGuid().ToString("N"))
        $secretsPath = Join-Path $Root "secrets.local.env"
        $envLines = @(
            "APP_ENV=local",
            "DATABASE_URL=sqlite:///runtime/db/ezviz-panel.db",
            "EZVIZ_BACKEND_SECRET_KEY=$secret",
            "EZVIZ_SECRETS_ENV_FILE=$secretsPath",
            "ACCESS_TOKEN_EXPIRE_MINUTES=720",
            "ADMIN_USERNAME=admin",
            "FFMPEG_BIN=ffmpeg"
        )
        Set-Content -LiteralPath $envPath -Encoding UTF8 -Value ($envLines -join "`r`n")
        Write-Host "Utworzono lokalny .env"
    }

    $localSecrets = Join-Path $Root "secrets.local.env"
    $secretExample = Join-Path $Root "secrets.local.example.env"
    if (-not (Test-Path -LiteralPath $localSecrets) -and (Test-Path -LiteralPath $secretExample)) {
        Copy-Item -LiteralPath $secretExample -Destination $localSecrets
        Write-Host "Utworzono secrets.local.env z template. Uzupelnij verification codes przed live testami."
    }

    $localCameras = Join-Path $Root "cameras.local.yml"
    $cameraExample = Join-Path $Root "cameras.example.yml"
    if (-not (Test-Path -LiteralPath $localCameras) -and (Test-Path -LiteralPath $cameraExample)) {
        Copy-Item -LiteralPath $cameraExample -Destination $localCameras
        Write-Host "Utworzono cameras.local.yml z template. Dostosuj hosty kamer do LAN w Lukowie."
    }

    Import-LukowDotEnv -Root $Root
    $env:PYTHONPATH = "src"
}

function Get-LukowPython {
    param([string]$Root)
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }
    return "python"
}

function Update-LukowProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $paths = @()
    if ($machinePath) {
        $paths += $machinePath
    }
    if ($userPath) {
        $paths += $userPath
    }
    if ($paths.Count) {
        $env:Path = ($paths -join ";")
    }
}

function Find-LukowFfmpeg {
    Update-LukowProcessPath
    $command = Get-Command "ffmpeg" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidatePatterns = @()
    if ($env:LOCALAPPDATA) {
        $candidatePatterns += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*\bin\ffmpeg.exe")
        $candidatePatterns += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Gyan.FFmpeg_*\*\bin\ffmpeg.exe")
    }
    if ($env:ProgramFiles) {
        $candidatePatterns += (Join-Path $env:ProgramFiles "ffmpeg\bin\ffmpeg.exe")
        $candidatePatterns += (Join-Path $env:ProgramFiles "Gyan\FFmpeg\bin\ffmpeg.exe")
        $candidatePatterns += (Join-Path $env:ProgramFiles "Gyan\ffmpeg\bin\ffmpeg.exe")
    }
    if (${env:ProgramFiles(x86)}) {
        $candidatePatterns += (Join-Path ${env:ProgramFiles(x86)} "ffmpeg\bin\ffmpeg.exe")
        $candidatePatterns += (Join-Path ${env:ProgramFiles(x86)} "Gyan\FFmpeg\bin\ffmpeg.exe")
        $candidatePatterns += (Join-Path ${env:ProgramFiles(x86)} "Gyan\ffmpeg\bin\ffmpeg.exe")
    }

    foreach ($pattern in $candidatePatterns) {
        $found = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }

    return $null
}

function Register-LukowFfmpegPath {
    param([string]$FfmpegPath)
    if (-not $FfmpegPath) {
        return
    }
    $binDir = Split-Path -Parent $FfmpegPath
    if (-not $binDir) {
        return
    }
    if ($env:Path -notlike "*$binDir*") {
        $env:Path = "$binDir;$env:Path"
    }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $userPath) {
        [Environment]::SetEnvironmentVariable("Path", $binDir, "User")
    } elseif ($userPath -notlike "*$binDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$binDir", "User")
    }
    $env:FFMPEG_BIN = $FfmpegPath
}

function Ensure-LukowFfmpeg {
    param([switch]$InstallIfMissing)

    $ffmpegPath = Find-LukowFfmpeg
    if ($ffmpegPath) {
        Register-LukowFfmpegPath -FfmpegPath $ffmpegPath
        Write-Host "FFmpeg OK: $ffmpegPath"
        return $ffmpegPath
    }

    if (-not $InstallIfMissing) {
        throw "ffmpeg nie jest dostepny w PATH. Zainstaluj FFmpeg albo dodaj go do PATH."
    }

    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "ffmpeg nie jest dostepny, a winget nie jest dostepny do automatycznej instalacji. Zainstaluj FFmpeg recznie: winget install --id Gyan.FFmpeg -e --source winget"
    }

    Write-Host "FFmpeg nie jest dostepny. Instaluje przez winget..."
    & $winget.Source install --id Gyan.FFmpeg -e --source winget --accept-package-agreements --accept-source-agreements

    $ffmpegPath = Find-LukowFfmpeg
    if (-not $ffmpegPath) {
        throw "FFmpeg zostal zainstalowany, ale nie jest jeszcze widoczny w tej sesji. Zamknij okno, otworz nowe PowerShell/CMD i uruchom TEST_STREAMY_LUKOW.bat ponownie."
    }

    Register-LukowFfmpegPath -FfmpegPath $ffmpegPath
    Write-Host "FFmpeg OK: $ffmpegPath"
    return $ffmpegPath
}

function Ensure-LukowCameraSeed {
    param([string]$Root)
    $python = Get-LukowPython -Root $Root
    & $python -m ezviz_panel.backend seed-lukow-cameras
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udalo sie przygotowac lokalnej listy kamer Lukow."
    }
}

function Test-LukowSecretTemplate {
    param([string]$Root)
    $localSecrets = Join-Path $Root "secrets.local.env"
    if (-not (Test-Path -LiteralPath $localSecrets)) {
        return $true
    }
    return [bool](Select-String -LiteralPath $localSecrets -Pattern "PUT_EZVIZ_VERIFICATION_CODE_HERE" -Quiet)
}

function Assert-LukowCommand {
    param(
        [string]$Name,
        [string]$InstallHint
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name nie jest dostepny w PATH. $InstallHint"
    }
}
