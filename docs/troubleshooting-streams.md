# Stream Troubleshooting

This guide is for local LAN/VPN diagnostics. Do not expose go2rtc, Frigate,
RTSP, ONVIF, or camera ports publicly.

## Why SUB can still lag

SUB streams are smaller, but they can still be HEVC/H.265, include audio, and
compete with Frigate or other viewers. Several browser iframes decoding HEVC at
once can overload the browser/GPU even at `768x432`.

## HEVC/H.265 matters

The current EZVIZ streams are HEVC/H.265. go2rtc can restream them, but browser
playback depends on browser/device support. Warnings such as `PPS id out of
range`, `Could not find ref with POC`, or `Skipping invalid undecodable NALU`
mean the stream can contain imperfect HEVC frames. If FFmpeg survives 120 s, the
stream can still be usable despite warnings.

## Frontend vs go2rtc

Use these rules:

- The generated go2rtc runtime preloads wall SUB streams as video-only. This
  reduces cold starts, but it will not mask long RTSP EOFs or a camera link that
  stops producing frames.

- If FFmpeg with TCP/video-only fails with EOF, the problem is upstream/go2rtc,
  not only React.
- If FFmpeg runs 120 s but the panel reloads players, inspect the live wall
  diagnostics overlay for mount count and src changes.
- Hover, event drawer, health polling, and Frigate event polling should not
  increase `src changes`.
- A high `mount count` means the tile was remounted; a high `reload count` means
  the operator clicked `Ponów`.

## Root Cause Lab

For a full root-cause pass, use:

```powershell
.\scripts\root_cause_stream_lab.ps1 -DurationSeconds 120 -VideoOnly
```

For a quick smoke first:

```powershell
.\scripts\root_cause_stream_lab.ps1 -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly
```

The full 120 s pass is expected to take at least about 10 minutes for go2rtc
alone, because streams are tested one after another.

This creates `runtime/diagnostics/root-cause-YYYYMMDD-HHMMSS/report.md` and
`report.json`. The lab compares direct camera RTSP, go2rtc restreams, C8C 60
paths, network ping, Docker stats, optional Frigate ON/OFF, and optional
recorder ON/OFF. It sanitizes RTSP URLs, secret values from
`EZVIZ_SECRETS_ENV_FILE`, and verification codes.

Use the focused wrappers when needed:

```powershell
.\scripts\test_go2rtc_stream.ps1 -DurationSeconds 120 -VideoOnly
.\scripts\test_direct_camera_stream.ps1 -DurationSeconds 120 -VideoOnly
.\scripts\test_network_quality.ps1 -PingCount 200
.\scripts\test_recorder_impact.ps1 -DurationSeconds 120 -VideoOnly
```

See `docs/root-cause-stream-lab.md` for the full procedure.

## FFmpeg TCP test

Always force TCP. UDP-like setup can fail with `461 Unsupported transport`.

```powershell
ffmpeg -rtsp_transport tcp -hide_banner -i "rtsp://127.0.0.1:8554/lukow_h9c_98_sub" -t 120 -f null -
```

## Video-only test

Use `-map 0:v:0 -an` to ignore audio while testing video stability:

```powershell
ffmpeg -rtsp_transport tcp -hide_banner -i "rtsp://127.0.0.1:8554/lukow_h9c_98_sub" -map 0:v:0 -an -t 120 -f null -
```

Or run the helper:

```powershell
.\scripts\diagnose_streams.ps1 -DurationSeconds 120 -VideoOnly
```

Output goes to `runtime/diagnostics/streams-*.txt`.

## C8C 60 `/ch1/sub`

The default `lukow_c8c_60_sub` can be unstable. Add the diagnostic alias:

```powershell
python -m ezviz_panel.backend go2rtc-render-runtime --include-diagnostic-streams
docker compose restart go2rtc
.\scripts\diagnose_streams.ps1 -DurationSeconds 120 -VideoOnly
```

Compare:

- `lukow_c8c_60_sub` -> current default, usually `/Streaming/Channels/102`
- `lukow_c8c_60_sub_ch1` -> diagnostic `/ch1/sub`

If `lukow_c8c_60_sub_ch1` passes 120 s, switch the preferred SUB path:

```powershell
python -m ezviz_panel.backend stream-override --camera-slug lukow_c8c_60 --role sub --path /ch1/sub
python -m ezviz_panel.backend go2rtc-render-runtime
docker compose restart go2rtc
```

Do not pass a full RTSP URL to `stream-override`.

## Frigate impact

Frigate consumes streams too. To compare load:

```powershell
docker compose stop frigate
```

Use the panel for 5 minutes. If lag disappears, collect:

```powershell
.\scripts\diagnose_docker.ps1
```

Then reduce active previews, keep `Tryb oszczędny` enabled, or tune Frigate
stream usage.

For a repeatable Frigate ON/OFF comparison:

```powershell
.\scripts\root_cause_stream_lab.ps1 -WithFrigateComparison -DurationSeconds 120 -VideoOnly
```

If Frigate OFF improves FFmpeg/go2rtc results, the issue is likely host load or
stream-session competition, not only the frontend.

## Recorder and VPN impact

A recorder/NVR can consume another RTSP session per camera. On smaller cameras
or weak Wi-Fi this can be enough to trigger EOF or low FPS. Use the manual
recorder mode:

```powershell
.\scripts\root_cause_stream_lab.ps1 -WithRecorderComparison -DurationSeconds 120 -VideoOnly
```

Do not leave the recorder disconnected if it is responsible for important
recordings.

If the stack runs on your computer through WireGuard, all camera ingest may be
crossing the VPN. Compare the same Root Cause Lab report from VPN and from LAN.
If LAN is stable but VPN is not, look at routing, upload/download and jitter.

## Video wall controls

In `Konsola podglądu`:

- `Maksymalna liczba aktywnych podglądów`: default `4`.
- `Tryb oszczędny`: forces `Szybka`, active limit `2`, audio off, slower polling.
- `Pokaż diagnostykę streamów`: shows mount/reload/src-change counters per tile.
- `bez limitu`: only for short local tests; it can cause HEVC/H.265 lag.

## Interpreting errors

`461 Unsupported transport` means the RTSP server rejected the attempted
transport. Use `-rtsp_transport tcp`.

`EOF` means the RTSP stream ended unexpectedly. If it happens during the 120 s
FFmpeg test, treat that alias as unstable.

HEVC warnings can be noisy. If FPS stays near the camera's expected rate and the
test reaches 120 s, the stream is likely usable. If FPS collapses or EOF occurs,
do not blame only the frontend.

## H.264 fallback

A single experimental H.264 fallback can be tested later for one stream. Do not
mass-transcode every camera by default; that can move the bottleneck from the
browser to the host CPU/GPU.
