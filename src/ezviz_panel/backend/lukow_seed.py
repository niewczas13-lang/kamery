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
        notes="Seeded as unstable/manual-load live tile. SUB uses /ch1/sub to reduce load; Frigate remains disabled by default.",
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
        notes="Seeded local second C8C camera. Keep NVR disabled by policy until LAN stability is confirmed.",
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
    }
