# Security

## Secret References

Camera verification codes are not stored in the database. Camera rows store only
refs such as:

```text
CAMERA98_PASSWORD
CAMERA98_USER
```

Runtime values are read from `EZVIZ_SECRETS_ENV_FILE`.

API responses may show `rtsp_password_secret_ref` and
`onvif_password_secret_ref`, plus `rtsp_secret_configured` and
`onvif_secret_configured`. They must not show actual verification codes.

## Local Files Not For Git

- `.env`
- `cameras.local.yml`
- `probe-results/`
- `snapshots/`
- `runtime/`
- `runtime/config/go2rtc/go2rtc.yaml`
- `secrets.local.env`

`go2rtc.example.yaml` is safe to commit because it contains placeholder secret
refs only. The generated runtime config is not safe to commit because it may
contain resolved RTSP URLs with real camera verification codes.

## Network

RTSP and ONVIF stay private on LAN/VPN. Do not forward camera ports to the
internet. Later remote access should expose only the HTTPS panel.

The Stage 3A `go2rtc` compose service binds to `127.0.0.1` for local/dev smoke
testing. Do not expose go2rtc, RTSP restreams, ONVIF, or camera ports publicly.

## ONVIF PTZ

PTZ runs locally through ONVIF, without EZVIZ Cloud. The backend resolves
`onvif_password_secret_ref` from `EZVIZ_SECRETS_ENV_FILE` at request time and
does not persist or return resolved passwords. PTZ commands must not be sent
directly from the browser to camera ONVIF ports.

Every movement command uses a short bounded duration and then attempts `stop`.
The default duration is 300 ms and the maximum accepted duration is 1500 ms.
If movement fails after connecting, the backend still attempts stop and returns
a sanitized error. If stop fails after a completed movement, the response keeps
the movement result but includes a sanitized warning.

## Sanitized Results

Sanitized probe output is for sharing/debugging only. It is intentionally not
valid for production import because host/IP and ids may be masked.

`import-probe --create-missing` must be used only with private probe JSON. The
importer creates camera rows with secret refs such as `CAMERA102_PASSWORD`; it
does not copy real passwords or verification codes from probe files.

## Runtime Responses

Safe preview endpoints show `${SECRET_REF}` values. Runtime render responses
show only output path, stream count, skipped camera slugs, unstable camera slugs,
and warnings.
Snapshot failures mask configured secret values before returning ffmpeg stderr.

`--include-unstable-streams` is for local diagnostics only. It may add an
experimental go2rtc stream for an unstable camera, but go2rtc remains bound to
`127.0.0.1` and must not be exposed publicly.

## go2rtc Logs

Do not paste raw `docker compose logs go2rtc`. When a camera upstream fails,
go2rtc can print full RTSP URLs such as `rtsp://admin:<secret>@host:554/path`.

Use:

```powershell
.\scripts\go2rtc_logs_sanitized.ps1 -Tail 200
```

or:

```bash
./scripts/go2rtc_logs_sanitized.sh
```

The sanitizer masks RTSP URL passwords, all values from
`EZVIZ_SECRETS_ENV_FILE`, and verification-code style fields.

## Frigate / NVR

Frigate must stay local/dev only. The compose service binds the UI/API to
`127.0.0.1:5000` and uses the same private Docker network as go2rtc.

Frigate config must use go2rtc restream URLs such as
`rtsp://go2rtc:8554/lukow_h9c_98_sub`, not direct camera RTSP URLs with
credentials. Runtime Frigate config is written to
`runtime/config/frigate/config.yml` and is ignored by Git.

Do not expose Frigate, go2rtc, RTSP restreams, ONVIF, or camera ports publicly.
Public HTTPS/reverse proxy is a later stage and should expose only hardened
backend/frontend surfaces.

## Frontend MVP

Stage 3B stores the bearer token in `localStorage` for local MVP convenience.
Do not use this as the final public deployment session model. The frontend must
use only backend API responses and go2rtc stream names; it must not read
`runtime/config/go2rtc/go2rtc.yaml`, raw logs, or `secrets.local.env`.

## Operator Console

Stage 5B keeps the same security boundary while improving the UI:

