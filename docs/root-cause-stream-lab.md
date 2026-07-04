# Root Cause Lab dla lagów streamów

Ten etap służy do znalezienia prawdziwej przyczyny lagów. Nie jest kolejną
mitigacją UI. Test porównuje kamerę bezpośrednio, go2rtc, Frigate, rejestrator,
LAN/WireGuard, obciążenie Dockera i ręczną obserwację dekodowania HEVC w
przeglądarce.

Nie wklejaj raw `docker logs` z go2rtc. Błędy upstream potrafią zawierać pełny
RTSP URL z hasłem. Używaj tylko sanitizowanych logów i raportów z katalogu
`runtime/diagnostics/`.

## Szybki start

Krótki smoke, żeby sprawdzić czy lab działa i czy terminal pokazuje postęp:

```powershell
.\scripts\root_cause_stream_lab.ps1 -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly
```

Domyślny test go2rtc, sieci, Docker stats i sanitizowanych logów:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

Pełny test 120 s dla 5 streamów go2rtc trwa co najmniej około 10 minut, bo
każdy stream jest mierzony osobno. Jeżeli dodasz Frigate ON/OFF albo direct RTSP,
czas rośnie dalej. Skrypt wypisuje teraz start, plan, każdy testowany stream,
timeout i wynik po każdej próbie.

Raport powstaje tutaj:

```text
runtime/diagnostics/root-cause-YYYYMMDD-HHMMSS/
```

Najważniejsze pliki:

```text
report.md
report.json
direct-camera-results.json
direct-camera-logs-sanitized.txt
go2rtc-results.json
go2rtc-logs-sanitized.txt
frigate-impact-results.json
```

`runtime/` jest ignorowane przez Git. Nie commituj raportów, runtime configów,
`runtime/config/go2rtc/go2rtc.yaml`, `secrets.local.env` ani żadnych plików z
hasłami kamer.

## Opcje skryptu

```powershell
.\scripts\root_cause_stream_lab.ps1 `
  -DurationSeconds 120 `
  -VideoOnly
```

Dostępne flagi:

- `-DurationSeconds 120`: czas pojedynczego testu FFmpeg.
- `-OnlyGo2rtc`: tylko restreamy go2rtc.
- `-OnlyDirect`: tylko direct camera RTSP.
- `-WithFrigateComparison`: porównanie Frigate ON/OFF.
- `-WithRecorderComparison`: ręczne porównanie rejestratora ON/OFF.
- `-Quick`: skraca domyślny test do 15 s i ping do 5 próbek, jeśli nie podasz
  własnych wartości.
- `-FfmpegTimeoutSeconds 180`: twardy timeout pojedynczego procesu FFmpeg.
  Domyślnie lab używa `DurationSeconds + 30`, minimum 30 s.
- `-VideoOnly`: FFmpeg używa `-map 0:v:0 -an`, czyli ignoruje audio.
- `-SkipDirectCamera`: pomija direct camera RTSP.
- `-SkipNetwork`: pomija ping do kamer.
- `-AllowDirectCameraRtsp`: świadoma zgoda na direct camera RTSP z sekretami.

Direct camera RTSP jest domyślnie pomijany, dopóki nie podasz
`-AllowDirectCameraRtsp`. Skrypt czyta sekrety z `EZVIZ_SECRETS_ENV_FILE` albo
lokalnego `secrets.local.env`, ale nigdy nie zapisuje pełnego RTSP URL do
raportu.

## Wrappery

```powershell
.\scripts\test_go2rtc_stream.ps1 -Quick -VideoOnly
.\scripts\test_go2rtc_stream.ps1 -DurationSeconds 120 -VideoOnly
.\scripts\test_direct_camera_stream.ps1 -Quick -VideoOnly
.\scripts\test_network_quality.ps1 -PingCount 200
.\scripts\test_recorder_impact.ps1 -DurationSeconds 120 -VideoOnly
```

