# Probe Import

Etap 2A imports private `camera-probe` JSON into the database. Use private
`probe-results/all.json`, not `all.sanitized.json`.

Sanitized results are rejected because they may contain masked camera ids or
hosts such as:

```text
10.20.1.xxx
dem****01
<snapshot_path>
```

## Import By API

```powershell
$probe = Get-Content -LiteralPath "probe-results/all.json" -Raw
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/cameras/1/probe-results/import" -Method Post -Headers $headers -ContentType "application/json" -Body $probe
```

Apply after review:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/cameras/1/apply-probe-result/1" -Method Post -Headers $headers
```

Import stores raw JSON and a sanitized copy. Applying is a separate action so a
probe does not silently overwrite camera configuration.

## Bootstrap By CLI

By default, CLI import only imports probe rows for cameras that already exist.
This keeps accidental production imports safe:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe --file probe-results/vpn-full-20260704-000914.json --apply
```

For a first local bootstrap, use `--create-missing` explicitly:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe --file probe-results/vpn-full-20260704-000914.json --create-missing --apply
```

This creates missing locations and cameras from private probe metadata. Camera
passwords are not stored; the importer derives secret refs from the camera host
or id, for example `CAMERA98_PASSWORD`.

Multiple probe files may be imported together. `--prefer-best` stores every
probe result, then applies the best scored result for each camera instead of
letting a later timeout overwrite a better run:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe `
  --file probe-results/vpn-full-20260704-000914.json `
  --file probe-results/vpn-recheck-lukow_c8c_60-20260704-001420.json `
  --file probe-results/vpn-recheck-lukow_c8c_102-20260704-001420.json `
  --create-missing `
  --apply `
  --prefer-best
```

Scoring prefers `ok` over `partial` over `failed`, more working RTSP paths,
snapshot support, ONVIF/PTZ, audio, fewer errors, shorter probes, and
`/Streaming/Channels/101` / `102` over `/ch1/main` / `/ch1/sub` when both work.

## Stream Selection

H9C:

- main: `/Streaming/Channels/101`
- sub: `/Streaming/Channels/102`
- lens 2 main: `/Streaming/Channels/201`
- lens 2 sub: `/Streaming/Channels/202`

Normal cameras:

- main: `/Streaming/Channels/101`, fallback `/ch1/main`
- sub: `/Streaming/Channels/102`, fallback `/ch1/sub`

C8W partial/substream-only keeps `main_stream_path = null` and sets
`sub_stream_path = /Streaming/Channels/102`.

C8C control-only keeps RTSP paths empty, sets `video_status = unavailable`, and
keeps PTZ/ONVIF capability.

## Statuses

- `video_status = ok`: a main stream is available.
- `video_status = partial`: only a partial stream set is available.
- `video_status = unavailable`: control works but video does not.
- `control_status = ptz_ok`: ONVIF/PTZ was detected.
- `probe_status = ok | partial | failed | unknown`: copied from probe.
- `reliability_status = unknown | stable | degraded | unstable`: computed from
  probe history. Unstable cameras are skipped from default go2rtc runtime.
