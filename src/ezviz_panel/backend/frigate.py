from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ezviz_panel.camera_probe.masking import sanitize_sensitive_object, sanitize_text

from .models import Camera, Event, RecordingPolicy
from .probe_importer import camera_reliability_status


HEVC_NVR_WARNING = "HEVC/H.265 recordings may not play in every browser; H.264 fallback/transcode is deferred."
DEFAULT_FRIGATE_TARGETS = {
    "lukow_h9c_98": {"retention_days": 2},
    "lukow_c8w_97": {"retention_days": 1},
}
SKIPPED_TARGET_WARNINGS = {
    "lukow_c8c_60": "lukow_c8c_60: skipped unstable/disabled NVR target",
    "lukow_c8c_102": "lukow_c8c_102: skipped unstable/disabled NVR target",
    "lukow_h8_101": "lukow_h8_101: skipped until CAMERA101_PASSWORD is available",
}
VALID_RECORDING_MODES = {"disabled", "events_only", "continuous", "continuous_selected_hours"}


@dataclass(frozen=True)
class FrigateCameraEntry:
    name: str
    camera_slug: str
    camera_id: int
    detect_stream: str
    record_stream: str
    retention_days: int
    mode: str
    warnings: list[str]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "camera_slug": self.camera_slug,
            "camera_id": self.camera_id,
            "detect_stream": self.detect_stream,
            "record_stream": self.record_stream,
            "retention_days": self.retention_days,
            "mode": self.mode,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class FrigateRenderResult:
    yaml: str
    cameras: list[FrigateCameraEntry]
    warnings: list[str]
    output_path: Path | None = None

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "yaml": self.yaml,
            "cameras": [camera.to_public_dict() for camera in self.cameras],
            "warnings": list(self.warnings),
        }
        if self.output_path is not None:
            payload["output_path"] = str(self.output_path)
        return payload


def render_frigate_preview(session: Session) -> FrigateRenderResult:
    cameras, warnings = _frigate_camera_entries(session)
    return FrigateRenderResult(yaml=_render_frigate_yaml(cameras), cameras=cameras, warnings=warnings)


def render_frigate_runtime_config(session: Session, *, output_path: str | Path) -> FrigateRenderResult:
    preview = render_frigate_preview(session)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(preview.yaml, encoding="utf-8")
    return FrigateRenderResult(
        yaml=preview.yaml,
        cameras=preview.cameras,
        warnings=preview.warnings,
        output_path=output,
    )


