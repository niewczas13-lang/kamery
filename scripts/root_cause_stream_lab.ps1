param(
    [int]$DurationSeconds = 120,
    [int]$PingCount = 200,
    [int]$FfmpegTimeoutSeconds = 0,
    [switch]$Quick,
    [switch]$OnlyGo2rtc,
    [switch]$OnlyDirect,
    [switch]$OnlyNetwork,
    [switch]$WithFrigateComparison,
    [switch]$WithRecorderComparison,
    [switch]$VideoOnly,
    [switch]$SkipDirectCamera,
    [switch]$SkipNetwork,
    [switch]$AllowDirectCameraRtsp,
    [switch]$StableOnly
)

$ErrorActionPreference = "Continue"
if ($Quick) {
    if (-not $PSBoundParameters.ContainsKey("DurationSeconds")) {
        $DurationSeconds = 15
    }
    if (-not $PSBoundParameters.ContainsKey("PingCount")) {
        $PingCount = 5
    }
}
$Root = Split-Path -Parent $PSScriptRoot
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ReportDir = Join-Path $Root "runtime\diagnostics\root-cause-$Stamp"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$DirectLogPath = Join-Path $ReportDir "direct-camera-logs-sanitized.txt"
$Go2RtcLogPath = Join-Path $ReportDir "go2rtc-logs-sanitized.txt"
$ReportJsonPath = Join-Path $ReportDir "report.json"
$ReportMdPath = Join-Path $ReportDir "report.md"
Set-Content -LiteralPath $DirectLogPath -Encoding UTF8 -Value "Direct camera logs sanitized by Root Cause Lab."
Set-Content -LiteralPath $Go2RtcLogPath -Encoding UTF8 -Value "go2rtc logs sanitized by Root Cause Lab."

$SecretFile = $env:EZVIZ_SECRETS_ENV_FILE
if (-not $SecretFile) {
    $Candidate = Join-Path $Root "secrets.local.env"
    if (Test-Path -LiteralPath $Candidate) {
        $SecretFile = $Candidate
    }
}

