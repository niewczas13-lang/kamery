# Sieć, LAN i WireGuard dla streamów kamer

Panel działa lokalnie i nie wystawia go2rtc, RTSP, ONVIF ani portów kamer
publicznie. Jeżeli komputer operatora łączy się z lokalizacją kamer przez
WireGuard, każdy aktywny stream może iść przez VPN.

## Dwie topologie

Obecny wariant, gdy stack działa na komputerze użytkownika po VPN:

```text
kamera -> Wi-Fi/LAN kamer -> WireGuard -> komputer -> go2rtc -> Frigate -> panel
```

Wariant do sprawdzenia w przyszłości:

```text
kamera -> Wi-Fi/LAN kamer -> lokalny serwer/gateway w Łukowie -> go2rtc/Frigate -> panel
```

Drugi wariant zwykle jest stabilniejszy, bo ingest RTSP i NVR zostają przy
kamerach, a przez VPN/idzie tylko gotowy podgląd albo panel.

## Ping i packet loss

Podstawowy test:

```powershell
ping -n 200 192.168.80.98
ping -n 200 192.168.80.97
ping -n 200 192.168.80.60
```

Szukaj:

- utraty pakietów powyżej `0%`,
- dużych skoków `Maximum`,
- średniej latencji wyższej niż zwykle dla tej lokalizacji.

Skrypt:

```powershell
.\scripts\test_network_quality.ps1 -PingCount 200
```

## Pathping i iperf3

`pathping` pomaga zobaczyć straty po drodze:

```powershell
pathping 192.168.80.98
```

`iperf3` jest opcjonalny. Użyj go tylko, jeśli masz host w LAN kamer:

```text
iperf3 -s
iperf3 -c <host-w-lan-kamer>
```

## RTSP port 554

Jeżeli ping działa, ale streamy zrywają się z EOF, sprawdź też stabilność portu
554 przez dłuższy test FFmpeg w Root Cause Lab:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

## LAN vs WireGuard

1. Uruchom Root Cause Lab z komputera po WireGuard.
2. Uruchom ten sam test lokalnie w LAN kamer albo na gatewayu w Łukowie.
3. Porównaj `report.md` i `report.json`.

Jeżeli LAN jest stabilny, a WireGuard nie, przyczyna jest prawdopodobnie w VPN,
routingu, upload/download albo jitterze. Jeżeli oba warianty są niestabilne,
szukaj przy kamerze, Wi-Fi, pathach RTSP, rejestratorze albo go2rtc.
