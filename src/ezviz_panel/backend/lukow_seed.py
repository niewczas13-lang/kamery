from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from .models import Camera, Location


@dataclass(frozen=True)
class LukowCameraSeed:
    slug: str
    name: str
    host: str
    model: str
    secret_ref: str
    main_stream_path: str | None = None
    sub_stream_path: str | None = None
    secondary_main_stream_path: str | None = None
    secondary_sub_stream_path: str | None = None
    video_codec: str | None = "hevc"
    audio_codec: str | None = None
    video_status: str = "ok"
    control_status: str = "unknown"
    probe_status: str = "manual_seed"
    has_audio: bool = False
    has_ptz: bool = False
    has_onvif: bool = False
    has_snapshot: bool = True
    notes: str | None = None


LUKOW_LOCATION = {
    "slug": "lukow",
    "name": "Lukow",
    "network_cidr": "192.168.80.0/24",
    "description": "Local Lukow camera LAN",
}

# Rejestrator (NVR) jako źródło restreamu dla go2rtc zamiast bezpośrednich kamer.
# Kamera trzyma wtedy jedną sesję RTSP (do rejestratora), co omija limit sesji.
# Po uzyskaniu danych rejestratora: ustaw "host", uzupełnij LUKOW_NVR_CHANNELS
# i przełącz "enabled" na True; hasło trafia do secrets.local.env jako NVR_PASSWORD.
# Ścieżki wg schematu Hikvision/EZVIZ: kanał N -> /Streaming/Channels/N01 (MAIN), N02 (SUB).
LUKOW_NVR_RESTREAM: dict[str, Any] = {
    # enabled zostaje False do czasu wlaczenia RTSP na rejestratorze (port 554
    # jest zamkniety; otwarty tylko 8000/SDK) i potwierdzenia kanalow skanem
    # SKANUJ_NVR_LUKOW.bat.
    "enabled": False,
    "host": "192.168.80.129",  # EZVIZ CS-X5S (8W)
    "username": "admin",
    "secret_ref": "NVR_PASSWORD",
    "main_path_template": "/Streaming/Channels/{channel}01",
    "sub_path_template": "/Streaming/Channels/{channel}02",
}

# slug kamery -> numery kanałów na rejestratorze; "secondary" tylko dla drugiego
# obiektywu H9C, jeśli rejestrator widzi go jako osobny kanał.
LUKOW_NVR_CHANNELS: dict[str, dict[str, int]] = {
    # "lukow_h9c_98": {"primary": 1, "secondary": 2},
    # "lukow_c8w_97": {"primary": 3},
    # "lukow_c8c_60": {"primary": 4},
    # "lukow_c8c_102": {"primary": 5},
}

LUKOW_CAMERA_SEEDS = [
    LukowCameraSeed(
        slug="lukow_h9c_98",
        name="Lukow / H9C 98",
        host="192.168.80.98",
        model="CS-H9c-R100-8G55WKFL",
        secret_ref="CAMERA98_PASSWORD",
        main_stream_path="/Streaming/Channels/101",
        sub_stream_path="/Streaming/Channels/102",
        secondary_main_stream_path="/Streaming/Channels/201",
        secondary_sub_stream_path="/Streaming/Channels/202",
        audio_codec="aac",
        has_audio=True,
        has_ptz=True,
        has_onvif=True,
        notes="Seeded local H9C dual-lens camera. SUB streams are default for grid/smoke.",
    ),
    LukowCameraSeed(
        slug="lukow_c8w_97",
        name="Lukow / C8W 97",
        host="192.168.80.97",
        model="CS-C8W",
        secret_ref="CAMERA97_PASSWORD",
        sub_stream_path="/Streaming/Channels/102",
        notes="Seeded local C8W camera. SUB stream only by default.",
    ),
    LukowCameraSeed(
        slug="lukow_c8c_60",
        name="Lukow / C8C 60",
        host="192.168.80.60",
        model="CS-C8c-R100-1J5WKFL",
        secret_ref="CAMERA60_PASSWORD",
        main_stream_path="/Streaming/Channels/101",
        sub_stream_path="/ch1/sub",
        audio_codec="aac",
        has_audio=True,
        video_codec="hevc",
        video_status="ok",
        control_status="ptz_ok",
        has_ptz=True,
        has_onvif=True,
        has_snapshot=False,
        notes="Seeded as unstable/manual-load live tile. SUB uses /ch1/sub to reduce load; Frigate uses SUB-only experimental NVR.",
    ),
    LukowCameraSeed(
        slug="lukow_c8c_102",
        name="Lukow / C8C 102",
        host="192.168.80.102",
        model="CS-C8c-R100-1J5WKFL",
        secret_ref="CAMERA102_PASSWORD",
        main_stream_path="/Streaming/Channels/101",
        sub_stream_path="/Streaming/Channels/102",
        audio_codec="aac",
        has_audio=True,
        video_codec="hevc",
        video_status="ok",
        control_status="ptz_ok",
        has_ptz=True,
        has_onvif=True,
        has_snapshot=False,
        notes="Seeded local second C8C camera. Frigate uses SUB-only experimental NVR to avoid MAIN load.",
    ),
]


