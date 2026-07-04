param(
    [int]$DurationSeconds = 180,
    [int]$NetworkPingCount = 30,
    [int]$FfmpegTimeoutSeconds = 0,
    [switch]$Quick,
    [switch]$SkipDirect,
    [switch]$WithFrigate
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

if ($Quick) {
    if (-not $PSBoundParameters.ContainsKey("DurationSeconds")) {
        $DurationSeconds = 45
    }
    if (-not $PSBoundParameters.ContainsKey("NetworkPingCount")) {
        $NetworkPingCount = 10
    }
}

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportDir = Join-Path $Root "runtime\diagnostics\stability-$Stamp"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$ReportJsonPath = Join-Path $ReportDir "report.json"
$ReportMdPath = Join-Path $ReportDir "report.md"
$SequentialLogPath = Join-Path $ReportDir "go2rtc-sequential-sanitized.log"
$ParallelLogPath = Join-Path $ReportDir "go2rtc-parallel-sanitized.log"
$DirectLogPath = Join-Path $ReportDir "direct-camera-sanitized.log"
$NetworkLogPath = Join-Path $ReportDir "network.txt"
Set-Content -LiteralPath $SequentialLogPath -Encoding UTF8 -Value "go2rtc sequential logs sanitized by Stability Lukow."
Set-Content -LiteralPath $ParallelLogPath -Encoding UTF8 -Value "go2rtc parallel logs sanitized by Stability Lukow."
Set-Content -LiteralPath $DirectLogPath -Encoding UTF8 -Value "direct camera logs sanitized by Stability Lukow."

$SecretFile = $env:EZVIZ_SECRETS_ENV_FILE
if (-not $SecretFile) {
    $CandidateSecretFile = Join-Path $Root "secrets.local.env"
    if (Test-Path -LiteralPath $CandidateSecretFile) {
        $SecretFile = $CandidateSecretFile
    }
}

function Write-StabilityStatus {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

function Read-StabilitySecrets {
    param([string]$Path)
    $values = @{}
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return $values
    }
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = [string]$rawLine
        if (-not $line -or $line.TrimStart().StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $separator = $line.IndexOf("=")
        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim().Trim('"').Trim("'")
        if ($key -and $value) {
            $values[$key] = $value
        }
    }
    return $values
}

$Secrets = Read-StabilitySecrets -Path $SecretFile

function Sanitize-StabilityText {
    param([string]$Value)
    $safe = [string]$Value
    $safe = $safe -replace 'rtsp://([^:\s/]+):([^@\s]+)@', 'rtsp://$1:***@'
    foreach ($secret in $Secrets.Values) {
        if ($secret) {
            $safe = $safe.Replace([string]$secret, "***")
        }
    }
    $safe = $safe -replace '(?i)\b(verification(?:\s+code)?\s*[:=]\s*)([^\s,;''"]+)', '$1***'
    return $safe
}

function Add-StabilityLog {
    param(
        [string]$Path,
        [string]$Value
    )
    Add-Content -LiteralPath $Path -Encoding UTF8 -Value (Sanitize-StabilityText $Value)
}

function Last-RegexValue {
    param(
        [string]$Text,
        [string]$Pattern
    )
    $matches = [regex]::Matches($Text, $Pattern)
    if ($matches.Count -eq 0) {
        return $null
    }
    return $matches[$matches.Count - 1].Groups[1].Value
}

function Parse-DurationSeconds {
    param([string]$Text)
    $matches = [regex]::Matches($Text, '\btime=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)')
    if ($matches.Count -eq 0) {
        return 0.0
    }
    $m = $matches[$matches.Count - 1]
    return ([int]$m.Groups[1].Value * 3600) + ([int]$m.Groups[2].Value * 60) + ([double]$m.Groups[3].Value)
}

function Parse-FfmpegLog {
    param(
        [string]$Text,
        [int]$TargetDurationSeconds,
        [int]$ExitCode
    )
    $frameValue = Last-RegexValue -Text $Text -Pattern 'frame=\s*(\d+)'
    $fpsValue = Last-RegexValue -Text $Text -Pattern '\bfps=\s*([0-9]*\.?[0-9]+)'
    $speedValue = Last-RegexValue -Text $Text -Pattern '\bspeed=\s*([0-9]*\.?[0-9]+)x'
    $actualDuration = Parse-DurationSeconds -Text $Text
    $lower = $Text.ToLowerInvariant()
    $eofCount = ([regex]::Matches($lower, 'end of file|\beof\b')).Count
    $timeout = $lower.Contains("timeout") -or $lower.Contains("timed out") -or ($ExitCode -eq 124)
    $decodeErrors = 0
    foreach ($line in $lower -split "`r?`n") {
        if ($line.Contains("pps id out of range") -or $line.Contains("could not find ref") -or $line.Contains("skipping invalid undecodable nalu") -or $line.Contains("error while decoding") -or $line.Contains("invalid data found")) {
            $decodeErrors += 1
        }
    }
    $frames = if ($frameValue) { [int]$frameValue } else { 0 }
    $fps = if ($fpsValue) { [double]$fpsValue } else { $null }
    $speed = if ($speedValue) { [double]$speedValue } else { $null }
    $connected = $lower.Contains("input #0") -or $lower.Contains("stream #0:") -or $frames -gt 0
    $stable = ($ExitCode -eq 0) -and $connected -and ($frames -gt 0) -and ($actualDuration -ge ($TargetDurationSeconds * 0.95)) -and ($eofCount -eq 0) -and (-not $timeout)
    return [ordered]@{
        connected = [bool]$connected
        duration_target_seconds = $TargetDurationSeconds
        actual_duration_seconds = [math]::Round($actualDuration, 2)
        frames = $frames
        fps = $fps
        speed = $speed
        eof_count = $eofCount
        timeout = [bool]$timeout
        decode_error_count = $decodeErrors
        stable = [bool]$stable
        exit_code = $ExitCode
    }
}

function Get-FfmpegArgs {
    param(
        [string]$Url,
        [int]$TargetDurationSeconds
    )
    return @(
        "-rtsp_transport", "tcp",
        "-hide_banner",
        "-i", $Url,
        "-map", "0:v:0",
        "-an",
        "-t", [string]$TargetDurationSeconds,
        "-f", "null",
        "-"
    )
}

function Invoke-StabilityProbe {
    param(
        [hashtable]$Target,
        [string]$Url,
        [string]$SafeUrl,
        [string]$Kind,
        [string]$Stage,
        [string]$LogPath
    )
    $ffmpegBin = if ($env:FFMPEG_BIN) { $env:FFMPEG_BIN } else { "ffmpeg" }
    $effectiveTimeout = if ($FfmpegTimeoutSeconds -gt 0) { $FfmpegTimeoutSeconds } else { [math]::Max($DurationSeconds + 45, 60) }
    $ffmpegArgs = Get-FfmpegArgs -Url $Url -TargetDurationSeconds $DurationSeconds
    $safeArgs = Get-FfmpegArgs -Url $SafeUrl -TargetDurationSeconds $DurationSeconds
    Add-StabilityLog -Path $LogPath -Value "=== $Stage / $Kind / $($Target.name) ==="
    Add-StabilityLog -Path $LogPath -Value ("Command: {0} {1}" -f $ffmpegBin, ($safeArgs -join " "))
    Write-StabilityStatus ("FFmpeg start: {0} / {1} / {2}s / timeout {3}s" -f $Stage, $Target.name, $DurationSeconds, $effectiveTimeout)

    $started = Get-Date
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $ffmpegBin -ArgumentList $ffmpegArgs -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit($effectiveTimeout * 1000)) {
            try {
                $process.Kill()
            } catch {
                Add-StabilityLog -Path $LogPath -Value ("Kill failed after timeout: {0}" -f $_.Exception.Message)
            }
            $rawLog = "Stability Lukow timeout after $effectiveTimeout seconds.`r`n"
            $rawLog += (Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue)
            $rawLog += (Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue)
            $exitCode = 124
        } else {
            $rawLog = (Get-Content -LiteralPath $stdoutPath -Raw -ErrorAction SilentlyContinue)
            $rawLog += (Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue)
            $exitCode = $process.ExitCode
        }
    } catch {
        $rawLog = $_.Exception.Message
        $exitCode = 1
    } finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }

    $elapsed = ((Get-Date) - $started).TotalSeconds
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value (Sanitize-StabilityText $rawLog)
    Add-StabilityLog -Path $LogPath -Value ("ExitCode: {0}" -f $exitCode)
    Add-StabilityLog -Path $LogPath -Value ""
    $metrics = Parse-FfmpegLog -Text $rawLog -TargetDurationSeconds $DurationSeconds -ExitCode $exitCode
    $metrics["elapsed_wall_seconds"] = [math]::Round($elapsed, 2)
    $metrics["name"] = $Target.name
    $metrics["group"] = $Target.group
    $metrics["kind"] = $Kind
    $metrics["stage"] = $Stage
    $metrics["host"] = $Target.host
    $metrics["path"] = $Target.path
    $metrics["url"] = $SafeUrl
    Write-StabilityStatus (
        "FFmpeg koniec: {0} / {1} / stable={2} / frames={3} / fps={4} / EOF={5} / elapsed={6}s" -f
        $Stage,
        $Target.name,
        $metrics.stable,
        $metrics.frames,
        $metrics.fps,
        $metrics.eof_count,
        $metrics.elapsed_wall_seconds
    )
    return $metrics
}