Manualna lista dla przeglądarki:

```text
scripts/test_browser_decode.md
```

## Test matrix

Direct camera RTSP:

```text
H9C lens1 sub: /Streaming/Channels/102
H9C lens2 sub: /Streaming/Channels/202
C8W sub:       /Streaming/Channels/102
C8C 60 sub A:  /Streaming/Channels/102
C8C 60 sub B:  /ch1/sub
```

go2rtc restream:

```text
lukow_h9c_98_sub
lukow_h9c_98_lens2_sub
lukow_c8w_97_sub
lukow_c8c_60_sub
lukow_c8c_60_sub_ch1
```

C8C 102 zostaje `unstable/experimental`. Nie optymalizuj panelu pod tę kamerę i
nie włączaj jej do domyślnego video walla.

## Direct camera vs go2rtc

Direct camera test omija go2rtc, Frigate i panel:

```powershell
.\scripts\root_cause_stream_lab.ps1 -OnlyDirect -AllowDirectCameraRtsp -DurationSeconds 120 -VideoOnly
```

go2rtc test używa tylko lokalnych restreamów bez sekretów w URL:

```powershell
.\scripts\root_cause_stream_lab.ps1 -OnlyGo2rtc -DurationSeconds 120 -VideoOnly
```

Interpretacja:

- direct FAIL i go2rtc FAIL: szukaj w kamerze, Wi-Fi, LAN, WireGuard albo w
  konkurencji rejestratora/NVR.
- direct OK i go2rtc FAIL: szukaj w konfiguracji go2rtc, pathach albo restreamie.
- direct OK i go2rtc OK, a panel laguje: szukaj w przeglądarce, HEVC decode,
  liczbie aktywnych kafelków albo remountach UI.

## C8C 60 path comparison

Skrypt porównuje:

```text
lukow_c8c_60_sub -> /Streaming/Channels/102
lukow_c8c_60_sub_ch1 -> /ch1/sub
```

Raport wybiera `preferred_sub_path` na podstawie: czy test doszedł do końca,
FPS, speed, EOF i liczby błędów HEVC.

Jeżeli `/ch1/sub` jest stabilniejszy:

```powershell
python -m ezviz_panel.backend stream-override --camera-slug lukow_c8c_60 --role sub --path /ch1/sub
python -m ezviz_panel.backend go2rtc-render-runtime
docker compose restart go2rtc
```

Do `stream-override` podawaj tylko path, nigdy pełny RTSP URL.

## Frigate ON/OFF

Automatyczny wariant:

```powershell
.\scripts\root_cause_stream_lab.ps1 -WithFrigateComparison -DurationSeconds 120 -VideoOnly
```

Skrypt wykona:

```powershell
docker compose up -d frigate
# test go2rtc
docker compose stop frigate
# test go2rtc
```

Jeżeli Frigate OFF daje więcej stabilnych streamów, Frigate zwiększa obciążenie
hosta albo konkuruje o sesje RTSP/go2rtc.

## Rejestrator ON/OFF

Nie automatyzujemy odłączania rejestratora. Tryb jest ręczny:

```powershell
.\scripts\root_cause_stream_lab.ps1 -WithRecorderComparison -DurationSeconds 120 -VideoOnly
```

Procedura:

1. Zostaw rejestrator normalnie włączony.
2. Uruchom test A.
3. Odłącz rejestrator od sieci albo wyłącz pobieranie tych kamer.
4. Odczekaj 60 s.
5. Uruchom test B.
6. Podłącz rejestrator z powrotem.

Nie zostawiaj rejestratora odłączonego, jeśli odpowiada za ważne nagrania.

Jeżeli po wyłączeniu rejestratora streamy są stabilniejsze, problemem może być
limit równoległych sesji RTSP w kamerze, Wi-Fi, switch, NVR albo suma
odbiorców: rejestrator + go2rtc + Frigate + panel.

## LAN vs WireGuard

Test przez WireGuard:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