def seed_lukow_cameras(session: Session) -> dict[str, Any]:
    location = session.query(Location).filter(Location.slug == LUKOW_LOCATION["slug"]).first()
    created: list[str] = []
    updated: list[str] = []

    if location is None:
        location = Location(**LUKOW_LOCATION)
        session.add(location)
        session.flush()
    else:
        for field, value in LUKOW_LOCATION.items():
            if getattr(location, field) != value:
                setattr(location, field, value)

    for seed in LUKOW_CAMERA_SEEDS:
        camera = session.query(Camera).filter(Camera.slug == seed.slug).first()
        values = _camera_values(seed, location.id)
        if camera is None:
            camera = Camera(**values)
            session.add(camera)
            created.append(seed.slug)
            continue

        changed = False
        for field, value in values.items():
            if getattr(camera, field) != value:
                setattr(camera, field, value)
                changed = True
        if changed:
            updated.append(seed.slug)

    session.commit()
    return {
        "location": LUKOW_LOCATION["slug"],
        "created": created,
        "updated": updated,
        "total": len(LUKOW_CAMERA_SEEDS),
    }


def _camera_values(seed: LukowCameraSeed, location_id: int) -> dict[str, Any]:
    return {
        "location_id": location_id,
        "name": seed.name,
        "slug": seed.slug,
        "model": seed.model,
        "serial_number": None,
        "host": seed.host,
        "rtsp_username": "admin",
        "rtsp_password_secret_ref": seed.secret_ref,
        "onvif_username": "admin",
        "onvif_password_secret_ref": seed.secret_ref,
        "main_stream_path": seed.main_stream_path,
        "sub_stream_path": seed.sub_stream_path,
        "secondary_main_stream_path": seed.secondary_main_stream_path,
        "secondary_sub_stream_path": seed.secondary_sub_stream_path,
        "video_codec": seed.video_codec,
        "audio_codec": seed.audio_codec,
        "video_status": seed.video_status,
        "control_status": seed.control_status,
        "probe_status": seed.probe_status,
        "has_audio": seed.has_audio,
        "has_ptz": seed.has_ptz,
        "has_onvif": seed.has_onvif,
        "has_snapshot": seed.has_snapshot,
        "has_two_way_audio_candidate": False,
        "enabled": True,
        "notes": seed.notes,
        **_nvr_source_values(seed.slug),
    }


def _nvr_source_values(slug: str) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "rtsp_source_host": None,
        "rtsp_source_username": None,
        "rtsp_source_password_secret_ref": None,
        "rtsp_source_main_path": None,
        "rtsp_source_sub_path": None,
        "rtsp_source_secondary_main_path": None,
        "rtsp_source_secondary_sub_path": None,
    }
    config = LUKOW_NVR_RESTREAM
    channels = LUKOW_NVR_CHANNELS.get(slug)
    if not config.get("enabled") or not config.get("host") or not channels:
        return empty

    def channel_paths(channel: int | None) -> tuple[str | None, str | None]:
        if channel is None:
            return None, None
        return (
            str(config["main_path_template"]).format(channel=channel),
            str(config["sub_path_template"]).format(channel=channel),
        )

    main_path, sub_path = channel_paths(channels.get("primary"))
    secondary_main_path, secondary_sub_path = channel_paths(channels.get("secondary"))
    return {
        "rtsp_source_host": str(config["host"]),
        "rtsp_source_username": str(config.get("username") or "admin"),
        "rtsp_source_password_secret_ref": str(config.get("secret_ref") or "NVR_PASSWORD"),
        "rtsp_source_main_path": main_path,
        "rtsp_source_sub_path": sub_path,
        "rtsp_source_secondary_main_path": secondary_main_path,
        "rtsp_source_secondary_sub_path": secondary_sub_path,
    }