def fetch_frigate_health(
    frigate_url: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    base_url = frigate_url.rstrip("/")
    try:
        client_kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
        if transport is not None:
            client_kwargs["transport"] = transport
        with httpx.Client(**client_kwargs) as client:
            response = client.get(f"{base_url}/")
            reachable = response.status_code < 400
            version = None
            try:
                version_response = client.get(f"{base_url}/api/version")
                if version_response.status_code < 400:
                    version = version_response.text.strip().strip('"') or None
            except httpx.HTTPError:
                version = None
    except (httpx.HTTPError, OSError) as exc:
        return {"reachable": False, "version": None, "error": sanitize_text(str(exc))}
    return {"reachable": reachable, "version": version, "error": None if reachable else "Frigate API not reachable"}


def fetch_frigate_cameras(
    frigate_url: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    payload = _fetch_frigate_json(frigate_url, "/api/config", timeout=timeout, transport=transport)
    if not payload["reachable"]:
        return {"reachable": False, "cameras": None, "error": payload["error"]}
    data = payload["data"]
    cameras = data.get("cameras") if isinstance(data, dict) else data
    return {"reachable": True, "cameras": sanitize_sensitive_object(cameras), "error": None}


def fetch_frigate_events(
    frigate_url: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    payload = _fetch_frigate_json(frigate_url, "/api/events", timeout=timeout, transport=transport)
    if not payload["reachable"]:
        return {"reachable": False, "events": None, "error": payload["error"]}
    return {"reachable": True, "events": sanitize_sensitive_object(payload["data"]), "error": None}


def fetch_frigate_event(
    frigate_url: str,
    event_id: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    payload = _fetch_frigate_json(frigate_url, f"/api/events/{event_id}", timeout=timeout, transport=transport)
    if not payload["reachable"]:
        return {"reachable": False, "event": None, "error": payload["error"]}
    return {"reachable": True, "event": sanitize_sensitive_object(payload["data"]), "error": None}


def fetch_frigate_recordings(
    frigate_url: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    payload = _fetch_frigate_json(frigate_url, "/api/review", timeout=timeout, transport=transport)
    if not payload["reachable"]:
        return {"reachable": False, "recordings": None, "error": payload["error"]}
    return {"reachable": True, "recordings": sanitize_sensitive_object(payload["data"]), "error": None}


def sync_frigate_events(session: Session, events: list[dict[str, Any]]) -> int:
    camera_by_slug = {camera.slug: camera for camera in session.query(Camera).all()}
    existing_ids = _existing_frigate_event_ids(session)
    imported = 0
    for item in events:
        event_id = str(item.get("id") or "")
        camera_slug = str(item.get("camera") or "")
        camera = camera_by_slug.get(camera_slug)
        if not event_id or event_id in existing_ids or camera is None:
            continue
        metadata = sanitize_sensitive_object(dict(item))
        session.add(
            Event(
                camera_id=camera.id,
                source="frigate",
                event_type=str(item.get("type") or "event"),
                label=str(item.get("label")) if item.get("label") is not None else None,
                score=_float_or_none(item.get("score") or item.get("top_score")),
                started_at=_timestamp_or_none(item.get("start_time")),
                ended_at=_timestamp_or_none(item.get("end_time")),
                thumbnail_path=_event_media_url(event_id, "thumbnail.jpg") if item.get("has_snapshot") or item.get("has_clip") else None,
                clip_path=_event_media_url(event_id, "clip.mp4") if item.get("has_clip") else None,
                metadata_json=json.dumps(metadata, sort_keys=True),
            )
        )
        existing_ids.add(event_id)
        imported += 1
    session.commit()
    return imported


def recording_policy_response(policy: RecordingPolicy, camera: Camera) -> dict[str, Any]:
    return {
        "camera_id": camera.id,
        "camera_name": camera.name,
        "camera_slug": camera.slug,
        "mode": policy.mode,
        "retention_days": policy.retention_days,
        "record_main_stream": policy.record_main_stream,
        "detect_sub_stream": policy.detect_sub_stream,
        "enabled": policy.enabled,
    }


def get_or_create_recording_policy(session: Session, camera: Camera) -> RecordingPolicy:
    if camera.recording_policy is not None:
        _materialize_default_recording_policy(camera.recording_policy, camera)
        return camera.recording_policy
    policy = RecordingPolicy(camera_id=camera.id)
    _materialize_default_recording_policy(policy, camera)
    session.add(policy)
    session.flush()
    return policy


def update_recording_policy(
    policy: RecordingPolicy,
    *,
    mode: str | None = None,
    retention_days: int | None = None,
) -> RecordingPolicy:
    if mode is not None:
        if mode not in VALID_RECORDING_MODES:
            raise ValueError("Invalid recording mode")
        policy.mode = mode
        policy.enabled = mode != "disabled"
        policy.detect_sub_stream = mode != "disabled"
        policy.record_main_stream = mode in {"events_only", "continuous", "continuous_selected_hours"}
    if retention_days is not None:
        if retention_days < 1 or retention_days > 30:
            raise ValueError("retention_days must be between 1 and 30")
        policy.retention_days = retention_days
    return policy


def _frigate_camera_entries(session: Session) -> tuple[list[FrigateCameraEntry], list[str]]:
    warnings: list[str] = []
    entries: list[FrigateCameraEntry] = []
    cameras = {camera.slug: camera for camera in session.query(Camera).order_by(Camera.slug).all() if camera.enabled}
    for skipped_slug, warning in SKIPPED_TARGET_WARNINGS.items():
        if skipped_slug in cameras:
            warnings.append(warning)

    for slug in DEFAULT_FRIGATE_TARGETS:
        camera = cameras.get(slug)
        if camera is None:
            warnings.append(f"{slug}: skipped because camera is not present")
            continue
        if camera_reliability_status(camera) == "unstable" or camera.video_status in {"failed", "unavailable"}:
            warnings.append(f"{slug}: skipped unstable/disabled NVR target")
            continue
        policy = _effective_policy(camera)
        if policy["mode"] == "disabled":
            warnings.append(f"{slug}: recording policy disabled")
            continue
        entries.extend(_camera_entries(camera, policy, warnings))
    return entries, sorted(set(warnings))


def _effective_policy(camera: Camera) -> dict[str, Any]:
    defaults = DEFAULT_FRIGATE_TARGETS.get(camera.slug, {"retention_days": 1})
    policy = camera.recording_policy
    if policy is None or _should_apply_default_recording_policy(policy, camera):
        return {"mode": "events_only", "retention_days": defaults["retention_days"]}
    if policy.mode == "disabled":
        return {"mode": "disabled", "retention_days": policy.retention_days}
    if camera.slug in DEFAULT_FRIGATE_TARGETS and policy.mode == "events_only" and policy.retention_days == 7:
        return {"mode": policy.mode, "retention_days": defaults["retention_days"]}
    return {"mode": policy.mode, "retention_days": policy.retention_days}


def _materialize_default_recording_policy(policy: RecordingPolicy, camera: Camera) -> None:
    if not _should_apply_default_recording_policy(policy, camera):
        return
    defaults = DEFAULT_FRIGATE_TARGETS[camera.slug]
    policy.mode = "events_only"
    policy.retention_days = defaults["retention_days"]
    policy.record_main_stream = True
    policy.detect_sub_stream = True
    policy.enabled = True


def _should_apply_default_recording_policy(policy: RecordingPolicy, camera: Camera) -> bool:
    return (
        camera.slug in DEFAULT_FRIGATE_TARGETS
        and policy.mode == "disabled"
        and policy.retention_days == 7
        and not policy.enabled
        and not policy.record_main_stream
        and not policy.detect_sub_stream
    )


def _camera_entries(camera: Camera, policy: dict[str, Any], warnings: list[str]) -> list[FrigateCameraEntry]:
    entries: list[FrigateCameraEntry] = []
    if policy["mode"] == "continuous_selected_hours":
        warnings.append(f"{camera.slug}: continuous_selected_hours schedule is deferred; rendering event-based retention only")
    if camera.sub_stream_path or camera.main_stream_path:
        entries.append(
            _entry(
                name=camera.slug,
                camera=camera,
                detect_stream=f"{camera.slug}_{'sub' if camera.sub_stream_path else 'main'}",
                record_stream=f"{camera.slug}_{'main' if camera.main_stream_path else 'sub'}",
                policy=policy,
            )
        )
    if camera.secondary_sub_stream_path or camera.secondary_main_stream_path:
        entries.append(
            _entry(
                name=f"{camera.slug}_lens2",
                camera=camera,
                detect_stream=f"{camera.slug}_lens2_{'sub' if camera.secondary_sub_stream_path else 'main'}",
                record_stream=f"{camera.slug}_lens2_{'main' if camera.secondary_main_stream_path else 'sub'}",
                policy=policy,
            )
        )
    if not entries:
        warnings.append(f"{camera.slug}: skipped because no usable stream paths are present")
    return entries


def _entry(name: str, camera: Camera, detect_stream: str, record_stream: str, policy: dict[str, Any]) -> FrigateCameraEntry:
    warnings = [HEVC_NVR_WARNING] if (camera.video_codec or "").lower() in {"hevc", "h265", "h.265"} else []
    return FrigateCameraEntry(
        name=name,
        camera_slug=camera.slug,
        camera_id=camera.id,
        detect_stream=detect_stream,
        record_stream=record_stream,
        retention_days=int(policy["retention_days"]),
        mode=str(policy["mode"]),
        warnings=warnings,
    )


def _render_frigate_yaml(cameras: list[FrigateCameraEntry]) -> str:
    lines = [
        "mqtt:",
        "  enabled: false",
        "detectors:",
        "  cpu1:",
        "    type: cpu",
        "motion:",
        "  threshold: 45",
        "  contour_area: 35",
        "objects:",
        "  track:",
        "    - person",
        "  filters:",
        "    person:",
        "      min_score: 0.7",
        "      threshold: 0.85",
        "cameras:",
    ]
    if not cameras:
        lines.append("  # no cameras enabled for Frigate yet")
        return "\n".join(lines) + "\n"
    for camera in cameras:
        lines.extend(_camera_yaml(camera))
    return "\n".join(lines) + "\n"


def _camera_yaml(camera: FrigateCameraEntry) -> list[str]:
    lines = [
        f"  {camera.name}:",
        "    ffmpeg:",
        "      inputs:",
    ]
    if camera.detect_stream == camera.record_stream:
        lines.extend(
            [
                f"        - path: rtsp://go2rtc:8554/{camera.detect_stream}",
                "          roles:",
                "            - detect",
                "            - record",
            ]
        )
    else:
        lines.extend(
            [
                f"        - path: rtsp://go2rtc:8554/{camera.detect_stream}",
                "          roles:",
                "            - detect",
                f"        - path: rtsp://go2rtc:8554/{camera.record_stream}",
                "          roles:",
                "            - record",
            ]
        )
    lines.extend(
        [
            "    detect:",
            "      enabled: true",
            "    record:",
            "      enabled: true",
        ]
    )
    if camera.mode == "continuous":
        lines.extend(
            [
                "      retain:",
                f"        days: {camera.retention_days}",
                "        mode: all",
            ]
        )
    else:
        lines.extend(
            [
                "      retain:",
                "        days: 0",
                "        mode: all",
                "      alerts:",
                "        retain:",
                f"          days: {camera.retention_days}",
                "          mode: motion",
                "      detections:",
                "        retain:",
                f"          days: {camera.retention_days}",
                "          mode: motion",
            ]
        )
    return lines


def _fetch_frigate_json(
    frigate_url: str,
    path: str,
    *,
    timeout: float,
    transport: httpx.BaseTransport | None,
) -> dict[str, Any]:
    base_url = frigate_url.rstrip("/")
    try:
        client_kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
        if transport is not None:
            client_kwargs["transport"] = transport
        with httpx.Client(**client_kwargs) as client:
            response = client.get(f"{base_url}{path}")
            response.raise_for_status()
            try:
                data: Any = response.json()
            except ValueError:
                data = response.text
    except (httpx.HTTPError, OSError) as exc:
        return {"reachable": False, "data": None, "error": sanitize_text(str(exc))}
    return {"reachable": True, "data": sanitize_sensitive_object(data), "error": None}


def _existing_frigate_event_ids(session: Session) -> set[str]:
    ids: set[str] = set()
    for event in session.query(Event).filter(Event.source == "frigate").all():
        try:
            metadata = json.loads(event.metadata_json or "{}")
        except json.JSONDecodeError:
            continue
        event_id = metadata.get("id")
        if event_id:
            ids.add(str(event_id))
    return ids


def _event_media_url(event_id: str, media_name: str) -> str:
    return f"/api/events/{event_id}/{media_name}"


def _timestamp_or_none(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (TypeError, ValueError, OSError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