function Invoke-ParallelGo2RtcProbe {
    param([array]$Targets)
    $ffmpegBin = if ($env:FFMPEG_BIN) { $env:FFMPEG_BIN } else { "ffmpeg" }
    $effectiveTimeout = if ($FfmpegTimeoutSeconds -gt 0) { $FfmpegTimeoutSeconds } else { [math]::Max($DurationSeconds + 45, 60) }
    Write-StabilityStatus ("Parallel go2rtc start: {0} streamow / {1}s / timeout {2}s" -f $Targets.Count, $DurationSeconds, $effectiveTimeout)
    Add-StabilityLog -Path $ParallelLogPath -Value "=== parallel go2rtc start ==="
    $items = @()
    foreach ($target in $Targets) {
        $url = "rtsp://127.0.0.1:8554/$($target.stream)"
        $ffmpegArgs = Get-FfmpegArgs -Url $url -TargetDurationSeconds $DurationSeconds
        Add-StabilityLog -Path $ParallelLogPath -Value ("Command: {0} {1}" -f $ffmpegBin, (($ffmpegArgs) -join " "))
        $stdoutPath = [System.IO.Path]::GetTempFileName()
        $stderrPath = [System.IO.Path]::GetTempFileName()
        $process = Start-Process -FilePath $ffmpegBin -ArgumentList $ffmpegArgs -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
        $items += [pscustomobject]@{
            Target = $target
            Process = $process
            StdoutPath = $stdoutPath
            StderrPath = $stderrPath
            StartedAt = Get-Date
            TimedOut = $false
        }
    }

    $deadline = (Get-Date).AddSeconds($effectiveTimeout)
    while ((Get-Date) -lt $deadline) {
        $running = @($items | Where-Object { -not $_.Process.HasExited })
        if (-not $running.Count) {
            break
        }
        Start-Sleep -Seconds 2
    }

    $results = @()
    foreach ($item in $items) {
        if (-not $item.Process.HasExited) {
            $item.TimedOut = $true
            try {
                $item.Process.Kill()
            } catch {
                Add-StabilityLog -Path $ParallelLogPath -Value ("Kill failed for {0}: {1}" -f $item.Target.name, $_.Exception.Message)
            }
        }
        $rawLog = ""
        if ($item.TimedOut) {
            $rawLog += "Stability Lukow timeout after $effectiveTimeout seconds.`r`n"
        }
        $rawLog += (Get-Content -LiteralPath $item.StdoutPath -Raw -ErrorAction SilentlyContinue)
        $rawLog += (Get-Content -LiteralPath $item.StderrPath -Raw -ErrorAction SilentlyContinue)
        Remove-Item -LiteralPath $item.StdoutPath, $item.StderrPath -Force -ErrorAction SilentlyContinue

        $exitCode = if ($item.TimedOut) { 124 } else { $item.Process.ExitCode }
        Add-StabilityLog -Path $ParallelLogPath -Value "=== parallel go2rtc / $($item.Target.name) ==="
        Add-Content -LiteralPath $ParallelLogPath -Encoding UTF8 -Value (Sanitize-StabilityText $rawLog)
        Add-StabilityLog -Path $ParallelLogPath -Value ("ExitCode: {0}" -f $exitCode)
        Add-StabilityLog -Path $ParallelLogPath -Value ""

        $metrics = Parse-FfmpegLog -Text $rawLog -TargetDurationSeconds $DurationSeconds -ExitCode $exitCode
        $metrics["elapsed_wall_seconds"] = [math]::Round(((Get-Date) - $item.StartedAt).TotalSeconds, 2)
        $metrics["name"] = $item.Target.name
        $metrics["group"] = $item.Target.group
        $metrics["kind"] = "go2rtc"
        $metrics["stage"] = "parallel"
        $metrics["host"] = $item.Target.host
        $metrics["path"] = $item.Target.path
        $metrics["url"] = "rtsp://127.0.0.1:8554/$($item.Target.stream)"
        $results += $metrics
        Write-StabilityStatus (
            "Parallel wynik: {0} / stable={1} / frames={2} / fps={3} / EOF={4}" -f
            $item.Target.name,
            $metrics.stable,
            $metrics.frames,
            $metrics.fps,
            $metrics.eof_count
        )
    }
    return $results
}

