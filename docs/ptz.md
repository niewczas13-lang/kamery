# ONVIF PTZ

Stage 4A adds local ONVIF PTZ for cameras where private probe results mark
`has_ptz=true`.

## Confirmed PTZ Targets

- `lukow_h9c_98`: supported, ONVIF reachable, primary PTZ test camera.
- `lukow_c8c_60`: supported, ONVIF reachable, second PTZ test camera.
- `lukow_h8_101`: PTZ-capable in probe data, but local testing may be blocked
  until `CAMERA101_PASSWORD` is available.

Not treated as stable real PTZ targets:

- `lukow_c8w_97`: ONVIF/PTZ is not confirmed.
- `lukow_c8c_102`: unstable/experimental. PTZ may be rechecked later, but it is
  not a stable PTZ target in this stage.

## Safety Model

- PTZ is local ONVIF only; no EZVIZ Cloud is used.
- The browser never connects to camera ONVIF ports directly.
- The database stores only secret refs such as `CAMERA98_PASSWORD`.
- Runtime passwords are read from `EZVIZ_SECRETS_ENV_FILE`.
- A movement command defaults to 300 ms.
- Maximum accepted duration is 1500 ms.
- Default speed is 0.3 and is clamped to a safe range.
- Every movement attempts `stop` after the duration.
- If a move fails after connection, the backend still attempts `stop`.
- Errors and warnings are sanitized before they reach CLI/API/UI.

## CLI Probe

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"

.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-probe --camera-slug lukow_h9c_98
```

The output reports whether ONVIF connected, how many profiles were found, and
whether a PTZ profile exists. It does not print passwords.

## Safe PTZ Smoke Tests

H9C 98:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-test --camera-slug lukow_h9c_98 --command left --duration-ms 300
```

C8C 60:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-test --camera-slug lukow_c8c_60 --command right --duration-ms 300
```

Stop explicitly:

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-test --camera-slug lukow_h9c_98 --command stop
```

## Backend API

```http
POST /api/v1/cameras/{id}/ptz/{command}
```

Commands:

- `up`
- `down`
- `left`
- `right`
- `zoom_in`
- `zoom_out`
- `stop`

Optional JSON body:

```json
{
  "duration_ms": 300,
  "speed": 0.3
}
```

Response:

```json
{
  "camera_id": 1,
  "command": "left",
  "status": "moved",
  "duration_ms": 300,
  "stopped": true
}
```

Status behavior:

- `404`: camera not found.
- `400`: unsupported command.
- `409`: PTZ not detected or PTZ secret missing.
- `502`: ONVIF connection/profile/command failure.

## Frontend joystick

Open the local panel and use `Konsola podglądu`, then `Powiększ` on a PTZ
camera. The focus panel shows a joystick-style PTZ control only when the backend
returns `has_ptz=true`.

Stable UI smoke targets:

- H9C: open H9C focus mode, test one short direction click, then `Stop`.
- C8C 60: open C8C 60 focus mode, test one short direction click, then `Stop`.

C8W must not show PTZ unless a later private probe confirms `has_ptz=true`.
C8C 102 remains unstable/experimental.

The UI uses safe nudge mode:

- default duration: 300 ms,
- selectable durations: 200/300/500 ms,
- selectable speeds: slow/medium/fast,
- stop button is always visible,
- backend still enforces max duration and automatic stop.

Focus mode keyboard shortcuts:

- arrows: nudge,
- `+` / `-`: zoom,
- space: stop,
- Escape: close focus.

Shortcuts are ignored while the user is typing in an input/select/textarea.
Press-and-hold controls, presets, tours, autotracking, and public remote PTZ are
intentionally deferred.

## Panel movement lock

The frontend does not run patrols, tours, autotracking, or automatic PTZ loops.
Focus mode starts with `Blokada ruchu PTZ` enabled. While locked:

- arrow/zoom keyboard shortcuts do not send movement,
- joystick movement buttons are disabled,
- `STOP` remains enabled for emergency stopping,
- unlocking is session-only and is reset on focus close, camera/lens change, or
  page refresh.

## Etap 5C PTZ UX

Focus mode labels PTZ as `Sterowanie kamerą fizyczną`. For dual-lens H9C this
is intentional: PTZ moves the physical camera, not a separate stream tile. The
focus side panel shows the warning:

```text
Uwaga: PTZ steruje fizyczną kamerą, nie osobnym strumieniem ani pojedynczym obiektywem.
```

The joystick remains safe-nudge only. The radial pad has a larger center `STOP`,
visible status text (`Gotowe`, `Ruch`, `Zatrzymano`, `Błąd`) and the same
speed/duration controls: wolno/średnio/szybko and 200/300/500 ms.

## Etap 5D PTZ target lens dla H9C

H9C focus mode now has a local operator setting:

```text
PTZ steruje:
- Obiektyw 1
- Obiektyw 2
- Nie wiem / do sprawdzenia
```

This does not assume which physical lens moves. The operator should open both
lenses, run one short safe-nudge PTZ movement, and choose the image that moved.
The UI then shows:

```text
PTZ steruje fizyczną kamerą. Aktualnie przypisane do: Obiektyw 2.
```

The value is frontend/localStorage state only for this stage. Backend schema or
probe-derived `ptz_target_stream_role` can be added later if needed.
