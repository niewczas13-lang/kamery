# Live Smoke Test

Use this after importing and applying the real probe results and generating
`runtime/config/go2rtc/go2rtc.yaml`.

## Start

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_BACKEND_SECRET_KEY = "local-dev-secret-change-me"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"
$env:GO2RTC_API_URL = "http://127.0.0.1:1984"

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

Open:

```text
http://127.0.0.1:8000/debug/streams
```

Frontend MVP:

```powershell
cd apps/web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

The frontend Live Smoke page defaults to substreams only. Main streams are
available from the Streams or Camera Details views after an explicit click/open
action; they are not autoloaded.

## H9C

In go2rtc or the debug page, test:

- `lukow_h9c_98_main`
- `lukow_h9c_98_sub`
- `lukow_h9c_98_lens2_main`
- `lukow_h9c_98_lens2_sub`

Expected: streams are generated and marked with HEVC warnings. Audio metadata may
show AAC.

Direct smoke URLs:

- `http://127.0.0.1:1984/stream.html?src=lukow_h9c_98_sub`
- `http://127.0.0.1:1984/stream.html?src=lukow_h9c_98_lens2_sub`

## H8

Test:

- `lukow_h8_101_main`
- `lukow_h8_101_sub`

Expected: streams are generated and marked with HEVC warnings. Probe metadata
did not detect audio.

Direct smoke URL:

- `http://127.0.0.1:1984/stream.html?src=lukow_h8_101_sub`

## C8W

Test:

- `lukow_c8w_97_main`
- `lukow_c8w_97_sub`

Expected: main and sub are generated when the best current VPN probe has
`/Streaming/Channels/101` and `/Streaming/Channels/102`. If a future import only
has `102`, only the substream is generated.

Direct smoke URL:

- `http://127.0.0.1:1984/stream.html?src=lukow_c8w_97_sub`

## C8C 60

Test:

- `lukow_c8c_60_main`
- `lukow_c8c_60_sub`

Expected: streams are generated after the recheck import. Reliability may show
`degraded` if the earlier full probe had a snapshot timeout.

Direct smoke URL:

- `http://127.0.0.1:1984/stream.html?src=lukow_c8c_60_sub`

## C8C 102

`lukow_c8c_102` is unstable. When it exists in the database and
`CAMERA102_PASSWORD` is configured, the Lukow start scripts render it as an
experimental manual-load live tile. Manual diagnostic flow:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime --include-unstable-streams
docker compose restart go2rtc
```

Then test:

- `http://127.0.0.1:1984/stream.html?src=lukow_c8c_102_main_experimental`

## Direct go2rtc Player

The local go2rtc UI is:

```text
http://127.0.0.1:1984
```

Choose the stream names above. Do not expose this port publicly.

## Snapshot Check

For cameras with video, the backend snapshot endpoint writes to
`runtime/snapshots/` and does not return RTSP credentials:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/cameras/1/snapshot" -Method Post -Headers $headers
```

For control-only/no-video cameras, the endpoint returns `409`.

## Deferred

- Final frontend live grid.
- Production Frigate/NVR.
- Recording.
- Public HTTPS/reverse proxy.
- Press-and-hold PTZ controls and PTZ presets/tours.
- Mass transcode for all cameras.