function Test-NetworkTarget {
    param([hashtable]$Target)
    Write-StabilityStatus ("Ping start: {0} ({1}) / count {2}" -f $Target.name, $Target.host, $NetworkPingCount)
    try {
        $results = Test-Connection -ComputerName $Target.host -Count $NetworkPingCount -ErrorAction SilentlyContinue
    } catch {
        $results = @()
    }
    $items = @($results)
    $latencies = @($items | ForEach-Object { $_.ResponseTime } | Where-Object { $_ -ne $null })
    $received = $latencies.Count
    $lost = [math]::Max($NetworkPingCount - $received, 0)
    $avg = if ($received) { [math]::Round(($latencies | Measure-Object -Average).Average, 2) } else { $null }
    $min = if ($received) { ($latencies | Measure-Object -Minimum).Minimum } else { $null }
    $max = if ($received) { ($latencies | Measure-Object -Maximum).Maximum } else { $null }
    $port554 = $false
    try {
        $port554 = [bool](Test-NetConnection -ComputerName $Target.host -Port 554 -InformationLevel Quiet -WarningAction SilentlyContinue)
    } catch {
        $port554 = $false
    }
    $result = [ordered]@{
        name = $Target.name
        host = $Target.host
        sent = $NetworkPingCount
        received = $received
        lost = $lost
        packet_loss_percent = if ($NetworkPingCount) { [math]::Round(($lost / $NetworkPingCount) * 100, 2) } else { $null }
        min_ms = $min
        avg_ms = $avg
        max_ms = $max
        jitter_proxy_ms = if ($received -gt 1) { [math]::Round(($max - $min), 2) } else { $null }
        rtsp_port_554_open = $port554
    }
    Add-Content -LiteralPath $NetworkLogPath -Encoding UTF8 -Value (($result | ConvertTo-Json -Depth 4) | Out-String)
    Write-StabilityStatus ("Ping koniec: {0} / loss={1}% / avg={2}ms / rtsp554={3}" -f $Target.name, $result.packet_loss_percent, $result.avg_ms, $result.rtsp_port_554_open)
    return $result
}

