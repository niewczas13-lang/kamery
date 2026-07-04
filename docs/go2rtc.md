# go2rtc Runtime

Stage 3A adds a local go2rtc runtime for first live-view smoke tests. It does
not add the final live grid, Frigate/NVR, recording, public RTSP/ONVIF exposure,
or mass transcoding.

## Environment

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_BACKEND_SECRET_KEY = "local-dev-secret-change-me"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"
$env:GO2RTC_API_URL = "http://127.0.0.1:1984"
$env:GO2RTC_CONFIG_PATH = "runtime/config/go2rtc/go2rtc.yaml"
$env:ENABLE_EXPERIMENTAL_TRANSCODE = "false"
```

## Full Local Flow

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend init-db
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe `
  --file probe-results/vpn-full-20260704-000914.json `
  --file probe-results/vpn-recheck-lukow_c8c_60-20260704-001420.json `
  --file probe-results/vpn-recheck-lukow_c8c_102-20260704-001420.json `
  --create-missing `
  --apply `
  --prefer-best
.\.venv\Scripts\python.exe -m ezviz_panel.backend list-streams
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime
docker compose up -d go2rtc
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-health
.\.venv\Scripts\python.exe -m ezviz_panel.backend runserver --host 127.0.0.1 --port 8000
```

## Config Files

- Safe example: `go2rtc.example.yaml`
- Safe preview: `GET /api/v1/config/go2rtc/preview` or `go2rtc-preview`
- Private runtime config: `runtime/config/go2rtc/go2rtc.yaml`

The runtime config resolves secret refs from `EZVIZ_SECRETS_ENV_FILE`, so it may
contain real RTSP credentials. It is ignored by Git and must not be committed.
Do not commit `secrets.local.env`.

## Generated Streams

- `lukow_h9c_98_main`
- `lukow_h9c_98_sub`
- `lukow_h9c_98_lens2_main`
- `lukow_h9c_98_lens2_sub`
- `lukow_h8_101_main`
- `lukow_h8_101_sub`
- `lukow_c8w_97_main`
- `lukow_c8w_97_sub`
- `lukow_c8c_60_main`
- `lukow_c8c_60_sub`

`lukow_c8c_102` is unstable after the current VPN probes and is skipped from the
default runtime. Diagnostics should show it as unstable/experimental.

To include the unstable diagnostic stream for `.102`, render with:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime --include-unstable-streams
```

That may add `lukow_c8c_102_main_experimental` when the best probe has
`/ch1/main`. Do not use unstable streams for the default live grid.

### C8C 60 diagnostic `/ch1/sub`

The current `lukow_c8c_60_sub` can be unstable through go2rtc. A safer candidate
path exists as `/ch1/sub`, but the default alias is not changed until the 120 s
TCP video-only test passes.

Render a temporary diagnostic alias:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime --include-diagnostic-streams
docker compose restart go2rtc
```

This can add:

```text
lukow_c8c_60_sub_ch1 -> /ch1/sub
```

Test it without audio:

```powershell
.\scripts\diagnose_streams.ps1 -DurationSeconds 120 -VideoOnly
```

If `lukow_c8c_60_sub_ch1` survives the test, make `/ch1/sub` the preferred SUB
path:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend stream-override --camera-slug lukow_c8c_60 --role sub --path /ch1/sub
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime
docker compose restart go2rtc
```

Do not pass a full RTSP URL to `stream-override`; it accepts only camera paths
such as `/ch1/sub`.

## HEVC Warning

The working video streams are HEVC/H.265. Browser support varies, so stream
responses and `/debug/streams` mark them as `needs_transcode` with a warning.
Stage 3A does not transcode all cameras.

To enable the single experimental H9C substream fallback:

```powershell
$env:ENABLE_EXPERIMENTAL_TRANSCODE = "true"
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime
docker compose restart go2rtc
```

This adds one test stream, for example `lukow_h9c_98_sub_h264`. Do not enable
mass H.264 transcoding for 25 cameras by default.

## API Checks

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-health
.\.venv\Scripts\python.exe -m ezviz_panel.backend list-streams
```

## Logs

Do not paste raw go2rtc Docker logs. Upstream errors may include full RTSP URLs
with credentials.

Use the sanitizer:

```powershell
.\scripts\go2rtc_logs_sanitized.ps1 -Tail 200
```

Optional follow mode:

```powershell
.\scripts\go2rtc_logs_sanitized.ps1 -Tail 100 -Follow
```

The sanitizer masks `rtsp://user:password@host`, all values from
`EZVIZ_SECRETS_ENV_FILE`, and verification-code style fields.

With the backend running, use:

- `GET /api/v1/streams`
- `GET /api/v1/streams/{stream_name}`
- `POST /api/v1/config/go2rtc/render-runtime`
- `GET /api/v1/go2rtc/health`
- `GET /api/v1/go2rtc/streams`
- `GET /api/v1/diagnostics/live`
- `GET /debug/streams` from the local machine

`/api/v1/diagnostics/live` returns a sanitized summary: backend/go2rtc/Frigate
health, stream count, default active preview limit, stability labels, and HEVC /
C8C warnings. It does not return go2rtc source URLs.

For FFmpeg TCP/video-only diagnostics:

```powershell
.\scripts\diagnose_streams.ps1 -DurationSeconds 120 -VideoOnly
```

Output is written to `runtime/diagnostics/streams-*.txt`.

For root-cause diagnostics, prefer the full lab:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

It writes a sanitized report to
`runtime/diagnostics/root-cause-YYYYMMDD-HHMMSS/` and compares go2rtc against
direct camera RTSP, network ping, Docker stats, optional Frigate ON/OFF and
manual recorder ON/OFF.

Only go2rtc restreams:

```powershell
.\scripts\test_go2rtc_stream.ps1 -DurationSeconds 120 -VideoOnly
```

Direct camera RTSP, with secrets read from `EZVIZ_SECRETS_ENV_FILE` and masked
in output:

```powershell
.\scripts\test_direct_camera_stream.ps1 -DurationSeconds 120 -VideoOnly
```

If direct camera RTSP is stable but go2rtc fails, inspect go2rtc stream config,
the selected path, and restream behavior. If both fail, look upstream: camera,
Wi-Fi/LAN, WireGuard, recorder/NVR, or RTSP session limits.

The public internet should later expose only the panel over HTTPS/reverse proxy,
not go2rtc, RTSP restreams, ONVIF, or camera ports.

For Stage 3B, go2rtc should stay local at `127.0.0.1:1984`. A backend/reverse
proxy boundary for public access is a later stage.
