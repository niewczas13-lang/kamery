from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ezviz_panel.camera_probe.masking import sanitize_for_sharing

from .models import Camera, CameraProbeResult, Location, RecordingPolicy


class ProbeImportError(ValueError):
    pass


@dataclass(frozen=True)
class ProbeAnalysis:
    probe_status: str
    video_status: str
    control_status: str
    main_stream_path: str | None
    sub_stream_path: str | None
    secondary_main_stream_path: str | None
    secondary_sub_stream_path: str | None
    video_codec: str | None
    audio_codec: str | None
    has_audio: bool
    has_onvif: bool
    has_ptz: bool
    has_snapshot: bool
    has_two_way_audio_candidate: bool

    def to_update_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


STATUS_SCORE = {
    "ok": 300,
    "partial": 200,
    "unknown": 100,
    "failed": 0,
}


def reject_sanitized_probe_result(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    if "xxx" in text or "****" in text or "<name>" in text or "<host>" in text or "<snapshot_path>" in text:
        raise ProbeImportError("Sanitized probe result cannot be imported as production configuration")


def extract_result_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    reject_sanitized_probe_result(payload)
    if isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    if payload.get("camera_id"):
        return [payload]
    raise ProbeImportError("Probe result must contain a camera result or a results list")


def find_probe_item_for_camera(payload: dict[str, Any], camera: Camera) -> dict[str, Any]:
    items = extract_result_items(payload)
    for item in items:
        if item.get("camera_id") == camera.slug or item.get("camera_id") == camera.name:
            return item
        if item.get("host") == camera.host:
            return item
    if len(items) == 1:
        return items[0]
    raise ProbeImportError(f"No probe result matched camera {camera.slug}")


def analyze_probe_result(item: dict[str, Any], camera: Camera | None = None) -> ProbeAnalysis:
    working = [stream for stream in item.get("working_rtsp_paths", []) if isinstance(stream, dict) and not stream.get("error")]
    paths = {stream.get("path"): stream for stream in working}
    model = (item.get("model") or getattr(camera, "model", "") or "").lower()
    is_h9c = "h9c" in model or "/Streaming/Channels/201" in paths or "/Streaming/Channels/202" in paths

    if is_h9c:
        main = _first_path(paths, "/Streaming/Channels/101", "/ch1/main")
        sub = _first_path(paths, "/Streaming/Channels/102", "/ch1/sub")
        secondary_main = _first_path(paths, "/Streaming/Channels/201")
        secondary_sub = _first_path(paths, "/Streaming/Channels/202")
    else:
        main = _first_path(paths, "/Streaming/Channels/101", "/ch1/main")
        sub = _first_path(paths, "/Streaming/Channels/102", "/ch1/sub")
        secondary_main = None
        secondary_sub = None

    has_onvif = bool(item.get("onvif_reachable"))
    has_ptz = bool(item.get("ptz_supported"))
    has_snapshot = bool(item.get("snapshot_possible"))
    has_audio = any(bool(stream.get("has_audio")) for stream in working)
    first_video = next((stream for stream in working if stream.get("video_codec")), None)
    first_audio = next((stream for stream in working if stream.get("audio_codec")), None)

    if main:
        video_status = "ok"
    elif sub or secondary_main or secondary_sub:
        video_status = "partial"
    elif has_onvif or has_ptz:
        video_status = "unavailable"
    else:
        video_status = "failed" if item.get("status") == "failed" else "unknown"

    if has_ptz:
        control_status = "ptz_ok"
    elif has_onvif:
        control_status = "onvif_ok"
    elif item.get("onvif_status") in {"unknown", None}:
        control_status = "unknown"
    else:
        control_status = "unavailable"

    return ProbeAnalysis(
        probe_status=str(item.get("status") or "unknown"),
        video_status=video_status,
        control_status=control_status,
        main_stream_path=main,
        sub_stream_path=sub,
        secondary_main_stream_path=secondary_main,
        secondary_sub_stream_path=secondary_sub,
        video_codec=first_video.get("video_codec") if first_video else None,
        audio_codec=first_audio.get("audio_codec") if first_audio else None,
        has_audio=has_audio,
        has_onvif=has_onvif,
        has_ptz=has_ptz,
        has_snapshot=has_snapshot,
        has_two_way_audio_candidate=bool(item.get("two_way_audio_candidate")),
    )


def import_probe_result(session: Session, camera: Camera, payload: dict[str, Any]) -> CameraProbeResult:
    item = find_probe_item_for_camera(payload, camera)
    analysis = analyze_probe_result(item, camera)
    record = CameraProbeResult(
        camera_id=camera.id,
        raw_result_json=json.dumps(item, ensure_ascii=False, indent=2),
        sanitized_result_json=json.dumps(sanitize_for_sharing(item), ensure_ascii=False, indent=2),
        status=analysis.probe_status,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def apply_probe_result(session: Session, camera: Camera, probe_result: CameraProbeResult) -> ProbeAnalysis:
    item = json.loads(probe_result.raw_result_json)
    analysis = analyze_probe_result(item, camera)
    for key, value in analysis.to_update_dict().items():
        setattr(camera, key, value)
    _ensure_recording_policy(session, camera, analysis)
    session.add(camera)
    session.commit()
    session.refresh(camera)
    return analysis


def import_probe_file(
    session: Session,
    payload: dict[str, Any],
    *,
    create_missing: bool = False,
    apply: bool = False,
    prefer_best: bool = False,
) -> list[CameraProbeResult]:
    records = import_probe_files(
        session,
        [payload],
        create_missing=create_missing,
        apply=apply,
        prefer_best=prefer_best,
    )
    return records


def import_probe_files(
    session: Session,
    payloads: list[dict[str, Any]],
    *,
    create_missing: bool = False,
    apply: bool = False,
    prefer_best: bool = False,
) -> list[CameraProbeResult]:
    records: list[CameraProbeResult] = []
    affected_cameras: dict[int, Camera] = {}
    for payload in payloads:
        items = extract_result_items(payload)
        for item in items:
            camera = _find_camera_for_item(session, item)
            if camera is None and create_missing:
                camera = _create_camera_for_item(session, item)
            if camera is None:
                continue
            record = CameraProbeResult(
                camera_id=camera.id,
                raw_result_json=json.dumps(item, ensure_ascii=False, indent=2),
                sanitized_result_json=json.dumps(sanitize_for_sharing(item), ensure_ascii=False, indent=2),
                status=str(item.get("status") or "unknown"),
            )
            session.add(record)
            records.append(record)
            affected_cameras[camera.id] = camera
    session.commit()
    for record in records:
        session.refresh(record)
    if apply:
        if prefer_best:
            for camera in affected_cameras.values():
                apply_best_probe_result(session, camera)
        else:
            for record in records:
                session.refresh(record)
                apply_probe_result(session, record.camera, record)
    return records


def apply_best_probe_result(session: Session, camera: Camera) -> ProbeAnalysis | None:
    results = list(camera.probe_results)
    if not results:
        return None
    best = max(results, key=_probe_result_score)
    return apply_probe_result(session, camera, best)


def camera_reliability_status(camera: Camera) -> str:
    parsed = [_raw_item_from_record(record) for record in camera.probe_results]
    items = [item for item in parsed if item is not None]
    if not items:
        return "unknown"

    usable = [_has_working_video(item) or bool(item.get("onvif_reachable")) for item in items]
    good_count = sum(1 for item in items if item.get("status") == "ok" and _has_working_video(item))
    failed_count = sum(
        1
        for item, item_usable in zip(items, usable, strict=True)
        if item.get("status") == "failed" or not item_usable
    )
    timeout_count = sum(1 for item in items if _has_timeout_error(item))

    if any(usable) and failed_count:
        return "unstable"
    if len(items) == 1:
        item = items[0]
        if item.get("status") == "ok" and _has_working_video(item) and not _has_timeout_error(item):
            return "stable"
        if _has_working_video(item) and not _has_timeout_error(item):
            return "stable"
        if _has_working_video(item):
            return "unstable"
        return "degraded" if bool(item.get("onvif_reachable")) else "unstable"
    if good_count and timeout_count:
        return "degraded"
    if all(usable) and not timeout_count:
        return "stable"
    if any(usable):
        return "degraded"
    return "unstable"


def _find_camera_for_item(session: Session, item: dict[str, Any]) -> Camera | None:
    camera_id = item.get("camera_id")
    host = item.get("host")
    query = session.query(Camera)
    if camera_id:
        found = query.filter(Camera.slug == str(camera_id)).first()
        if found:
            return found
    if host:
        return query.filter(Camera.host == str(host)).first()
    return None


def _create_camera_for_item(session: Session, item: dict[str, Any]) -> Camera:
    location_slug = str(item.get("location_id") or "default").strip() or "default"
    location = session.query(Location).filter(Location.slug == location_slug).first()
    if location is None:
        location = Location(
            slug=location_slug,
            name=_friendly_name(location_slug),
            network_cidr=None,
            description="Auto-created from camera probe",
        )
        session.add(location)
        session.flush()

    camera_slug = str(item.get("camera_id") or item.get("host") or "").strip()
    if not camera_slug:
        raise ProbeImportError("Probe camera result is missing camera_id")
    secret_ref = _secret_ref_for_item(item)
    camera = Camera(
        location_id=location.id,
        slug=camera_slug,
        name=str(item.get("name") or camera_slug),
        model=str(item.get("model") or ""),
        serial_number=str(item.get("serial_number") or "") or None,
        host=str(item.get("host") or ""),
        rtsp_username="admin",
        rtsp_password_secret_ref=secret_ref,
        onvif_username="admin",
        onvif_password_secret_ref=secret_ref,
        enabled=True,
        notes="Auto-created from camera probe",
    )
    session.add(camera)
    session.flush()
    return camera


def _secret_ref_for_item(item: dict[str, Any]) -> str:
    host = str(item.get("host") or "")
    octet_match = re.search(r"\.(\d{1,3})$", host)
    if octet_match:
        return f"CAMERA{octet_match.group(1)}_PASSWORD"
    camera_id = str(item.get("camera_id") or "")
    suffix_match = re.search(r"(\d+)$", camera_id)
    if suffix_match:
        return f"CAMERA{suffix_match.group(1)}_PASSWORD"
    raise ProbeImportError(f"Cannot infer secret ref for camera {camera_id or '<unknown>'}")


def _friendly_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", slug) if part) or slug


def _first_path(paths: dict[str | None, dict[str, Any]], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in paths:
            return candidate
    return None


def _ensure_recording_policy(session: Session, camera: Camera, analysis: ProbeAnalysis) -> None:
    policy = camera.recording_policy
    if policy is None:
        policy = RecordingPolicy(camera_id=camera.id)
        session.add(policy)
    if analysis.video_status == "unavailable":
        policy.mode = "disabled"
        policy.record_main_stream = False
        policy.detect_sub_stream = False
        policy.enabled = False
    elif analysis.main_stream_path or analysis.sub_stream_path:
        policy.mode = "events_only"
        policy.record_main_stream = bool(analysis.main_stream_path)
        policy.detect_sub_stream = bool(analysis.sub_stream_path)
        policy.enabled = True


def _probe_result_score(record: CameraProbeResult) -> int:
    item = _raw_item_from_record(record)
    if item is None:
        return -1
    working = [stream for stream in item.get("working_rtsp_paths", []) if isinstance(stream, dict) and not stream.get("error")]
    preferred_paths = {"/Streaming/Channels/101", "/Streaming/Channels/102", "/Streaming/Channels/201", "/Streaming/Channels/202"}
    score = STATUS_SCORE.get(str(item.get("status") or "unknown"), 100)
    score += len(working) * 20
    score += sum(10 for stream in working if stream.get("path") in preferred_paths)
    if item.get("snapshot_possible"):
        score += 15
    if item.get("onvif_reachable"):
        score += 10
    if item.get("ptz_supported"):
        score += 10
    if any(stream.get("has_audio") for stream in working):
        score += 5
    score -= len(item.get("errors") or []) * 8
    score -= sum(1 for stream in working if float(stream.get("probe_duration_ms") or 0) > 8000) * 4
    return score


def _raw_item_from_record(record: CameraProbeResult) -> dict[str, Any] | None:
    try:
        raw = json.loads(record.raw_result_json)
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None


def _has_working_video(item: dict[str, Any]) -> bool:
    return any(
        isinstance(stream, dict) and not stream.get("error")
        for stream in item.get("working_rtsp_paths", [])
    )


def _has_timeout_error(item: dict[str, Any]) -> bool:
    errors = item.get("errors") or []
    return any("timeout" in str(error).lower() or "timed out" in str(error).lower() for error in errors)