function Get-DockerSnapshot {
    $snapshot = [ordered]@{}
    try {
        $snapshot["compose_ps"] = Sanitize-StabilityText ((docker compose ps 2>&1 | Out-String))
    } catch {
        $snapshot["compose_ps"] = $_.Exception.Message
    }
    try {
        $snapshot["stats"] = Sanitize-StabilityText ((docker stats --no-stream 2>&1 | Out-String))
    } catch {
        $snapshot["stats"] = $_.Exception.Message
    }
    try {
        $logScript = Join-Path $PSScriptRoot "go2rtc_logs_sanitized.ps1"
        if (Test-Path -LiteralPath $logScript) {
            $snapshot["go2rtc_logs_tail"] = (& $logScript -Tail 150 2>&1 | Out-String)
        }
    } catch {
        $snapshot["go2rtc_logs_tail"] = $_.Exception.Message
    }
    return $snapshot
}

function Build-Conclusions {
    param([hashtable]$Report)
    $conclusions = @()
    $seqBad = @($Report.go2rtc_sequential | Where-Object { -not $_.stable })
    $parallelBad = @($Report.go2rtc_parallel | Where-Object { -not $_.stable })
    $directBad = @($Report.direct_camera | Where-Object { -not $_.stable -and -not $_.skipped })
    $networkBad = @($Report.network | Where-Object { $_.packet_loss_percent -gt 0 -or ($_.avg_ms -ne $null -and $_.avg_ms -gt 80) -or (-not $_.rtsp_port_554_open) })

    if ($networkBad.Count) {
        $conclusions += "Sa objawy problemu sieciowego: packet loss, wysokie opoznienie albo port RTSP 554 niedostepny dla co najmniej jednej kamery."
    }
    if ($directBad.Count) {
        $badNames = ($directBad | ForEach-Object { $_.name }) -join ", "
        $conclusions += "Direct RTSP pada dla: $badNames. To wskazuje na kamera/link/firmware/zasilanie albo limit sesji, bo panel i go2rtc nie sa wtedy glownym winowajca."
    }
    if ((-not $directBad.Count) -and $seqBad.Count) {
        $badNames = ($seqBad | ForEach-Object { $_.name }) -join ", "
        $conclusions += "Direct RTSP jest lepszy niz go2rtc dla: $badNames. Nastepny krok to konfiguracja go2rtc albo sposob restreamu."
    }
    if ((-not $seqBad.Count) -and $parallelBad.Count) {
        $badNames = ($parallelBad | ForEach-Object { $_.name }) -join ", "
        $conclusions += "Sekwencyjnie jest OK, ale rownolegle pada: $badNames. To wyglada jak limit jednoczesnych sesji, pasmo, CPU albo konkurencja o streamy."
    }
    if ((-not $seqBad.Count) -and (-not $parallelBad.Count) -and (-not $directBad.Count)) {
        $conclusions += "FFmpeg widzi streamy stabilnie. Jesli panel dalej pokazuje ladowanie, najbardziej podejrzany jest player/przegladarka/dekodowanie HEVC albo aktywne kafelki."
    }
    if ($Report.frigate_comparison -and $Report.frigate_comparison.enabled -and ($Report.frigate_comparison.with_frigate_unstable_count -gt $Report.frigate_comparison.without_frigate_unstable_count)) {
        $conclusions += "Frigate pogarsza wynik. Dla live view zostaw Frigate wylaczone albo ogranicz jego kamery/fps."
    }
    if (-not $conclusions.Count) {
        $conclusions += "Brak jednej oczywistej przyczyny w tym przebiegu; porownaj najnowsze raporty z momentem, kiedy obraz faktycznie padl."
    }
    return $conclusions
}

