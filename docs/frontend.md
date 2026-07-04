# Frontend

Stage 5B turns the local frontend into a Polish operator console. Frigate stays
the NVR engine and go2rtc stays the stream engine, but the daily operator UI is
EZVIZ Panel.

It is a React + TypeScript + Vite app. It talks only to the FastAPI backend and
to the go2rtc player by stream name. It does not read `runtime/config`, does not
know RTSP URLs, and does not receive camera passwords or verification codes.

## Język panelu

The UI is Polish-first. Core labels live in `apps/web/src/i18n/pl.ts`; technical
codes such as `HEVC`, `PTZ`, `ONVIF`, `go2rtc`, `Frigate`, `MAIN`, and `SUB` may
remain as technical badges. User-facing menu labels, actions, empty states, and
errors should be Polish.

## Environment

```powershell
cd apps/web
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
$env:VITE_GO2RTC_PUBLIC_URL = "http://127.0.0.1:1984"
$env:VITE_FRIGATE_PUBLIC_URL = "http://127.0.0.1:5000"
```

Both values have those local defaults, so they may be omitted for dev.

## Run

Start backend and go2rtc first:

```powershell
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///runtime/db/ezviz-panel.db"
$env:EZVIZ_BACKEND_SECRET_KEY = "local-dev-secret-change-me"
$env:EZVIZ_SECRETS_ENV_FILE = "C:\Users\Piotr\Desktop\PANEL\secrets.local.env"
$env:GO2RTC_API_URL = "http://127.0.0.1:1984"

python -m ezviz_panel.backend runserver
docker compose up -d go2rtc
```

Then start the frontend:

```powershell
cd apps/web
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Login with the local backend admin account created by `python -m
ezviz_panel.backend create-admin`.

## Operator Console UX

- `Pulpit`: control-room metrics, health cards, recent events, quick launch.
- `Konsola podglądu`: camera grid with layout choices 1/2/4/6/9/Auto.
- `Kamery`: inventory and capabilities.
- `Strumienie`: stream list opened by stream name only.
- `Zdarzenia`: Frigate events with camera/location/label filters.
- `Nagrania`: Frigate review/recording data grouped by day.
- `Diagnostyka`: health, HEVC warnings, unstable cameras, local-only reminders.

`Konsola podglądu` does not load all streams automatically. A card must be
explicitly loaded, and the layout limit controls how many camera cards are shown.

## Profile jakości

- `Szybka`: uses SUB, recommended for grids and many cameras.
- `Wysoka`: uses MAIN, recommended for focus/fullscreen.
- `Auto`: uses SUB in the grid and MAIN in focus/fullscreen when MAIN exists.

SUB can look weak, often around `768x432`. MAIN is the intended high-quality
view, for example `2560x1440` or `2880x1620`. If MAIN is missing, the UI falls
back to SUB and tells the operator.

## Focus mode

Focus mode opens a large camera view. It defaults to MAIN through the `Auto`
profile when a MAIN stream exists, shows resolution/FPS/codec, exposes a
MAIN/SUB quality switch, and keeps the technical stream name in metadata rather
than as the primary label.

H9C dual lens is shown as one physical camera with:

- `Obiektyw 1`
- `Obiektyw 2`
- `Widok podzielony`

Split view uses SUB for both lenses by default. Active lens focus can use MAIN.
Do not assume which H9C lens physically follows PTZ; verify manually and record
that as a later `ptz_target_stream_role` setting.

## PTZ joystick

The frontend uses a joystick-style component for PTZ cameras. Safe nudge mode is
the default: one click sends one backend command with a bounded duration, and the
backend sends stop automatically. Keyboard shortcuts work only in focus mode and
are ignored while typing in inputs:

- arrows: nudge
- `+` / `-`: zoom
- space: stop
- Escape: close focus

Press-and-hold remains deferred/experimental.

## Notes

- H8 101 can be absent when `CAMERA101_PASSWORD` is not available. That must not
  block the UI.
- C8C 60 and C8C 102 are visible when stream metadata exists, but they are
  unstable/manual-load tiles and should not auto-start in the wall.
- HEVC/H.265 warnings mean browser playback may need player support or a later
  transcode step.
- Token storage is localStorage for this MVP only. Hardened session handling is a
  later production step.
- PTZ is safe-nudge only in this stage. Each button sends a backend request with
  the default 300 ms duration, then the backend sends stop automatically.
- C8W 97 must not be presented as real PTZ unless a private probe/import marks
  `has_ptz=true`. C8C 102 is experimental/unstable when present.
- Frigate UI/API defaults to `http://127.0.0.1:5000` through
  `VITE_FRIGATE_PUBLIC_URL`. It remains local/dev only.
- Etap 6A public HTTPS/reverse proxy is intentionally deferred.

## Etap 5C video wall

`Konsola podglądu` is now the main monitoring video wall. It distinguishes a
physical camera from a logical preview window. H9C is one physical camera, but it
can render two grid tiles:

- `H9C 98 - Obiektyw 1`
- `H9C 98 - Obiektyw 2`

The `Obiektywy jako osobne okna` toggle controls split/merged grid behavior.
When merged, H9C is represented as one tile with a `2 obiektywy` marker.

Normal tiles stay clean: video, title, and compact badges (`LIVE`, `REC`, `PTZ`,
`AUDIO`, `HEVC`, `NIESTABILNA`). Resolution, FPS, codec, stream role, model,
location, and last event are shown in the hover overlay or in focus mode.