Test lokalnie w LAN kamer albo na serwerze w Łukowie:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

Porównaj dwa raporty. Jeżeli LAN jest OK, a WireGuard FAIL, problem jest
prawdopodobnie w VPN, routingu, upload/download albo jitterze.

Ping:

```powershell
ping -n 200 192.168.80.98
ping -n 200 192.168.80.97
ping -n 200 192.168.80.60
pathping 192.168.80.98
```

Jeżeli masz host w LAN kamer, można dodać `iperf3`, ale skrypt nie zakłada, że
jest zainstalowany:

```text
iperf3 -s
iperf3 -c <host-w-lan-kamer>
```

Jeżeli cały stack działa na komputerze po WireGuard, topologia wygląda tak:

```text
kamera -> WireGuard -> komputer użytkownika -> go2rtc -> Frigate -> frontend
```

To oznacza, że ingest kamer przechodzi przez VPN. Docelowo stabilniejszy wariant
do sprawdzenia:

```text
kamera -> lokalny serwer/gateway w Łukowie -> go2rtc/Frigate -> panel
```

Wtedy przy kamerach działa ingest i NVR, a zdalnie idzie tylko panel/podgląd.
Tego deploymentu nie zmieniamy w tym etapie.

## Browser / HEVC decode

Manualna instrukcja jest w:

```text
scripts/test_browser_decode.md
```

Najważniejszy sygnał: jeżeli GPU Video Decode nie rośnie, a CPU mocno rośnie,
HEVC/H.265 prawdopodobnie dekoduje się software'owo. Wtedy nawet SUB może
lagować przy kilku kafelkach.

W raporcie zostaje pole:

```json
{
  "browser_decode_notes": ""
}
```

Uzupełnij je ręcznie w notatkach z testu: CPU, GPU Video Decode, GPU 3D, RAM,
sieć dla 1/2/4/6 aktywnych streamów.

## Interpretacja metryk

`connected`: FFmpeg zobaczył wejście RTSP albo pierwsze klatki.

`frames`: liczba klatek odczytanych przez FFmpeg.

`fps`: ostatni FPS z logu FFmpeg.

`speed`: tempo przetwarzania. Około `1.0x` oznacza real-time. Bardzo niskie
wartości przy krótkim czasie i EOF oznaczają niestabilny stream.

`EOF`: stream zakończył się niespodziewanie. Jeżeli EOF pojawia się przed końcem
testu 120 s, traktuj stream jako niestabilny.

`HEVC errors`: ostrzeżenia dekodera H.265. Pojedyncze błędy mogą być akceptowalne,
jeżeli test dochodzi do końca z normalnym FPS. Dużo błędów, niski FPS albo EOF to
sygnał upstream/path/decode.

## Wnioski automatyczne

Raport generuje proste klasyfikacje:

- direct camera FAIL i go2rtc FAIL: kamera, sieć, Wi-Fi, VPN albo rejestrator.
- direct camera OK i go2rtc FAIL: konfiguracja go2rtc/restreamu.
- direct OK, go2rtc OK, panel FAIL: frontend, przeglądarka, HEVC decode albo za
  dużo aktywnych streamów.
- Frigate OFF poprawia wyniki: Frigate zwiększa obciążenie lub konkurencję o
  streamy.
- recorder OFF poprawia wyniki: rejestrator albo dodatkowe sesje RTSP obciążają
  kamerę/sieć.
- LAN OK i WireGuard FAIL: VPN, upload/download, routing albo jitter.
- CPU/GPU dobija: HEVC decode albo za dużo aktywnych streamów.

## Bezpieczeństwo

Sanitizer maskuje:

- `rtsp://user:password@host`
- wartości z `EZVIZ_SECRETS_ENV_FILE`
- verification codes

Do zgłoszeń i debugowania wklejaj `report.md`, `report.json` albo
`go2rtc-logs-sanitized.txt`, nie raw `docker logs`.
