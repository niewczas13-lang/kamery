param(
    [switch]$SkipDocker,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root

$PidDir = Join-Path $Root "runtime\pids"

function Write-LukowStopStatus {
    param([string]$Message)
    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Stop-LukowProcessTree {
    param([int]$ProcessId)

    $children = @()
    try {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    } catch {
        $children = @()
    }

    foreach ($child in $children) {
        Stop-LukowProcessTree -ProcessId ([int]$child.ProcessId)
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        Stop-Process -Id $ProcessId -Force
    }
}

function Stop-LukowRecordedProcess {
    param(
        [string]$Name,
        [string]$PidFileName
    )

    $pidPath = Join-Path $PidDir $PidFileName
    if (-not (Test-Path -LiteralPath $pidPath)) {
        Write-LukowStopStatus "${Name}: brak zapisanego PID."
        return
    }

    $rawPid = (Get-Content -LiteralPath $pidPath -Raw).Trim()
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        Remove-Item -LiteralPath $pidPath -Force
        Write-LukowStopStatus "${Name}: usunieto nieprawidlowy PID."
        return
    }

    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        Stop-LukowProcessTree -ProcessId $processId
        Write-LukowStopStatus "$Name zatrzymany. PID=$processId"
    } else {
        Write-LukowStopStatus "${Name}: proces PID=$processId juz nie dziala."
    }

    Remove-Item -LiteralPath $pidPath -Force
}

Stop-LukowRecordedProcess -Name "backend" -PidFileName "backend.pid"
Stop-LukowRecordedProcess -Name "frontend" -PidFileName "frontend.pid"

if (-not $SkipDocker) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        try {
            docker compose stop go2rtc frigate | Out-Null
            Write-LukowStopStatus "Kontenery go2rtc/frigate zatrzymane."
        } catch {
            Write-LukowStopStatus "Nie udalo sie zatrzymac kontenerow: $($_.Exception.Message)"
        }
    } else {
        Write-LukowStopStatus "Docker niedostepny, pomijam kontenery."
    }
}

Write-LukowStopStatus "Panel zatrzymany."
