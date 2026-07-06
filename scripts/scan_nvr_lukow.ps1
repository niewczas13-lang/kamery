param(
    [string]$NvrHost = "192.168.80.129",
    [string]$UserName = "admin",
    [int[]]$Channels = @(1, 2, 3, 4, 5, 6, 7, 8),
    [int]$TimeoutSeconds = 8
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lukow_common.ps1"

$Root = Get-LukowProjectRoot
Set-Location $Root
Initialize-LukowEnvironment -Root $Root
Ensure-LukowFfmpeg -InstallIfMissing

function Get-NvrPassword {
    param([string]$Root)
    $secretsPath = Join-Path $Root "secrets.local.env"
    if (-not (Test-Path -LiteralPath $secretsPath)) {
        throw "Brak secrets.local.env. Skopiuj secrets.local.example.env i uzupelnij NVR_PASSWORD."
    }
    foreach ($rawLine in Get-Content -LiteralPath $secretsPath -Encoding UTF8) {
        $line = [string]$rawLine
        if (-not $line -or $line.TrimStart().StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $separator = $line.IndexOf("=")
        $key = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if ($key -eq "NVR_PASSWORD") {
            if (-not $value -or $value -like "PUT_*") {
                throw "NVR_PASSWORD w secrets.local.env ma placeholder. Wpisz haslo RTSP rejestratora."
            }
            return $value
        }
    }
    throw "Brak NVR_PASSWORD w secrets.local.env. Dodaj linie: NVR_PASSWORD=<haslo rejestratora>."
}

function Test-NvrRtspPort {
    param([string]$NvrHost)
    $result = Test-NetConnection -ComputerName $NvrHost -Port 554 -WarningAction SilentlyContinue
    return [bool]$result.TcpTestSucceeded
}

function Get-MaskedUrl {
    param([string]$Url, [string]$Password)
    return $Url.Replace([uri]::EscapeDataString($Password), "***")
}

function Test-NvrChannelStream {
    param(
        [string]$NvrHost,
        [string]$UserName,
        [string]$Password,
        [string]$ChannelPath,
        [int]$TimeoutSeconds
    )
    $encodedUser = [uri]::EscapeDataString($UserName)
    $encodedPassword = [uri]::EscapeDataString($Password)
    $url = "rtsp://${encodedUser}:${encodedPassword}@${NvrHost}:554${ChannelPath}"
    $ffprobeArgs = @(
        "-v", "error",
        "-rtsp_transport", "tcp",
        "-rw_timeout", ($TimeoutSeconds * 1000000).ToString(),
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate",
        "-of", "csv=p=0",
        $url
    )
    $output = & ffprobe @ffprobeArgs 2>&1 | Out-String
    $masked = (Get-MaskedUrl -Url $output.Trim() -Password $Password)
    if ($LASTEXITCODE -eq 0 -and $masked) {
        return [pscustomobject]@{ Path = $ChannelPath; Ok = $true; Detail = $masked }
    }
    return [pscustomobject]@{ Path = $ChannelPath; Ok = $false; Detail = $masked }
}

$password = Get-NvrPassword -Root $Root

Write-Host "Sprawdzam port RTSP 554 na $NvrHost..."
if (-not (Test-NvrRtspPort -NvrHost $NvrHost)) {
    Write-Host ""
    Write-Host "Port 554 na $NvrHost jest ZAMKNIETY - RTSP na rejestratorze jest wylaczone." -ForegroundColor Yellow
    Write-Host "Wlacz RTSP na EZVIZ X5S (menu lokalne na monitorze HDMI/VGA: Konfiguracja -> Siec -> Zaawansowane,"
    Write-Host "albo w aplikacji EZVIZ: urzadzenie -> Ustawienia -> Ustawienia uslug lokalnych / LAN Live View -> RTSP)"
    Write-Host "i uruchom skan ponownie."
    exit 1
}
Write-Host "Port 554 otwarty. Skanuje kanaly..." -ForegroundColor Green

$results = @()
foreach ($channel in $Channels) {
    foreach ($stream in @("01", "02")) {
        $path = "/Streaming/Channels/$channel$stream"
        $kind = "MAIN"
        if ($stream -eq "02") { $kind = "SUB" }
        Write-Host ("Kanal {0} {1}: {2} ..." -f $channel, $kind, $path)
        $result = Test-NvrChannelStream -NvrHost $NvrHost -UserName $UserName -Password $password -ChannelPath $path -TimeoutSeconds $TimeoutSeconds
        $results += [pscustomobject]@{ Channel = $channel; Stream = $kind; Path = $path; Ok = $result.Ok; Detail = $result.Detail }
        if ($result.Ok) {
            Write-Host ("  OK: {0}" -f $result.Detail) -ForegroundColor Green
        } else {
            Write-Host ("  BRAK: {0}" -f $result.Detail) -ForegroundColor DarkGray
        }
    }
}

Write-Host ""
Write-Host "=== PODSUMOWANIE ==="
$working = @($results | Where-Object { $_.Ok })
if ($working.Count -eq 0) {
    Write-Host "Zaden kanal nie odpowiedzial. Sprawdz haslo (sprobuj tez Verification Code z naklejki rejestratora)" -ForegroundColor Yellow
    Write-Host "wpisujac je do secrets.local.env jako NVR_PASSWORD i uruchom skan ponownie."
    exit 1
}
$working | Format-Table Channel, Stream, Path, Detail -AutoSize | Out-String | Write-Host
Write-Host "Aktywne kanaly wpisz do LUKOW_NVR_CHANNELS w src/ezviz_panel/backend/lukow_seed.py"
Write-Host "(dopasuj kanal do kamery wg kolejnosci w aplikacji EZVIZ / na monitorze rejestratora)."
