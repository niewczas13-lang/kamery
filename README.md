# EZVIZ Panel

Local-first panel for EZVIZ cameras. Current scope is Etap 5B:

- `camera-probe` for RTSP/ONVIF discovery,
- FastAPI backend core,
- SQLite database for dev/test,
- admin auth,
- secret references instead of stored camera passwords,
- probe result import/apply,
- go2rtc YAML preview without real secrets,
- generated private go2rtc runtime config,
- local go2rtc Docker runtime for first live-view smoke tests,
- Polish React/Vite operator console in `apps/web`,
- local ONVIF PTZ backend and safe short PTZ smoke tests.
- local Frigate/NVR MVP using go2rtc restreams.
- simplified stable Live Console, muted focus mode, PTZ joystick, and H9C dual-lens UX.

The 25-camera production grid, public RTSP/ONVIF exposure, reverse proxy/HTTPS
Etap 6A, two-way audio, long retention, and mass transcoding are intentionally
deferred.

## Safety Rules

- Keep real camera secrets only in a private env file.
- Keep `cameras.local.yml`, `probe-results/`, `snapshots/`, and `runtime/` out of Git.
- Store camera secrets in the database only as refs such as `CAMERA98_PASSWORD`.
- Never expose RTSP/ONVIF camera ports to the public internet.
- Do not paste raw `docker compose logs go2rtc`; use sanitized log scripts.
- Run PTZ only through the backend/CLI so every movement gets an automatic stop.

## Setup

Create and install local backend dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Set environment values for the current shell:

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_BACKEND_SECRET_KEY = "local-dev-secret-change-me"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"
$env:GO2RTC_API_URL = "http://127.0.0.1:1984"
```

## Camera Probe

Check tools:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.camera_probe verify-tools
```

Run all cameras:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.camera_probe run --config cameras.local.yml --timeout 8 --secrets-env-file $env:EZVIZ_SECRETS_ENV_FILE --output probe-results/all.json
```

Create share-safe output:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.camera_probe sanitize-result probe-results/all.json --output probe-results/all.sanitized.json
```

## Backend

Initialize database:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend init-db
```

Create admin:

```powershell
$env:ADMIN_PASSWORD = "choose-a-local-password"
.\.venv\Scripts\python.exe -m ezviz_panel.backend create-admin --username admin --password-env ADMIN_PASSWORD
```

Run API:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend runserver --host 127.0.0.1 --port 8000
```

Docs are available at:

```text
http://127.0.0.1:8000/docs
```

## First API Calls

Login:

```powershell
$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method Post -ContentType "application/json" -Body '{"username":"admin","password":"choose-a-local-password"}'
$headers = @{ Authorization = "Bearer $($login.access_token)" }
```

Create location:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/locations" -Method Post -Headers $headers -ContentType "application/json" -Body '{"name":"Lukow","slug":"lukow","network_cidr":"192.168.80.0/24"}'
```

Create first camera:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/cameras" -Method Post -Headers $headers -ContentType "application/json" -Body '{"location_id":1,"name":"H9C 98","slug":"lukow_h9c_98","model":"CS-H9c-R100-8G55WKFL","host":"192.168.80.98","rtsp_password_secret_ref":"CAMERA98_PASSWORD","onvif_password_secret_ref":"CAMERA98_PASSWORD"}'
```

Import a private probe result for that camera:

```powershell
$probe = Get-Content -LiteralPath "probe-results/all.json" -Raw
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/cameras/1/probe-results/import" -Method Post -Headers $headers -ContentType "application/json" -Body $probe
```

Apply a probe result:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/cameras/1/apply-probe-result/1" -Method Post -Headers $headers
```

Preview go2rtc:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/config/go2rtc/preview" -Method Get -Headers $headers
```

## Backend CLI

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend init-db
.\.venv\Scripts\python.exe -m ezviz_panel.backend create-admin --username admin --password-env ADMIN_PASSWORD
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe --file probe-results/vpn-full-20260704-000914.json --create-missing --apply
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe --file probe-results/vpn-recheck-lukow_c8c_60-20260704-001420.json --file probe-results/vpn-recheck-lukow_c8c_102-20260704-001420.json --apply --prefer-best
.\.venv\Scripts\python.exe -m ezviz_panel.backend list-streams
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-preview
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime
docker compose up -d go2rtc
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-health
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-probe --camera-slug lukow_h9c_98
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-test --camera-slug lukow_h9c_98 --command left --duration-ms 300
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-test --camera-slug lukow_c8c_60 --command right --duration-ms 300
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-preview
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-render-runtime
docker compose up -d go2rtc frigate
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-health
```

The same bootstrap can be run as one multi-file import:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe `
  --file probe-results/vpn-full-20260704-000914.json `
  --file probe-results/vpn-recheck-lukow_c8c_60-20260704-001420.json `
  --file probe-results/vpn-recheck-lukow_c8c_102-20260704-001420.json `
  --create-missing `
  --apply `
  --prefer-best
```

