# Frigate / NVR MVP

Stage 5A adds a local Frigate service for short-retention NVR smoke testing.
Frigate reads from go2rtc restreams, not from EZVIZ cameras directly.

## Why go2rtc Restreams

The private camera RTSP credentials live only in the ignored go2rtc runtime
config. Frigate receives local Docker-network URLs:

```text
rtsp://go2rtc:8554/lukow_h9c_98_sub
rtsp://go2rtc:8554/lukow_h9c_98_main
```

This keeps verification codes and camera passwords out of Frigate config,
backend responses, and the frontend.

## Generate Config

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_BACKEND_SECRET_KEY = "local-dev-secret-change-me"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"
$env:GO2RTC_API_URL = "http://127.0.0.1:1984"
$env:FRIGATE_API_URL = "http://127.0.0.1:5000"

python -m ezviz_panel.backend go2rtc-render-runtime
python -m ezviz_panel.backend frigate-preview
python -m ezviz_panel.backend frigate-render-runtime
```

Runtime config:

```text
runtime/config/frigate/config.yml
```

This path is ignored by Git.

## Start

```powershell
docker compose up -d go2rtc frigate
python -m ezviz_panel.backend go2rtc-health
python -m ezviz_panel.backend frigate-health
python -m ezviz_panel.backend runserver
```

Local Frigate UI:

```text
http://127.0.0.1:5000
```

Panel NVR dashboard:

```text
http://127.0.0.1:5173
```

Use the NVR, Events, and Recordings tabs.

## Cameras Enabled

- `lukow_h9c_98`: lens1, detect from substream, record from main stream, 2-day event retention.
- `lukow_h9c_98_lens2`: lens2, detect from lens2 substream, record from lens2 main stream, 2-day event retention.
- `lukow_c8w_97`: detect from substream; record from main stream when present, otherwise substream; 1-day event retention.
- `lukow_c8c_60`: excluded from default Frigate/NVR after direct RTSP instability; keep it manual until the Lukow LAN link is stable.

Skipped:

- `lukow_h8_101`: omitted until `CAMERA101_PASSWORD` is available.
- `lukow_c8c_102`: unstable/experimental, disabled by default.

## Recording Policy

Camera Details includes a Recording Policy section. Supported modes:

- `disabled`
- `events_only`
- `continuous`
- `continuous_selected_hours`

Retention is validated from 1 to 30 days. Stage 5A defaults are intentionally
short because the current system disk is small.

`continuous_selected_hours` is accepted as a policy mode for the next scheduler
step, but Stage 5A does not invent Frigate schedule fields. Runtime config emits
a warning and keeps event-based retention until selected-hour rules exist.

## Event Sensitivity

Frigate remains enabled as the local NVR/events engine, but the main operator
video wall does not show raw Frigate event overlays or an event drawer. Events
and recordings stay in the dedicated NVR, Events, Recordings, and focus timeline
views.

Generated runtime config uses less sensitive defaults than Frigate's baseline:

```yaml
motion:
  threshold: 45
  contour_area: 35
objects:
  track:
    - person
  filters:
    person:
      min_score: 0.7
      threshold: 0.85
```

If events are still too noisy in the Lukow LAN, raise `motion.threshold` or
`motion.contour_area` first. If real person events disappear, lower the person
filter thresholds slightly.

## HEVC Warning

Current EZVIZ streams are HEVC/H.265. Stage 5A does not mass-transcode. Frigate
may record the streams, but browser playback can depend on browser/device
support. A single H.264 fallback/transcode smoke stream can be added later.

## Quality roles

SUB is optimized for detection and multi-camera grid preview. It can look weak,
often around `768x432`. MAIN is the high-quality stream for focus/fullscreen and
recording, often `2560x1440` or `2880x1620`.

Expected Frigate mapping:

```text
lukow_h9c_98: detect lukow_h9c_98_sub, record lukow_h9c_98_main
lukow_h9c_98_lens2: detect lukow_h9c_98_lens2_sub, record lukow_h9c_98_lens2_main
lukow_c8w_97: detect lukow_c8w_97_sub, record lukow_c8w_97_main if present, else sub
lukow_c8c_60: skipped by default until direct RTSP is stable in the Lukow LAN
```

The operator panel exposes this as:

```text
Detekcja: szybki strumień
Nagrania: wysoka jakość
```

or, when MAIN is missing:

```text
Nagrywanie używa szybkiego strumienia, bo strumień wysokiej jakości jest niedostępny.
```

Frigate UI can still be useful for diagnostics, but it is not the primary
operator UX. EZVIZ Panel owns the stable muted live wall and focus mode.

## Lag diagnostics

Frigate is another stream consumer. If the video wall lags even on SUB streams,
compare the panel with Frigate stopped:

```powershell
docker compose stop frigate
```

Use the panel for 5 minutes. If lag disappears, the likely cause is host load,
GPU/browser pressure, or stream competition between go2rtc, Frigate, and the
wall. Capture a safe diagnostic bundle:

```powershell
.\scripts\diagnose_docker.ps1
```

The script writes `runtime/diagnostics/docker-*.txt` with `docker compose ps`,
`docker stats --no-stream`, sanitized go2rtc logs, go2rtc health, and Frigate
health. Do not paste raw go2rtc logs.

For a repeatable root-cause comparison:

```powershell
.\scripts\root_cause_stream_lab.ps1 -WithFrigateComparison -DurationSeconds 120 -VideoOnly
```

The lab tests go2rtc streams with Frigate ON, stops Frigate, tests the same
streams again, and writes `frigate-impact-results.json` plus the main
`report.md` and `report.json`.

Interpretation:

- Frigate OFF improves stability: Frigate adds load or competes for stream
  sessions.
- Frigate ON and OFF are both unstable: look at camera, Wi-Fi/LAN, WireGuard,
  go2rtc path, recorder/NVR, or RTSP session limits.
- Frigate ON and OFF are stable but the browser lags: check HEVC/H.265 decode,
  GPU Video Decode, CPU, RAM, and active preview limit in the panel.

Do not expose Frigate publicly in this stage. Keep Frigate local or behind the
backend/reverse proxy boundary planned for a later stage.