function Render-StabilityMarkdown {
    param([hashtable]$Report)
    $lines = @(
        "# Lukow Stability Lab",
        "",
        "## Co testuje",
        "Ten raport rozdziela stabilnosc na: siec, direct RTSP, go2rtc sekwencyjnie, go2rtc rownolegle i opcjonalny wplyw Frigate.",
        "",
        "## Wyniki sieci",
        '```json',
        (($Report.network | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## go2rtc sekwencyjnie",
        '```json',
        (($Report.go2rtc_sequential | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## go2rtc rownolegle",
        '```json',
        (($Report.go2rtc_parallel | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## direct RTSP",
        '```json',
        (($Report.direct_camera | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Frigate",
        '```json',
        (($Report.frigate_comparison | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Linki do recznego testu playera go2rtc",
        "- H9C 98 obiektyw 1: http://127.0.0.1:1984/stream.html?src=lukow_h9c_98_sub",
        "- H9C 98 obiektyw 2: http://127.0.0.1:1984/stream.html?src=lukow_h9c_98_lens2_sub",
        "- C8W 97: http://127.0.0.1:1984/stream.html?src=lukow_c8w_97_sub",
        "",
        "## Wnioski"
    )
    foreach ($item in $Report.conclusions) {
        $lines += "- $item"
    }
    $lines += @(
        "",
        "## Nastepne kroki",
        "- Jesli direct RTSP pada: sprawdz zasilanie kamery, Wi-Fi/LAN, firmware, limit sesji i czy kamera nie jest jednoczesnie ciagnieta przez aplikacje/rejestrator.",
        "- Jesli direct jest OK, ale go2rtc pada: zmieniamy konfiguracje go2rtc dla konkretnego streamu.",
        "- Jesli tylko rownolegly test pada: ograniczamy liczbe aktywnych live kafelkow i NVR, albo rozdzielamy obciazenie.",
        "- Jesli testy FFmpeg sa OK, ale panel buforuje: testujemy tryb playera/przegladarke/GPU decode."
    )
    return (Sanitize-StabilityText ($lines -join "`r`n"))
}

$Targets = @(
    @{ name = "h9c_lens1_sub"; group = "h9c_lens1"; stream = "lukow_h9c_98_sub"; host = "192.168.80.98"; path = "/Streaming/Channels/102"; secret = "CAMERA98_PASSWORD" },
    @{ name = "h9c_lens2_sub"; group = "h9c_lens2"; stream = "lukow_h9c_98_lens2_sub"; host = "192.168.80.98"; path = "/Streaming/Channels/202"; secret = "CAMERA98_PASSWORD" },
    @{ name = "c8w_97_sub"; group = "c8w_97"; stream = "lukow_c8w_97_sub"; host = "192.168.80.97"; path = "/Streaming/Channels/102"; secret = "CAMERA97_PASSWORD" }
)

Write-StabilityStatus "Stability Lukow start."
Write-StabilityStatus ("Raport: {0}" -f $ReportDir)
Write-StabilityStatus ("Opcje: Duration={0}s, PingCount={1}, Quick={2}, SkipDirect={3}, WithFrigate={4}" -f $DurationSeconds, $NetworkPingCount, [bool]$Quick, [bool]$SkipDirect, [bool]$WithFrigate)
Write-StabilityStatus "Ten test moze trwac kilkanascie minut; postep bedzie widoczny po kazdym streamie."

Assert-LukowCommand -Name "docker" -InstallHint "Zainstaluj i uruchom Docker Desktop."
Ensure-LukowFfmpeg -InstallIfMissing | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe"))) {
    Write-StabilityStatus "Brak .venv. Uruchamiam setup bez promptu admina..."
    & (Join-Path $PSScriptRoot "setup_lukow.ps1") -NoAdminPrompt
}

$Python = Get-LukowPython -Root $Root
Write-StabilityStatus "Init DB i seed kamer Lukow."
& $Python -m ezviz_panel.backend init-db
if ($LASTEXITCODE -ne 0) {
    throw "init-db nie powiodl sie."
}
Ensure-LukowCameraSeed -Root $Root

if (Test-LukowSecretTemplate -Root $Root) {
    throw "secrets.local.env ma placeholdery. Uzupelnij verification codes przed testem stabilnosci."
}

Write-StabilityStatus "Renderuje go2rtc runtime."
$renderOutput = & $Python -m ezviz_panel.backend go2rtc-render-runtime 2>&1
$renderOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    throw "Render go2rtc nie powiodl sie."
}
if (($renderOutput | Out-String) -match "Streams:\s*0") {
    throw "go2rtc wygenerowal 0 streamow. Sprawdz seed kamer i secrets.local.env."
}

Write-StabilityStatus "Startuje go2rtc i wylaczam Frigate do bazowego testu."
docker compose up -d --force-recreate go2rtc | Out-Null
docker compose stop frigate 2>$null | Out-Null

$deadline = (Get-Date).AddSeconds(45)
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
    throw "go2rtc nie jest gotowy do testu stabilnosci."
}

$networkResults = @()
foreach ($target in $Targets) {
    $networkResults += Test-NetworkTarget -Target $target
}

$go2rtcSequential = @()
Write-StabilityStatus "Etap 1/3: go2rtc sekwencyjnie."
foreach ($target in $Targets) {
    $url = "rtsp://127.0.0.1:8554/$($target.stream)"
    $go2rtcSequential += Invoke-StabilityProbe -Target $target -Url $url -SafeUrl $url -Kind "go2rtc" -Stage "sequential" -LogPath $SequentialLogPath
}

Write-StabilityStatus "Etap 2/3: go2rtc rownolegle."
$go2rtcParallel = @(Invoke-ParallelGo2RtcProbe -Targets $Targets)

$directResults = @()
if ($SkipDirect) {
    Write-StabilityStatus "Etap 3/3: direct RTSP pominiety przez -SkipDirect."
    foreach ($target in $Targets) {
        $directResults += [ordered]@{
            name = $target.name
            group = $target.group
            stage = "direct"
            kind = "direct-camera"
            skipped = $true
            reason = "Pominieto przez -SkipDirect."
        }
    }
} else {
    Write-StabilityStatus "Etap 3/3: direct RTSP bez go2rtc."
    foreach ($target in $Targets) {
        $password = $Secrets[$target.secret]
        if (-not $password) {
            Write-StabilityStatus ("Direct RTSP pominiety dla {0}: brak sekretu {1}" -f $target.name, $target.secret)
            $directResults += [ordered]@{
                name = $target.name
                group = $target.group
                stage = "direct"
                kind = "direct-camera"
                skipped = $true
                reason = "Brak sekretu $($target.secret)."
            }
            continue
        }
        $url = "rtsp://admin:$password@$($target.host):554$($target.path)"
        $safeUrl = "rtsp://admin:***@$($target.host):554$($target.path)"
        $directResults += Invoke-StabilityProbe -Target $target -Url $url -SafeUrl $safeUrl -Kind "direct-camera" -Stage "direct" -LogPath $DirectLogPath
    }
}

$frigateComparison = [ordered]@{ enabled = [bool]$WithFrigate }
if ($WithFrigate) {
    Write-StabilityStatus "Frigate comparison: startuje Frigate i uruchamiam rownolegly test go2rtc."
    docker compose up -d frigate | Out-Null
    Start-Sleep -Seconds 20
    $withFrigate = @(Invoke-ParallelGo2RtcProbe -Targets $Targets)
    docker compose stop frigate 2>$null | Out-Null
    $frigateComparison = [ordered]@{
        enabled = $true
        with_frigate = $withFrigate
        with_frigate_unstable_count = @($withFrigate | Where-Object { -not $_.stable }).Count
        without_frigate_unstable_count = @($go2rtcParallel | Where-Object { -not $_.stable }).Count
    }
}

Write-StabilityStatus "Zbieram snapshot Dockera i sanitizowane logi go2rtc."
$dockerSnapshot = Get-DockerSnapshot

$report = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    report_dir = $ReportDir
    duration_seconds = $DurationSeconds
    network_ping_count = $NetworkPingCount
    targets = $Targets
    network = $networkResults
    go2rtc_sequential = $go2rtcSequential
    go2rtc_parallel = $go2rtcParallel
    direct_camera = $directResults
    frigate_comparison = $frigateComparison
    docker = $dockerSnapshot
    conclusions = @()
}
$report.conclusions = Build-Conclusions -Report $report

$jsonText = Sanitize-StabilityText (($report | ConvertTo-Json -Depth 12) | Out-String)
Set-Content -LiteralPath $ReportJsonPath -Encoding UTF8 -Value $jsonText
Set-Content -LiteralPath $ReportMdPath -Encoding UTF8 -Value (Render-StabilityMarkdown -Report $report)

Write-Host ""
Write-Host "Stability Lukow report:"
Write-Host $ReportMdPath
Write-Host $ReportJsonPath
Write-Host ""
Write-Host "Wnioski:"
foreach ($item in $report.conclusions) {
    Write-Host "- $item"
}
