# Camera Probe

`camera-probe` is the first MVP tool for EZVIZ Panel. It checks real cameras
before the dashboard exists and keeps secrets out of logs and saved output.

## Commands

Check FFmpeg tools:

```bash
python -m ezviz_panel.camera_probe verify-tools
```

Run one camera:

```bash
python -m ezviz_panel.camera_probe run --config cameras.local.yml --camera-id lukow_h9c_98 --timeout 8 --secrets-env-file "C:\Users\Pawel Z\OneDrive\Documents\kamery podgląd\config\secrets.local.env" --output probe-results/lukow_h9c_98.json
```

Run all enabled cameras:

```bash
python -m ezviz_panel.camera_probe run --config cameras.local.yml --timeout 8 --secrets-env-file "C:\Users\Pawel Z\OneDrive\Documents\kamery podgląd\config\secrets.local.env" --output probe-results/all.json
```

Create a sanitized share file:

```bash
python -m ezviz_panel.camera_probe sanitize-result probe-results/lukow_h9c_01.json --output probe-results/lukow_h9c_01.sanitized.json
```

## Config file

Use `cameras.example.yml` as the template and create `cameras.local.yml`.
`cameras.local.yml` is ignored by Git because it contains private IP addresses
and verification codes.

The current dependency-free parser supports the example shape: top-level
`locations` and `cameras` lists with scalar fields.

Credential fields may be literals (`rtsp_password`) or references to a private
env file (`rtsp_password_env`). When using `*_env`, pass `--secrets-env-file`.

## What is checked

For each enabled camera:

- host DNS/IP resolution,
- ping when the system supports it,
- TCP port `554` for RTSP,
- RTSP stream metadata through `ffprobe`,
- video codec, audio codec, resolution, FPS, bitrate, and audio presence,
- stream role guess for known EZVIZ/Hikvision paths,
- snapshot capture from the first working RTSP stream through `ffmpeg`,
- common ONVIF ports: `80`, `8000`, `8080`, `8899`,
- ONVIF device capabilities and media profiles when the camera responds,
- PTZ and audio-output hints from ONVIF responses.

## RTSP result fields

Each item in `rtsp_path_results` includes:

- `path`
- `stream_role`
- `video_codec`
- `audio_codec`
- `resolution`
- `fps`
- `bitrate`
- `has_audio`
- `probe_duration_ms`
- `error`

`working_rtsp_paths` is the subset where `error` is `null`.

## ONVIF result fields

The top-level camera result includes:

- `onvif_reachable`
- `onvif_status`
- `onvif_open_ports`
- `onvif_port_results`
- `onvif_profiles_detected`
- `onvif_profiles_status`
- `ptz_supported`
- `ptz_status`

An ONVIF failure does not stop RTSP probing.

## Snapshot behavior

Snapshots are captured only from working RTSP streams. The default directory is:

```text
snapshots/probe/
```

This directory is ignored by Git.

## Security behavior

Private probe output masks credentials and full RTSP URLs with credentials.
Sanitized output additionally masks host/IP values, serials, camera ids,
location ids, camera names, and snapshot paths so it can be pasted into a
support thread.