## go2rtc Local Runtime

Generate the safe preview:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-preview
```

Generate the private runtime config. This resolves secret refs from
`EZVIZ_SECRETS_ENV_FILE` and writes `runtime/config/go2rtc/go2rtc.yaml`, which is
ignored by Git:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime
```

Start local go2rtc:

```powershell
docker compose up -d go2rtc
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-health
```

Open diagnostics after the backend is running:

```text
http://127.0.0.1:8000/debug/streams
```

Read go2rtc logs only through the sanitizer:

```powershell
.\scripts\go2rtc_logs_sanitized.ps1 -Tail 200
```

Do not paste raw go2rtc logs, because upstream errors can include full RTSP URLs
with credentials.

## Frontend / Operator Console

Start the local admin UI:

```powershell
cd apps/web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The frontend uses `VITE_API_BASE_URL`, `VITE_GO2RTC_PUBLIC_URL`, and
`VITE_FRIGATE_PUBLIC_URL`, defaulting to `http://127.0.0.1:8000`,
`http://127.0.0.1:1984`, and `http://127.0.0.1:5000`. It never receives RTSP
URLs or camera password values.

The UI is Polish-first. Main operator work happens in `Konsola podglądu`:

- grid cameras are locked to SUB/fast playback for stability,
- focus mode is also muted and uses the stable fast profile by default,
- MAIN streams remain useful for recording and direct diagnostics, not the default wall,
- H9C shows `Obiektyw 1`, `Obiektyw 2`, and `Widok podzielony`,
- PTZ uses a joystick-style safe nudge control for cameras with `has_ptz=true`.

See [docs/go2rtc.md](docs/go2rtc.md) and
[docs/live-smoke-test.md](docs/live-smoke-test.md) for the live-view smoke-test
flow. See [docs/ptz.md](docs/ptz.md) for ONVIF PTZ testing and
[docs/frigate.md](docs/frigate.md) for NVR setup.

## Frigate / NVR MVP

Frigate reads only local go2rtc restreams such as
`rtsp://go2rtc:8554/lukow_h9c_98_sub`. It does not receive direct camera RTSP
URLs or camera passwords.

