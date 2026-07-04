# NVR Operations

Use this checklist after probe import, go2rtc runtime generation, and Frigate
runtime generation.

```powershell
python -m ezviz_panel.backend frigate-render-runtime
docker compose up -d go2rtc frigate
python -m ezviz_panel.backend frigate-health
python -m ezviz_panel.backend frigate-events
python -m ezviz_panel.backend sync-frigate-events
```

Open the local panel:

```text
http://127.0.0.1:5173
```

Use:

- `Pulpit`: health and counts.
- `Konsola podglądu`: operator live grid.
- `Zdarzenia`: Frigate event list with camera/location/label filters.
- `Nagrania`: Frigate review/recording data when available.
- Focus mode: recording policy editor, event drawer, PTZ joystick.

If Frigate is not running, backend endpoints return `reachable=false` with a
clear error and the frontend stays usable.

## Frigate UI vs EZVIZ Panel

Frigate is the NVR engine. The primary operator panel is EZVIZ Panel at
`http://127.0.0.1:5173`. The Frigate UI at `http://127.0.0.1:5000` remains a
local diagnostics/admin surface, not the daily operator workflow.

## Stream quality

The panel distinguishes:

- `Szybka`: SUB stream, low load, good for grids.
- `Wysoka`: MAIN stream, better quality, good for focus/fullscreen.
- `Auto`: SUB in grid, MAIN in focus/fullscreen when available.

Frigate config should use SUB for detection and MAIN for recording when MAIN
exists:

```text
detect -> SUB
record -> MAIN
```

If MAIN is missing, Frigate and the panel fall back to SUB and show that lower
quality is being used.

## Etap 5C operator workflow

The daily operator workflow should stay in EZVIZ Panel:

- `Konsola podglądu`: monitoring grid and global quality control.
- Event drawer: latest Frigate events without leaving the live wall.
- `Zdarzenia`: filtered Frigate events.
- `Nagrania`: Frigate review/recording data.
- Focus mode: active camera, PTZ, recording policy, recent events, recent recordings.

Etap 5D adds operator NVR polish:

- tile-level `Nowe zdarzenie` overlay with thumbnail, label, score/time context,
- collapsible/filterable event drawer on the live wall,
- focus timeline named `Ostatnie zdarzenia i nagrania`,
- click from an event back to focus mode for the matching camera,
- Polish empty/error states when Frigate is unavailable or has zero events.

Frigate stays the detection/recording engine. Its UI remains useful for local
diagnostics, but it is not the primary operator console.

In the NVR configuration, detection should prefer the fast/SUB stream and
recording should prefer high/MAIN when present. If a camera records from SUB
because MAIN is missing, the panel must describe it as lower-quality recording
rather than silently implying full quality.

## Storage / retencja UI

The dashboard and `Nagrania` view show the current local NVR policy plainly:

```text
Nagrania lokalne
Retencja: 1-2 dni
Tryb: zdarzenia
Dysk: brak danych
```

Until a real storage endpoint exists, the panel must say:

```text
Szczegółowy monitoring dysku będzie dodany w kolejnym etapie.
```

Do not invent free-space numbers or health states if the backend does not return
them.

## Deferred

Public HTTPS/reverse proxy Etap 6A, long retention, mass HEVC transcoding,
full 25-camera production grid, two-way audio, and advanced Frigate autotracking
remain out of scope for this stage.