- `Konsola podglądu` builds player URLs from stream names only.
- The frontend never receives direct camera RTSP URLs.
- MAIN/SUB quality selection is a stream-name choice, not a credential choice.
- Focus mode, H9C dual-lens tabs, event drawer, and PTZ joystick all use backend
  APIs.
- PTZ commands are sent to the backend only; the browser never talks to camera
  ONVIF ports.
- Raw go2rtc logs and raw Frigate runtime config are not shown in the panel.

Etap 6A public HTTPS/reverse proxy is deferred. Until then, backend, frontend,
go2rtc, and Frigate stay local/dev or behind the user's VPN.

## Operator Console Etap 5C

The video wall uses logical tile ids and go2rtc stream names only. It must not
receive or store:

- RTSP URLs,
- camera passwords,
- verification codes,
- values from `EZVIZ_SECRETS_ENV_FILE`,
- `runtime/config/go2rtc/go2rtc.yaml`,
- raw go2rtc logs,
- raw Frigate runtime config.

Saved layouts in `localStorage` store tile ids, order, and hidden tile ids. They
do not store credentials or stream URLs. Event drawer data comes through backend
Frigate proxy endpoints and sanitized public Frigate media URLs.

Etap 6A remains postponed. Do not expose go2rtc, Frigate, RTSP restreams, ONVIF,
or camera ports publicly while working on the local operator console.

## Operator Console Etap 5D

Friendly camera names, tile names, custom layout order, monitor mode, fullscreen
mode, and H9C PTZ target lens are local UI preferences only. The allowed
`localStorage` values are:

- `cameraDisplayNames`,
- `tileDisplayNames`,
- layout ids/order/hidden tile ids/layout size/quality mode/split lens setting,
- H9C PTZ target lens label.

The frontend sanitizer rejects display names or layout values that look like
RTSP URLs or credential-bearing strings. Do not store, paste, or commit:

- raw RTSP URLs,
- camera passwords,
- EZVIZ verification codes,
- values from `EZVIZ_SECRETS_ENV_FILE`,
- `secrets.local.env`,
- `runtime/config/go2rtc/go2rtc.yaml`,
- raw `docker compose logs go2rtc`.

### Polityka dźwięku

The video wall, fullscreen wall, monitor mode, H9C dual-lens grid tiles, and
stream previews are always muted. They request `muted=1` / `media=video` from
go2rtc and do not grant iframe autoplay-audio permission. The UI does not
provide a global audio-on action.

Focus mode starts muted. A manual `Włącz dźwięk` click can enable audio only for
one active player. Closing focus mode, switching camera, switching lens, or
refreshing the browser returns to muted. H9C split view can enable audio only
for the active lens; the second lens remains muted.

go2rtc and Frigate remain local/dev services or must sit behind the backend or a
future reverse proxy. Etap 6A public HTTPS/reverse proxy is still deferred.

### Blokada ruchu PTZ

The frontend must not start automatic PTZ patrols, tours, or tracking. Focus
mode starts with movement locked. Non-stop PTZ commands are blocked until the
operator explicitly unlocks movement for the current focus session. `STOP`
remains available while locked so an already-moving camera can be stopped.

## Operator Console Etap 5E

Stream diagnostics are allowed only as sanitized metadata:

- tile ids,
- go2rtc stream names,
- quality labels,
- mount/reload/src-change counters,
- active-limit/offscreen flags,
- stability labels.

The per-tile diagnostics overlay and `GET /api/v1/diagnostics/live` must not
show RTSP source URLs, camera passwords, verification codes, raw go2rtc logs,
`secrets.local.env`, or `runtime/config/go2rtc/go2rtc.yaml`.

Use `scripts/diagnose_streams.ps1` for local restream FFmpeg tests and
`scripts/diagnose_docker.ps1` for Docker load checks. Both write to
`runtime/diagnostics/`, which remains non-committable runtime output.

Use `scripts/root_cause_stream_lab.ps1` for deeper lag diagnostics. Its reports
and FFmpeg logs are written under `runtime/diagnostics/root-cause-*` and must
stay out of Git. Direct camera RTSP requires `-AllowDirectCameraRtsp`; the
script must read secrets from `EZVIZ_SECRETS_ENV_FILE` or the local secrets file
and must write only masked RTSP URLs, masked secret values, and masked
verification codes.
