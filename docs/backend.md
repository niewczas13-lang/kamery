# Backend

The backend is a FastAPI app with SQLAlchemy models and SQLite by default.

## Environment

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_BACKEND_SECRET_KEY = "change-this-to-a-long-local-secret"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"
$env:GO2RTC_API_URL = "http://127.0.0.1:1984"
```

`DATABASE_URL` can later point to PostgreSQL. Etap 2A uses SQLite for dev/test.

## Commands

```powershell
.\.venv\Scripts\python.exe -m ezviz_panel.backend init-db
$env:ADMIN_PASSWORD = "choose-a-local-password"
.\.venv\Scripts\python.exe -m ezviz_panel.backend create-admin --username admin --password-env ADMIN_PASSWORD
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe --file probe-results/vpn-full-20260704-000914.json --create-missing --apply
.\.venv\Scripts\python.exe -m ezviz_panel.backend import-probe --file probe-results/vpn-recheck-lukow_c8c_60-20260704-001420.json --file probe-results/vpn-recheck-lukow_c8c_102-20260704-001420.json --apply --prefer-best
.\.venv\Scripts\python.exe -m ezviz_panel.backend list-streams
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-preview
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-render-runtime
docker compose up -d go2rtc
.\.venv\Scripts\python.exe -m ezviz_panel.backend go2rtc-health
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-probe --camera-slug lukow_h9c_98
.\.venv\Scripts\python.exe -m ezviz_panel.backend ptz-test --camera-slug lukow_h9c_98 --command left --duration-ms 300
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-preview
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-render-runtime
.\.venv\Scripts\python.exe -m ezviz_panel.backend frigate-health
.\.venv\Scripts\python.exe -m ezviz_panel.backend runserver --host 127.0.0.1 --port 8000
```

## Auth

`POST /api/v1/auth/login` returns a bearer token. Private endpoints require:

```text
Authorization: Bearer <token>
```

The admin password is hashed with PBKDF2-SHA256. Plain admin passwords are never
stored.

## Current Endpoints

- `GET /api/v1/health`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- CRUD for `/api/v1/locations`
- CRUD for `/api/v1/cameras`
- `POST /api/v1/cameras/{id}/probe-results/import`
- `GET /api/v1/cameras/{id}/probe-results`
- `GET /api/v1/cameras/{id}/probe-results/latest`
- `POST /api/v1/cameras/{id}/apply-probe-result/{probe_result_id}`
- `POST /api/v1/cameras/{id}/snapshot`
- `POST /api/v1/cameras/{id}/ptz/{command}`
- `GET /api/v1/streams`
- `GET /api/v1/streams/{stream_name}`
- `GET /api/v1/config/go2rtc/preview`
- `POST /api/v1/config/go2rtc/render-preview`
- `POST /api/v1/config/go2rtc/render-runtime`
- `GET /api/v1/go2rtc/health`
- `GET /api/v1/go2rtc/streams`
- `GET /api/v1/recording-policies`
- `GET /api/v1/cameras/{id}/recording-policy`
- `PATCH /api/v1/cameras/{id}/recording-policy`
- `GET /api/v1/frigate/health`
- `GET /api/v1/frigate/cameras`
- `GET /api/v1/frigate/events`
- `GET /api/v1/frigate/events/{event_id}`
- `GET /api/v1/frigate/recordings`
- `GET /api/v1/frigate/config/preview`
- `POST /api/v1/frigate/config/render-runtime`
- `GET /debug/streams` local/dev diagnostics page

PTZ uses local ONVIF through `POST /api/v1/cameras/{id}/ptz/{command}`. Supported
commands are `up`, `down`, `left`, `right`, `zoom_in`, `zoom_out`, and `stop`.
The backend resolves `onvif_password_secret_ref` from `EZVIZ_SECRETS_ENV_FILE`,
uses a default 300 ms movement, clamps duration to 1500 ms, and attempts `stop`
after every movement even when the move command fails. Unsupported/no-PTZ cameras
return `409`, missing PTZ secrets return `409`, invalid commands return `400`,
and ONVIF connection/command failures return `502` without secret values.

`POST /api/v1/config/go2rtc/render-runtime` writes the private runtime config to
`runtime/config/go2rtc/go2rtc.yaml` by default. The response contains path,
counts, skipped camera slugs, unstable camera slugs, and warnings, but never
resolved camera passwords.

Camera responses include a dynamic `reliability_status` value:

- `unknown`: no probe history yet.
- `stable`: the available probe history is consistently usable.
- `degraded`: usable, but one or more probe attempts had timeouts or reduced capability.
- `unstable`: mixed failed/usable results or only experimental video availability.

`POST /api/v1/cameras/{id}/snapshot` uses ffmpeg and the best configured RTSP
path. It resolves the secret ref at runtime, writes to `runtime/snapshots/`, and
returns `409` for control-only/no-video cameras.

See [ptz.md](ptz.md) for safe PTZ smoke-test commands for H9C 98 and C8C 60.

Frigate endpoints use `FRIGATE_API_URL`, defaulting to
`http://127.0.0.1:5000`. They return safe unavailable payloads when Frigate is
offline instead of crashing the panel. `frigate-render-runtime` writes
`runtime/config/frigate/config.yml`, using go2rtc restream URLs only.