function Read-Secrets {
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

$Secrets = Read-Secrets -Path $SecretFile

function Write-LabStatus {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

function Sanitize-Text {
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

function Add-SanitizedLine {
    param(
        [string]$Path,
        [string]$Value
    )
    Add-Content -LiteralPath $Path -Encoding UTF8 -Value (Sanitize-Text $Value)
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
    $timeout = $lower.Contains("timeout") -or $lower.Contains("timed out")
    $hevcErrors = 0
    foreach ($line in $lower -split "`r?`n") {
        if ($line.Contains("pps id out of range") -or $line.Contains("could not find ref") -or $line.Contains("skipping invalid undecodable nalu") -or $line.Contains("error while decoding") -or $line.Contains("invalid data found")) {
            $hevcErrors += 1
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
        hevc_error_count = $hevcErrors
        stable = [bool]$stable
        exit_code = $ExitCode
    }
}

function Invoke-FfmpegProbe {
    param(
        [string]$Name,
        [string]$Url,
        [string]$SanitizedUrl,
        [string]$Kind,
        [string]$LogPath,
        [string]$PathValue = ""
    )
    $ffmpegBin = if ($env:FFMPEG_BIN) { $env:FFMPEG_BIN } else { "ffmpeg" }
    Add-SanitizedLine -Path $LogPath -Value "=== $Kind $Name ==="
    $effectiveTimeout = if ($FfmpegTimeoutSeconds -gt 0) { $FfmpegTimeoutSeconds } else { [math]::Max($DurationSeconds + 30, 30) }
    Write-LabStatus ("FFmpeg start: {0} / {1} / target {2}s / timeout {3}s" -f $Kind, $Name, $DurationSeconds, $effectiveTimeout)
    $ffmpegArgs = @("-rtsp_transport", "tcp", "-hide_banner", "-i", $Url)
    $safeArgs = @("-rtsp_transport", "tcp", "-hide_banner", "-i", $SanitizedUrl)
    if ($VideoOnly) {
        $ffmpegArgs += @("-map", "0:v:0", "-an")
        $safeArgs += @("-map", "0:v:0", "-an")
    }
    $ffmpegArgs += @("-t", [string]$DurationSeconds, "-f", "null", "-")
    $safeArgs += @("-t", [string]$DurationSeconds, "-f", "null", "-")
    Add-SanitizedLine -Path $LogPath -Value ("Command: {0} {1}" -f $ffmpegBin, ($safeArgs -join " "))
    $started = Get-Date
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        $process = Start-Process -FilePath $ffmpegBin -ArgumentList $ffmpegArgs -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -WindowStyle Hidden -PassThru
        if (-not $process.WaitForExit($effectiveTimeout * 1000)) {
            try {
                $process.Kill()
            } catch {
                Add-SanitizedLine -Path $LogPath -Value ("Kill failed after timeout: {0}" -f $_.Exception.Message)
            }
            $rawLog = "Root Cause Lab timeout after $effectiveTimeout seconds.`r`n"
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
    $safeLog = Sanitize-Text $rawLog
    Add-Content -LiteralPath $LogPath -Encoding UTF8 -Value $safeLog
    Add-SanitizedLine -Path $LogPath -Value ("ExitCode: {0}" -f $exitCode)
    Add-SanitizedLine -Path $LogPath -Value ""
    $metrics = Parse-FfmpegLog -Text $rawLog -TargetDurationSeconds $DurationSeconds -ExitCode $exitCode
    $metrics["elapsed_wall_seconds"] = [math]::Round($elapsed, 2)
    $metrics["name"] = $Name
    $metrics["kind"] = $Kind
    $metrics["path"] = $PathValue
    $metrics["url"] = $SanitizedUrl
    Write-LabStatus (
        "FFmpeg koniec: {0} / {1} / stable={2} / frames={3} / fps={4} / EOF={5} / elapsed={6}s" -f
        $Kind,
        $Name,
        $metrics.stable,
        $metrics.frames,
        $metrics.fps,
        $metrics.eof_count,
        $metrics.elapsed_wall_seconds
    )
    return $metrics
}

function Test-NetworkQuality {
    param(
        [string]$Name,
        [string]$CameraHost
    )
    Write-LabStatus ("Ping start: {0} ({1}) / count {2}" -f $Name, $CameraHost, $PingCount)
    try {
        $results = Test-Connection -ComputerName $CameraHost -Count $PingCount -ErrorAction SilentlyContinue
    } catch {
        $results = @()
    }
    $items = @($results)
    $latencies = @($items | ForEach-Object { $_.ResponseTime } | Where-Object { $_ -ne $null })
    $received = $latencies.Count
    $lost = [math]::Max($PingCount - $received, 0)
    $avg = if ($received) { [math]::Round(($latencies | Measure-Object -Average).Average, 2) } else { $null }
    $min = if ($received) { ($latencies | Measure-Object -Minimum).Minimum } else { $null }
    $max = if ($received) { ($latencies | Measure-Object -Maximum).Maximum } else { $null }
    $jitter = if ($received -gt 1) { [math]::Round(($max - $min), 2) } else { $null }
    $result = [ordered]@{
        name = $Name
        host = $CameraHost
        sent = $PingCount
        received = $received
        lost = $lost
        packet_loss_percent = if ($PingCount) { [math]::Round(($lost / $PingCount) * 100, 2) } else { $null }
        min_ms = $min
        avg_ms = $avg
        max_ms = $max
        jitter_proxy_ms = $jitter
    }
    Write-LabStatus ("Ping koniec: {0} / loss={1}% / avg={2}ms" -f $Name, $result.packet_loss_percent, $result.avg_ms)
    return $result
}

function Run-Go2RtcSuite {
    param([string]$Label = "go2rtc")
    $stableStreams = @(
        @{ name = "lukow_h9c_98_sub"; path = "/Streaming/Channels/102" },
        @{ name = "lukow_h9c_98_lens2_sub"; path = "/Streaming/Channels/202" },
        @{ name = "lukow_c8w_97_sub"; path = "/Streaming/Channels/102" }
    )
    $diagnosticStreams = @(
        @{ name = "lukow_c8c_60_sub"; path = "/Streaming/Channels/102" },
        @{ name = "lukow_c8c_60_sub_ch1"; path = "/ch1/sub" }
    )
    $streams = if ($StableOnly) { $stableStreams } else { $stableStreams + $diagnosticStreams }
    $results = @()
    Write-LabStatus ("Start testow go2rtc: {0} streamow" -f $streams.Count)
    foreach ($stream in $streams) {
        $url = "rtsp://127.0.0.1:8554/$($stream.name)"
        $results += Invoke-FfmpegProbe -Name $stream.name -Url $url -SanitizedUrl $url -Kind $Label -LogPath $Go2RtcLogPath -PathValue $stream.path
    }
    return $results
}

function Run-DirectSuite {
    if (-not $AllowDirectCameraRtsp) {
        Write-LabStatus "Direct RTSP pominiety: dodaj -AllowDirectCameraRtsp, jezeli chcesz test bez go2rtc."
        return @([ordered]@{
            skipped = $true
            reason = "Direct RTSP wymaga flagi -AllowDirectCameraRtsp."
        })
    }
    if (-not $SecretFile -or -not (Test-Path -LiteralPath $SecretFile)) {
        Write-LabStatus "Direct RTSP pominiety: brak EZVIZ_SECRETS_ENV_FILE albo secrets.local.env."
        return @([ordered]@{
            skipped = $true
            reason = "Brak EZVIZ_SECRETS_ENV_FILE albo secrets.local.env."
        })
    }
    $targets = @(
        @{ name = "h9c_lens1_sub"; host = "192.168.80.98"; path = "/Streaming/Channels/102"; secret = "CAMERA98_PASSWORD" },
        @{ name = "h9c_lens2_sub"; host = "192.168.80.98"; path = "/Streaming/Channels/202"; secret = "CAMERA98_PASSWORD" },
        @{ name = "c8w_sub"; host = "192.168.80.97"; path = "/Streaming/Channels/102"; secret = "CAMERA97_PASSWORD" },
        @{ name = "c8c60_sub_streaming_102"; host = "192.168.80.60"; path = "/Streaming/Channels/102"; secret = "CAMERA60_PASSWORD" },
        @{ name = "c8c60_sub_ch1"; host = "192.168.80.60"; path = "/ch1/sub"; secret = "CAMERA60_PASSWORD" }
    )
    $results = @()
    Write-LabStatus ("Start testow direct RTSP: {0} streamow, sekrety beda maskowane" -f $targets.Count)
    foreach ($target in $targets) {
        $password = $Secrets[$target.secret]
        if (-not $password) {
            Write-LabStatus ("Direct RTSP pominiety dla {0}: brak sekretu {1}" -f $target.name, $target.secret)
            $results += [ordered]@{
                name = $target.name
                path = $target.path
                stable = $false
                skipped = $true
                reason = "Brak sekretu $($target.secret)."
            }
            continue
        }
        $url = "rtsp://admin:$password@$($target.host):554$($target.path)"
        $safeUrl = "rtsp://admin:***@$($target.host):554$($target.path)"
        $results += Invoke-FfmpegProbe -Name $target.name -Url $url -SanitizedUrl $safeUrl -Kind "direct-camera" -LogPath $DirectLogPath -PathValue $target.path
    }
    return $results
}

function Get-DockerSnapshot {
    Write-LabStatus "Zbieram docker compose ps, docker stats i sanitizowany tail go2rtc logs."
    $snapshot = [ordered]@{}
    try {
        $snapshot["compose_ps"] = Sanitize-Text ((docker compose ps 2>&1 | Out-String))
    } catch {
        $snapshot["compose_ps"] = $_.Exception.Message
    }
    try {
        $snapshot["stats"] = Sanitize-Text ((docker stats --no-stream 2>&1 | Out-String))
    } catch {
        $snapshot["stats"] = $_.Exception.Message
    }
    try {
        $LogScript = Join-Path $PSScriptRoot "go2rtc_logs_sanitized.ps1"
        if (Test-Path -LiteralPath $LogScript) {
            $snapshot["go2rtc_logs_tail"] = (& $LogScript -Tail 120 2>&1 | Out-String)
        }
    } catch {
        $snapshot["go2rtc_logs_tail"] = $_.Exception.Message
    }
    Write-LabStatus "Docker snapshot gotowy."
    return $snapshot
}

function Compare-C8C60Paths {
    param([array]$Results)
    $candidates = @($Results | Where-Object { $_.name -in @("lukow_c8c_60_sub", "lukow_c8c_60_sub_ch1", "c8c60_sub_streaming_102", "c8c60_sub_ch1") })
    if (-not $candidates.Count) {
        return [ordered]@{ preferred_sub_path = $null; preferred_stream = $null; reason = "Brak wynikow C8C 60." }
    }
    $ranked = $candidates | Sort-Object -Descending -Property @{ Expression = {
        $score = 0.0
        if ($_.stable) { $score += 10000 }
        if ($null -ne $_.fps) { $score += ([double]$_.fps * 100) }
        if ($null -ne $_.speed) { $score += ([double]$_.speed * 100) }
        if ($null -ne $_.eof_count) { $score -= ([double]$_.eof_count * 500) }
        if ($null -ne $_.hevc_error_count) { $score -= ([double]$_.hevc_error_count * 5) }
        $score
    } }
    $best = @($ranked)[0]
    if (-not (@($candidates | Where-Object { $_.stable }).Count)) {
        return [ordered]@{
            preferred_sub_path = $null
            preferred_stream = $null
            least_bad_sub_path = $best.path
            least_bad_stream = $best.name
            reason = "Brak stabilnego pathu C8C 60; nie ustawiaj preferred_sub_path na podstawie tego przebiegu."
            all_candidates_unstable = $true
        }
    }
    return [ordered]@{
        preferred_sub_path = $best.path
        preferred_stream = $best.name
        least_bad_sub_path = $best.path
        least_bad_stream = $best.name
        reason = "Wybrano wynik z najlepszym stable/fps/speed i bez EOF."
        all_candidates_unstable = $false
    }
}

function Build-Conclusions {
    param([hashtable]$Report)
    $conclusions = @()
    $directResults = @($Report.direct_camera | Where-Object { -not $_.skipped })
    $go2rtcResults = @($Report.go2rtc | Where-Object { -not $_.skipped })
    $directStable = if ($directResults.Count) { -not (@($directResults | Where-Object { -not $_.stable }).Count) } else { $null }
    $go2rtcStable = if ($go2rtcResults.Count) { -not (@($go2rtcResults | Where-Object { -not $_.stable }).Count) } else { $null }
    if ($directStable -eq $false -and $go2rtcStable -eq $false) {
        $conclusions += "Problem jest prawdopodobnie w: kamera, siec, Wi-Fi, VPN albo rejestrator."
    }
    if ($directStable -eq $true -and $go2rtcStable -eq $false) {
        $conclusions += "Problem jest prawdopodobnie w konfiguracji go2rtc albo restreamu."
    }
    if ($directStable -eq $true -and $go2rtcStable -eq $true) {
        $conclusions += "Direct RTSP i go2rtc wygladaja stabilnie; jesli panel dalej laguje, sprawdz HEVC decode, CPU/GPU i liczbe aktywnych kafelkow."
    }
    if ($Report.frigate_impact -and $Report.frigate_impact.off_stable_count -gt $Report.frigate_impact.on_stable_count) {
        $conclusions += "Frigate zwieksza obciazenie lub konkurencje o streamy."
    }
    if ($Report.recorder_impact -and $Report.recorder_impact.manual_mode) {
        $conclusions += "Porownaj wariant rejestrator ON/OFF recznie; dodatkowe sesje RTSP moga obciazac kamery."
    }
    if ($Report.network_quality) {
        $badNetwork = @($Report.network_quality | Where-Object { $_.packet_loss_percent -gt 0 -or ($_.avg_ms -ne $null -and $_.avg_ms -gt 80) })
        if ($badNetwork.Count) {
            $conclusions += "Siec/VPN ma packet loss albo wysoka latencje; porownaj test LAN vs WireGuard."
        }
    }
    if (-not $conclusions.Count) {
        $conclusions += "Brak jednoznacznej klasyfikacji; porownaj direct RTSP, go2rtc, panel, Frigate, rejestrator i VPN."
    }
    return $conclusions
}

function Render-MarkdownReport {
    param([hashtable]$Report)
    $lines = @(
        "# Root Cause Lab - raport",
        "",
        "## Podsumowanie",
        $Report.summary,
        "",
        "## Topologia testu",
        $Report.topology,
        "",
        "## Kamery",
        "H9C 98, C8W 97, C8C 60. C8C 102 pozostaje unstable/experimental.",
        "",
        "## Wyniki direct camera",
        '```json',
        (($Report.direct_camera | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Wyniki go2rtc",
        '```json',
        (($Report.go2rtc | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## C8C 60 path comparison",
        '```json',
        (($Report.c8c60_path_comparison | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Frigate impact",
        '```json',
        (($Report.frigate_impact | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Rejestrator impact",
        "Nie zostawiaj rejestratora odlaczonego, jesli odpowiada za wazne nagrania.",
        '```json',
        (($Report.recorder_impact | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## WireGuard/VPN impact",
        '```json',
        (($Report.network_quality | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Docker stats",
        '```json',
        (($Report.docker_stats | ConvertTo-Json -Depth 8) | Out-String).Trim(),
        '```',
        "",
        "## Browser decode notes",
        $Report.browser_decode_notes,
        "",
        "## Wnioski"
    )
    foreach ($item in $Report.conclusions) {
        $lines += "- $item"
    }
    $lines += @(
        "",
        "## Rekomendowane nastepne kroki",
        "- Jesli C8C 60 /ch1/sub jest stabilniejszy, ustaw stream-override na /ch1/sub.",
        "- Jesli Frigate OFF poprawia wynik, ogranicz konkurencje o streamy albo przenies ingest blizej kamer.",
        "- Jesli WireGuard ma straty/jitter, testuj stack w LAN kamer.",
        "- Jesli direct/go2rtc sa stabilne, a panel laguje, sprawdz GPU Video Decode i aktywny limit kafelkow."
    )
    return (Sanitize-Text ($lines -join "`r`n"))
}

$runDirect = (-not $SkipDirectCamera) -and (-not $OnlyGo2rtc) -and (-not $OnlyNetwork)
$runGo2rtc = (-not $OnlyDirect) -and (-not $OnlyNetwork)
$runNetwork = (-not $SkipNetwork) -and (-not $OnlyDirect) -and (-not $OnlyGo2rtc)

$estimatedFfmpegRuns = 0
if ($runGo2rtc) { $estimatedFfmpegRuns += 5 }
if ($runDirect -and $AllowDirectCameraRtsp) { $estimatedFfmpegRuns += 5 }
if ($WithFrigateComparison) { $estimatedFfmpegRuns += 10 }
if ($WithRecorderComparison) { $estimatedFfmpegRuns += 10 }
$estimatedMinutes = [math]::Ceiling(($estimatedFfmpegRuns * $DurationSeconds) / 60)

Write-LabStatus "Root Cause Lab start."
Write-LabStatus ("Raport roboczy: {0}" -f $ReportDir)
Write-LabStatus ("Opcje: Duration={0}s, PingCount={1}, Quick={2}, VideoOnly={3}, OnlyGo2rtc={4}, OnlyDirect={5}, OnlyNetwork={6}" -f $DurationSeconds, $PingCount, [bool]$Quick, [bool]$VideoOnly, [bool]$OnlyGo2rtc, [bool]$OnlyDirect, [bool]$OnlyNetwork)
if ($estimatedFfmpegRuns -gt 0) {
    Write-LabStatus ("Plan FFmpeg: {0} probe(s), okolo {1} min przy pelnym czasie kazdej proby." -f $estimatedFfmpegRuns, $estimatedMinutes)
}
if (-not $Quick -and $DurationSeconds -ge 120 -and $estimatedFfmpegRuns -ge 5) {
    Write-LabStatus "Pelny przebieg moze wygladac dlugo. Szybki smoke: .\scripts\root_cause_stream_lab.ps1 -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly"
}

$directResults = @()
$go2rtcResults = @()
$networkResults = @()
$frigateImpact = [ordered]@{ enabled = [bool]$WithFrigateComparison }
$recorderImpact = [ordered]@{ enabled = [bool]$WithRecorderComparison }

if ($runDirect) {
    $directResults = @(Run-DirectSuite)
}

if ($runGo2rtc) {
    $go2rtcResults = @(Run-Go2RtcSuite)
}

if ($runNetwork) {
    $networkTargets = @(
        @{ name = "H9C 98"; host = "192.168.80.98" },
        @{ name = "C8W 97"; host = "192.168.80.97" },
        @{ name = "C8C 60"; host = "192.168.80.60" }
    )
    foreach ($target in $networkTargets) {
        $networkResults += Test-NetworkQuality -Name $target.name -CameraHost $target.host
    }
}

if ($WithFrigateComparison) {
    Write-LabStatus "Frigate comparison: startuje Frigate i czekam 10s."
    docker compose up -d frigate | Out-Null
    Start-Sleep -Seconds 10
    $on = @(Run-Go2RtcSuite -Label "go2rtc-frigate-on")
    Write-LabStatus "Frigate comparison: zatrzymuje Frigate i czekam 10s."
    docker compose stop frigate | Out-Null
    Start-Sleep -Seconds 10
    $off = @(Run-Go2RtcSuite -Label "go2rtc-frigate-off")
    $frigateImpact = [ordered]@{
        enabled = $true
        on = $on
        off = $off
        on_stable_count = @($on | Where-Object { $_.stable }).Count
        off_stable_count = @($off | Where-Object { $_.stable }).Count
        conclusion = if (@($off | Where-Object { $_.stable }).Count -gt @($on | Where-Object { $_.stable }).Count) { "Frigate wplywa na stabilnosc." } else { "Brak wyraznego wplywu Frigate w tym przebiegu." }
    }
}

if ($WithRecorderComparison) {
    Write-LabStatus "Recorder impact manual mode."
    Write-LabStatus "1. Zostaw rejestrator ON i nacisnij Enter."
    Read-Host | Out-Null
    $recorderOn = @(Run-Go2RtcSuite -Label "go2rtc-recorder-on")
    Write-LabStatus "2. Odlacz rejestrator albo wylacz pobieranie tych kamer, odczekaj 60 s i nacisnij Enter."
    Read-Host | Out-Null
    Write-LabStatus "Czekam 60s po zmianie rejestratora."
    Start-Sleep -Seconds 60
    $recorderOff = @(Run-Go2RtcSuite -Label "go2rtc-recorder-off")
    Write-LabStatus "Podlacz rejestrator z powrotem, jesli odpowiada za wazne nagrania."
    $recorderImpact = [ordered]@{
        enabled = $true
        manual_mode = $true
        warning = "Nie zostawiaj rejestratora odlaczonego, jesli odpowiada za wazne nagrania."
        on = $recorderOn
        off = $recorderOff
    }
}

$dockerStats = Get-DockerSnapshot
$combinedC8c = @($directResults + $go2rtcResults)

$report = [ordered]@{
    generated_at = (Get-Date).ToString("s")
    summary = "Root Cause Lab porownuje direct RTSP, go2rtc, siec/VPN, Docker, Frigate i rejestrator bez ujawniania sekretow."
    topology = "Jesli stack dziala na komputerze po WireGuard: kamera -> WireGuard -> komputer -> go2rtc -> Frigate -> frontend. Stabilniejszy wariant do sprawdzenia: kamera -> lokalny serwer/gateway w Lukowie -> go2rtc/Frigate -> panel."
    options = [ordered]@{
        duration_seconds = $DurationSeconds
        ping_count = $PingCount
        quick = [bool]$Quick
        ffmpeg_timeout_seconds = if ($FfmpegTimeoutSeconds -gt 0) { $FfmpegTimeoutSeconds } else { [math]::Max($DurationSeconds + 30, 30) }
        video_only = [bool]$VideoOnly
        allow_direct_camera_rtsp = [bool]$AllowDirectCameraRtsp
    }
    direct_camera = $directResults
    go2rtc = $go2rtcResults
    c8c60_path_comparison = Compare-C8C60Paths -Results $combinedC8c
    frigate_impact = $frigateImpact
    recorder_impact = $recorderImpact
    network_quality = $networkResults
    docker_stats = $dockerStats
    browser_decode_notes = "Uzupelnij recznie: CPU, GPU Video Decode, GPU 3D, RAM i siec dla 1/2/4/6 aktywnych streamow."
    conclusions = @()
}
$report.conclusions = Build-Conclusions -Report $report

$jsonText = Sanitize-Text (($report | ConvertTo-Json -Depth 12) | Out-String)
Set-Content -LiteralPath $ReportJsonPath -Encoding UTF8 -Value $jsonText
Set-Content -LiteralPath $ReportMdPath -Encoding UTF8 -Value (Render-MarkdownReport -Report $report)

if ($directResults.Count) {
    Set-Content -LiteralPath (Join-Path $ReportDir "direct-camera-results.json") -Encoding UTF8 -Value (Sanitize-Text (($directResults | ConvertTo-Json -Depth 8) | Out-String))
}
if ($go2rtcResults.Count) {
    Set-Content -LiteralPath (Join-Path $ReportDir "go2rtc-results.json") -Encoding UTF8 -Value (Sanitize-Text (($go2rtcResults | ConvertTo-Json -Depth 8) | Out-String))
}
if ($frigateImpact.enabled) {
    Set-Content -LiteralPath (Join-Path $ReportDir "frigate-impact-results.json") -Encoding UTF8 -Value (Sanitize-Text (($frigateImpact | ConvertTo-Json -Depth 12) | Out-String))
}

Write-Host "Root Cause Lab report:"
Write-Host $ReportMdPath
Write-Host $ReportJsonPath
