# Architecture

Current layers:

- `ezviz_panel.camera_probe`: local RTSP/ONVIF probe and sanitized output.
- `ezviz_panel.backend`: FastAPI app, SQLite/SQLAlchemy models, auth, probe import.
- `ezviz_panel.backend.onvif_ptz`: mockable ONVIF PTZ adapter and safe movement
  orchestration.
- `apps/web`: minimal React/Vite admin frontend for local MVP.
- `runtime/`: local private database/config/output directory.
- `go2rtc`: local Docker runtime using generated config from the backend.
- `frigate`: local NVR Docker runtime using go2rtc restreams as sources.

Etap 2A stores capability metadata from probe results:

- stream paths,
- HEVC/AAC metadata,
- ONVIF/PTZ status,
- snapshot support,
- audio support,
- control-only cameras.

go2rtc preview is rendered from database camera rows and uses secret refs such as
`${CAMERA98_PASSWORD}`. Runtime config generation resolves those refs only when
writing `runtime/config/go2rtc/go2rtc.yaml`, which is ignored by Git.

Etap 3A generates streams only for cameras with usable video:

- `lukow_h9c_98`: main, sub, lens2 main, lens2 sub,
- `lukow_h8_101`: main, sub,
- `lukow_c8w_97`: substream only.

Control-only C8C cameras remain visible in diagnostics as no-video/PTZ-capable
cameras and do not receive go2rtc streams.

Etap 3B frontend reads only backend API data and go2rtc stream names. It does
not read runtime config files, raw go2rtc logs, RTSP URLs, or secret env files.
Live Smoke defaults to known substreams and loads embedded players only after a
click.

Etap 4A adds real PTZ through local ONVIF for cameras with `has_ptz=true`. The
backend resolves ONVIF secret refs at runtime, chooses the first ONVIF profile
with PTZ configuration, sends `ContinuousMove` for short click-to-move commands,
and always attempts `Stop` after movement.

Etap 5A adds Frigate/NVR in the same Docker Compose network as go2rtc:

```text
EZVIZ cameras -> go2rtc -> Frigate -> backend API -> frontend
```

Frigate config is generated from database camera rows and references only local
go2rtc stream names such as `rtsp://go2rtc:8554/lukow_h9c_98_sub`. Real camera
RTSP credentials remain only in the ignored go2rtc runtime config.

Deferred to later stages:

- live grid,
- production go2rtc hardening,
- final browser playback strategy for HEVC,
- mass transcoding,
- production Frigate/NVR integration,
- press-and-hold PTZ controls and advanced presets/tours.
- full 25-camera NVR, long retention, and hardware accelerated detection tuning.
