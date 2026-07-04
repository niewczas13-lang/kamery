# Real Camera Test Checklist

Use this checklist before testing the first real EZVIZ camera.

## Before probe

- The camera and computer are on the same LAN or connected through VPN.
- The camera IP address is known.
- The EZVIZ verification code is known.
- LAN Live View/RTSP is enabled in the EZVIZ app if the model requires it.
- `ffmpeg` and `ffprobe` are available.
- Port `554` is reachable from the computer.
- `cameras.local.yml` exists and is not committed.

## Windows quick start

```powershell
Copy-Item cameras.example.yml cameras.local.yml
notepad cameras.local.yml
$env:PYTHONPATH = "src"
python -m ezviz_panel.camera_probe verify-tools
python -m ezviz_panel.camera_probe run --config cameras.local.yml --camera-id lukow_h9c_98 --timeout 8 --secrets-env-file "C:\Users\Pawel Z\OneDrive\Documents\kamery podgląd\config\secrets.local.env" --output probe-results/lukow_h9c_98.json
python -m ezviz_panel.camera_probe sanitize-result probe-results/lukow_h9c_98.json --output probe-results/lukow_h9c_98.sanitized.json
```

Or use the helper:

```powershell
.\scripts\run_probe.ps1 -Config cameras.local.yml -CameraId lukow_h9c_98
```

## After probe

- Save the private result under `probe-results/`.
- Generate a sanitized result before sharing.
- Confirm no local files were committed:
  - `cameras.local.yml`
  - `probe-results/`
  - `snapshots/probe/`

## Interpreting common results

- `ok`: ready for later dashboard configuration.
- `partial`: likely usable, but inspect RTSP/ONVIF/snapshot details.
- `failed`: no useful path found; check network, RTSP setting, port `554`, and
  verification code.
- `unknown`: install/fix local tooling or rerun from a network that can reach
  the camera.