Generate the local Frigate config:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-render-runtime
```

Start NVR services:

```powershell
docker compose up -d go2rtc frigate
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-health
```

Local Frigate UI:

```text
http://127.0.0.1:5000
```

The panel exposes NVR, Events, and Recordings views through the backend. Runtime
Frigate config lives at `runtime/config/frigate/config.yml` and is ignored by
Git.

Frigate is the NVR engine, not the primary operator UI. The primary UI is EZVIZ
Panel at:

```text
http://127.0.0.1:5173
```

## Current VPN Probe Summary

- `lukow_h9c_98`: stable dual-lens camera, 4 default streams, HEVC, AAC audio, ONVIF/PTZ.
- `lukow_h8_101`: stable camera, 2 default streams, HEVC, ONVIF/PTZ, no audio detected.
- `lukow_c8w_97`: video works, 2 default streams when the best probe has 101/102, ONVIF/PTZ unavailable or unknown.
- `lukow_c8c_60`: works for manual checks, ONVIF/PTZ, AAC audio; direct RTSP is unstable over longer runs, so it is excluded from default smoke wall and Frigate/NVR until the local link is stable.
- `lukow_c8c_102`: experimental/unstable; keep it out of the default video wall until a stable SUB stream is confirmed.

HEVC playback in browsers is not solved yet. Etap 3 must handle go2rtc playback
and possible fallback/transcoding.

PTZ is enabled only where probe/import marks `has_ptz=true`. H9C 98 and C8C 60
are the stable PTZ smoke targets. C8W 97 is not shown as real PTZ unless a later
probe confirms it. C8C 102 remains experimental/unstable. H8 101 may be blocked
locally until `CAMERA101_PASSWORD` is present.

Frigate/NVR defaults include H9C lens1, H9C lens2, and C8W 97. C8C 60 is
omitted until direct RTSP is stable in the Lukow LAN. H8 101 is omitted until
`CAMERA101_PASSWORD` is available. C8C 102 stays experimental and should not be
part of the default live wall or NVR target set in this stage.

## Etap 5C Operator Video Wall

`Konsola podglądu` is now the main operator video wall. It separates a physical
camera from a logical preview window: H9C can appear as `Obiektyw 1` and
`Obiektyw 2`, while focus mode still treats it as one PTZ device.

- normal tiles show mostly video, title, and compact badges,
- the live wall exposes only location filtering plus layout/active-preview count,
- quality is not operator-selectable in the wall; it is locked to SUB/fast streams,
- video wall playback uses the stable go2rtc mode and stays muted,
- H9C lenses are shown as separate preview windows by default,
- cameras without video stay out of the default grid,
- Frigate events are not overlaid on the live wall; use Events/Recordings/focus timeline,
- Etap 6A public HTTPS/reverse proxy remains deferred.

## Etap 5D Operator Polish

`Konsola podglądu` adds daily-operator polish while staying local-only:

- `Zmień nazwę` lets the operator set friendly camera/tile labels in
  `localStorage` keys `cameraDisplayNames` and `tileDisplayNames`.
- Layout is intentionally simple in the live wall: use `Auto / 1 / 2 / 4 / 6 / 9`
  and the active-preview limit. Saved layout editing is disabled in this stage.
- Fullscreen/monitor/event-drawer controls were removed from the main wall to
  keep the operator surface stable.
- Recent Frigate events are available in the Events view and focus mode mini
  timeline, but they do not highlight live tiles.
- H9C focus mode includes `PTZ steruje` with `Obiektyw 1`, `Obiektyw 2`, or
  `Nie wiem / do sprawdzenia`; this is local UI state, not a model assumption.
- PTZ movement has a session-only `Blokada ruchu PTZ`. The panel starts locked,
  does not run patrol/autotracking, and allows `STOP` even while movement is
  locked.

### Polityka dźwięku

The video wall and focus mode are muted. Stream previews request `muted=1` /
`media=video` and do not grant iframe autoplay-audio permission. There is no
global or focus-mode action to enable camera audio in the operator UI.

## Etap 5E Stream Stability

`Konsola podglądu` now protects the browser from loading every HEVC iframe at
once:

- `Aktywne podglądy` defaults to `6` with options `2 / 4 / 6 / 9`.
- Tiles outside the active limit render `Podgląd wstrzymany` and load only after
  `Kliknij, aby załadować`.
- Stream diagnostics are not shown in the operator wall. Use the diagnostics
  scripts and sanitized logs when debugging.
- The wall uses stable `tile_id` React keys. Player `src` changes only when the
  stream name, audio policy, or retry token changes.

C8C 60 has a diagnostic go2rtc alias for `/ch1/sub`, but the default
`lukow_c8c_60_sub` is not changed until the TCP video-only 120 s test passes:

```powershell
python -m ezviz_panel.backend go2rtc-render-runtime --include-diagnostic-streams
docker compose restart go2rtc
.\scripts\diagnose_streams.ps1 -DurationSeconds 120 -VideoOnly
```

If `lukow_c8c_60_sub_ch1` is stable, set it as the preferred SUB path:

```powershell
python -m ezviz_panel.backend stream-override --camera-slug lukow_c8c_60 --role sub --path /ch1/sub
python -m ezviz_panel.backend go2rtc-render-runtime
docker compose restart go2rtc
```

To compare Frigate load impact:

```powershell
docker compose stop frigate
```

Then test the panel for 5 minutes. If lag disappears, inspect
`.\scripts\diagnose_docker.ps1` output and reduce competing stream consumers.

## Etap 5F Root Cause Lab

Quick smoke:

```powershell
.\scripts\root_cause_stream_lab.ps1 -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly
```

For repeatable lag root-cause diagnostics:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

The full 120 s matrix is intentionally long: 5 go2rtc streams alone take about
10 minutes. The script prints progress per stream and writes partial sanitized
logs while running.

The lab writes sanitized Markdown/JSON reports to
`runtime/diagnostics/root-cause-YYYYMMDD-HHMMSS/` and compares go2rtc, optional
direct camera RTSP, C8C 60 path variants, network ping, Docker stats, optional
Frigate ON/OFF, and manual recorder ON/OFF. Direct camera RTSP requires:

```powershell
.\scripts\root_cause_stream_lab.ps1 -OnlyDirect -AllowDirectCameraRtsp -DurationSeconds 120 -VideoOnly
```

See [docs/root-cause-stream-lab.md](docs/root-cause-stream-lab.md),
[docs/networking.md](docs/networking.md), and
[docs/troubleshooting-streams.md](docs/troubleshooting-streams.md). Do not paste
raw go2rtc logs or commit runtime reports/configs.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall -q src tests
```