The only quality selector is global:

- `Auto`: SUB in grid, MAIN in focus when available.
- `Szybka`: SUB everywhere.
- `Wysoka`: MAIN for visible tiles when available, fallback to SUB.

Per-tile quality buttons are intentionally removed so the grid does not become
an admin form. If MAIN is missing, the UI falls back to SUB and shows:
`Brak strumienia wysokiej jakości. Używam szybkiego podglądu.`

Saved layouts are stored in `localStorage` as tile ids, hidden tile ids, and
order. They do not store stream URLs, RTSP URLs, credentials, or runtime config.
The built-in layouts are `Wszystkie kamery`, `H9C podwójny`, `PTZ`, and
`NVR / zdarzenia`; users can save a `Własny układ`.

The event drawer is a right-side panel with recent Frigate events. Empty state:
`Brak zdarzeń. Przejdź przed kamerę, żeby przetestować detekcję.`

## Etap 5D operator controls

### Nazwy operatorskie kamer

Use `Zmień nazwę` on a tile or in focus mode to set a friendly label such as
`Plac`, `Brama`, `Wjazd`, `Magazyn`, `H9C - szeroki`, or `H9C - obrotowy`.
Names are frontend-only and stored in:

```text
cameraDisplayNames
tileDisplayNames
```

`Reset nazwy` returns the UI to the technical/backend name. The sanitizer rejects
values that look like RTSP URLs or credentials, and the frontend never stores
camera passwords or verification codes.

### Edytor układu

Use `Edytuj układ` in `Konsola podglądu` to hide/show tiles and move them with
`Góra` / `Dół`. `Zapisz układ` creates a local `Własny układ`; `Ustaw jako
domyślny` activates the current local order; `Przywróć domyślny` returns to the
built-in `Wszystkie kamery` / `Auto` state.

Saved layouts store only:

```text
tile_id
order
visible / hidden
layout size
quality mode
split lenses setting
```

They do not store RTSP URLs, stream source URLs, runtime go2rtc config, or
secrets.

### Tryb pełnoekranowy

`Tryb pełnoekranowy` hides the sidebar and keeps the wall with compact status
pills. Use `Wyjdź z pełnego ekranu` or Escape when focus mode is not open.

### Tryb monitora

`Tryb monitora` is for a large local display. It hides editing panels, keeps the
video wall and event drawer, periodically refreshes status, blocks automatic
MAIN loading for many cameras, and keeps every player muted.

### Blokada ruchu PTZ

Focus mode starts with `Blokada ruchu PTZ` enabled. While locked, the panel does
not send movement commands from joystick buttons or keyboard shortcuts. The
`STOP` button remains active as an emergency stop. Unlocking movement is
session-only and is reset when focus mode closes, the camera/lens changes, or
the page refreshes.

### Event overlay

Recent Frigate events can highlight the matching tile with `Nowe zdarzenie`,
thumbnail, label (`Osoba`, `Ruch`, `Pojazd`) and time. If Frigate returns no
events, the empty state says:

```text
Brak zdarzeń. Przejdź przed kamerę, żeby przetestować detekcję.
```

### Focus timeline

Focus mode shows `Ostatnie zdarzenia i nagrania` below the player. H9C filters
timeline data by `lukow_h9c_98` or `lukow_h9c_98_lens2` when Frigate can map the
event to a logical lens; otherwise it shows the H9C camera-level events.

### Polityka dźwięku

`Konsola podglądu` is always muted. Tiles request `muted=1` / `media=video` from
go2rtc and do not grant iframe autoplay-audio permission. Changing `Auto /
Szybka / Wysoka` cannot enable audio. There is no global button that enables
audio for all cameras.

Focus mode starts with `Dźwięk wyłączony`. `Włącz dźwięk` can enable audio only
for the active camera/player after a manual click. Closing focus mode, switching
camera, switching H9C lens, entering monitor mode, or refreshing the page returns
to muted. Cameras without audio show `Dźwięk niedostępny`.

## Etap 5E stabilizacja streamów

The live wall now separates UI refresh from player lifetime:

- React tile keys use stable `tile_id` values.
- The iframe/player URL is derived from stream name, audio policy, and retry
  token only. Health polling, Frigate events, hover overlays, event drawer state,
  and friendly-name changes do not create a new URL.
- `Maksymalna liczba aktywnych podglądów` controls how many visible tiles render
  iframes. The default is `4`; options are `2`, `4`, `6`, `9`, and `bez limitu`.
- Tiles over the limit show `Podgląd wstrzymany` and `Kliknij, aby załadować`.
  Manual load affects only that local browser session.
- `Tryb oszczędny` forces the wall to `Szybka`, limits active previews to `2`,
  keeps audio off, and slows live polling to reduce browser/GPU load.
- IntersectionObserver unloads offscreen iframe players when the browser
  supports it.
- `Pokaż diagnostykę streamów` shows `tile_id`, stream name, quality, active /
  paused state, mount count, reload count, src changes, last loaded, last error,
  over-limit state, offscreen state, and stability label.

Diagnostics never show RTSP URLs, credentials, verification codes, raw go2rtc
logs, or runtime config. Grid players remain muted and request `media=video` /
`muted=1`; confirmed go2rtc audio-free stream aliases are deferred until tested.
