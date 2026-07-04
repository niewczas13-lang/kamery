# Agent Working Rules

- Do not commit secrets, EZVIZ verification codes, camera passwords, private IP
  credentials, `.env`, or `cameras.local.yml`.
- Do not log passwords, verification codes, or full RTSP URLs with credentials.
- Prefer small, focused changes.
- Run tests after larger changes.
- Backend work should add endpoint tests.
- Frontend work should run lint/typecheck.
- Docker Compose should build before it is treated as ready.
- Mark camera features as `supported`, `unsupported`, or `experimental` from
  probe results, not from model assumptions.
- Build `camera-probe` first, then the dashboard.
