from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from ezviz_panel.camera_probe.config import ConfigError
from ezviz_panel.camera_probe.masking import sanitize_sensitive_object, sanitize_text

from .models import Camera
from .probe_importer import camera_reliability_status
from .secrets import load_secret_refs


HEVC_WARNING = "HEVC/H.265 stream may need go2rtc playback support or the experimental H.264 fallback."
C8C60_DIAGNOSTIC_WARNING = "diagnostic alternate C8C 60 /ch1/sub stream"
C8C60_DIAGNOSTIC_PATH = "/ch1/sub"
STREAM_OVERRIDE_FIELDS = {
    "main": "main_stream_path",
    "sub": "sub_stream_path",
    "lens2_main": "secondary_main_stream_path",
    "lens2_sub": "secondary_sub_stream_path",
}


class Go2RtcConfigError(ValueError):
    pass


class MissingSecretError(Go2RtcConfigError):
    pass


@dataclass(frozen=True)
class StreamDescriptor:
    stream_name: str
    camera_id: int
    camera_name: str
    camera_slug: str
    location_id: int
    stream_role: str
    path: str
    video_codec: str | None
    audio_codec: str | None
    resolution: str | None
    fps: float | None
    has_audio: bool
    quality_role: str
    quality_label: str
    is_recommended_for_grid: bool
    is_recommended_for_focus: bool
    is_recommended_for_recording: bool
    is_recommended_for_detection: bool
    playback_status: str
    warnings: list[str]
    host: str
    rtsp_username: str
    rtsp_password_secret_ref: str | None
    experimental: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "stream_name": self.stream_name,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "location_id": self.location_id,
            "stream_role": self.stream_role,
            "path": self.path,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "resolution": self.resolution,
            "fps": self.fps,
            "has_audio": self.has_audio,
            "quality_role": self.quality_role,
            "quality_label": self.quality_label,
            "is_recommended_for_grid": self.is_recommended_for_grid,
            "is_recommended_for_focus": self.is_recommended_for_focus,
            "is_recommended_for_recording": self.is_recommended_for_recording,
            "is_recommended_for_detection": self.is_recommended_for_detection,
            "playback_status": self.playback_status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class SkippedCamera:
    camera_id: int
    camera_name: str
    camera_slug: str
    video_status: str
    control_status: str
    reason: str

    def warning(self) -> str:
        return (
            f"{self.camera_slug}: video_status {self.video_status}; "
            f"control_status {self.control_status}; {self.reason}"
        )


@dataclass(frozen=True)
class RuntimeRenderResult:
    output_path: Path
    stream_count: int
    skipped_cameras: list[str]
    unstable_cameras: list[str]
    warnings: list[str]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "stream_count": self.stream_count,
            "skipped_cameras": list(self.skipped_cameras),
            "unstable_cameras": list(self.unstable_cameras),
            "warnings": list(self.warnings),
        }


def list_go2rtc_streams(
    session: Session,
    *,
    enable_experimental_transcode: bool = False,
    include_unstable_streams: bool = False,
    include_diagnostic_streams: bool = False,
) -> list[StreamDescriptor]:
    streams: list[StreamDescriptor] = []
    cameras = session.query(Camera).order_by(Camera.slug).all()
    for camera in cameras:
        if not camera.enabled:
            continue
        streams.extend(
            _stream_descriptors_for_camera(
                camera,
                include_unstable_streams=include_unstable_streams,
                include_diagnostic_streams=include_diagnostic_streams,
            )
        )

    if enable_experimental_transcode:
        experimental = _experimental_transcode_stream(streams)
        if experimental is not None:
            streams.append(experimental)
    return streams


def find_go2rtc_stream(
    session: Session,
    stream_name: str,
    *,
    enable_experimental_transcode: bool = False,
    include_unstable_streams: bool = False,
    include_diagnostic_streams: bool = False,
) -> StreamDescriptor | None:
    return next(
        (
            stream
            for stream in list_go2rtc_streams(
                session,
                enable_experimental_transcode=enable_experimental_transcode,
                include_unstable_streams=include_unstable_streams,
                include_diagnostic_streams=include_diagnostic_streams,
            )
            if stream.stream_name == stream_name
        ),
        None,
    )


def list_skipped_cameras(session: Session, *, include_unstable_streams: bool = False) -> list[SkippedCamera]:
    skipped: list[SkippedCamera] = []
    for camera in session.query(Camera).order_by(Camera.slug).all():
        if not camera.enabled:
            continue
        if _stream_entries_for_camera(camera, include_unstable_streams=include_unstable_streams):
            continue
        reliability = camera_reliability_status(camera)
        if reliability == "unstable" and not include_unstable_streams:
            reason = "unstable camera omitted from default go2rtc runtime"
        elif camera.video_status == "unavailable" and camera.control_status in {"ptz_ok", "onvif_ok"}:
            reason = "no go2rtc stream generated"
        elif camera.video_status in {"failed", "unknown", "unavailable"}:
            reason = "no go2rtc stream generated"
        else:
            reason = "no configured RTSP path"
        skipped.append(
            SkippedCamera(
                camera_id=camera.id,
                camera_name=camera.name,
                camera_slug=camera.slug,
                video_status=camera.video_status,
                control_status=camera.control_status,
                reason=reason,
            )
        )
    return skipped


def render_go2rtc_preview(
    session: Session,
    *,
    enable_experimental_transcode: bool = False,
    include_unstable_streams: bool = False,
    include_diagnostic_streams: bool = False,
) -> tuple[str, list[str]]:
    warnings = _runtime_warnings(
        session,
        include_unstable_streams=include_unstable_streams,
        include_diagnostic_streams=include_diagnostic_streams,
    )
    lines = ["streams:"]
    streams = list_go2rtc_streams(
        session,
        enable_experimental_transcode=enable_experimental_transcode,
        include_unstable_streams=include_unstable_streams,
        include_diagnostic_streams=include_diagnostic_streams,
    )
    for stream in streams:
        lines.append(f"  {stream.stream_name}:")
        if stream.experimental:
            source = stream.stream_name.removesuffix("_h264")
            lines.append(f"    - ffmpeg:{source}#video=h264#audio=copy")
        else:
            lines.append(f"    - {build_rtsp_preview_url(stream)}")
    if not streams:
        lines.append("  # no streams configured yet")
    return "\n".join(lines) + "\n", warnings


def render_go2rtc_runtime_config(
    session: Session,
    *,
    secrets_env_file: str | None,
    output_path: str | Path,
    enable_experimental_transcode: bool = False,
    include_unstable_streams: bool = False,
    include_diagnostic_streams: bool = False,
) -> RuntimeRenderResult:
    try:
        secrets = load_secret_refs(secrets_env_file)
    except ConfigError as exc:
        raise Go2RtcConfigError(str(exc)) from exc

    streams = list_go2rtc_streams(
        session,
        enable_experimental_transcode=enable_experimental_transcode,
        include_unstable_streams=include_unstable_streams,
        include_diagnostic_streams=include_diagnostic_streams,
    )
    missing = _missing_secret_refs(streams, secrets)
    if missing:
        raise MissingSecretError("Missing RTSP secret refs: " + ", ".join(missing))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_runtime_yaml(streams, secrets), encoding="utf-8")
    skipped = list_skipped_cameras(session, include_unstable_streams=include_unstable_streams)
    return RuntimeRenderResult(
        output_path=output,
        stream_count=len(streams),
        skipped_cameras=[camera.camera_slug for camera in skipped],
        unstable_cameras=_unstable_camera_slugs(session),
        warnings=_runtime_warnings(
            session,
            include_unstable_streams=include_unstable_streams,
            include_diagnostic_streams=include_diagnostic_streams,
        ),
    )


def apply_stream_path_override(session: Session, camera_slug: str, stream_role: str, path: str) -> Camera:
    field_name = STREAM_OVERRIDE_FIELDS.get(stream_role)
    if field_name is None:
        raise Go2RtcConfigError(f"Unsupported stream override role: {stream_role}")
    normalized = _normalized_path(path.strip())
    if not normalized.startswith("/") or "rtsp://" in normalized.lower() or "@" in normalized:
        raise Go2RtcConfigError("Stream override path must be a camera path, not a URL or credential string")
    camera = session.query(Camera).filter(Camera.slug == camera_slug).first()
    if camera is None:
        raise Go2RtcConfigError(f"Camera not found: {camera_slug}")
    setattr(camera, field_name, normalized)
    session.commit()
    session.refresh(camera)
    return camera


def build_rtsp_preview_url(stream: StreamDescriptor) -> str:
    password = f"${{{stream.rtsp_password_secret_ref}}}" if stream.rtsp_password_secret_ref else "${MISSING_PASSWORD_REF}"
    username = stream.rtsp_username or "admin"
    return f"rtsp://{username}:{password}@{stream.host}:554{_normalized_path(stream.path)}"


def build_rtsp_runtime_url_for_stream(stream: StreamDescriptor, secrets: dict[str, str]) -> str:
    if not stream.rtsp_password_secret_ref or not secrets.get(stream.rtsp_password_secret_ref):
        raise MissingSecretError(f"Missing RTSP secret ref for {stream.stream_name}")
    username = quote(stream.rtsp_username or "admin", safe="")
    password = quote(secrets[stream.rtsp_password_secret_ref], safe="")
    return f"rtsp://{username}:{password}@{stream.host}:554{_normalized_path(stream.path)}"


def build_rtsp_runtime_url_for_camera(camera: Camera, path: str, secrets: dict[str, str]) -> str:
    if not camera.rtsp_password_secret_ref or not secrets.get(camera.rtsp_password_secret_ref):
        raise MissingSecretError(f"Missing RTSP secret ref for {camera.slug}")
    username = quote(camera.rtsp_username or "admin", safe="")
    password = quote(secrets[camera.rtsp_password_secret_ref], safe="")
    return f"rtsp://{username}:{password}@{camera.host}:554{_normalized_path(path)}"


def best_snapshot_path(camera: Camera) -> str | None:
    for path in (
        camera.main_stream_path,
        camera.sub_stream_path,
        camera.secondary_main_stream_path,
        camera.secondary_sub_stream_path,
    ):
        if path:
            return path
    return None


def mask_secret_values(text: str, secrets: dict[str, str]) -> str:
    masked = text
    for value in secrets.values():
        if value:
            masked = masked.replace(value, "***")
    return masked


def fetch_go2rtc_health(
    go2rtc_url: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    base_url = go2rtc_url.rstrip("/")
    try:
        client_kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
        if transport is not None:
            client_kwargs["transport"] = transport
        with httpx.Client(**client_kwargs) as client:
            version: str | None = None
            stream_count: int | None = None
            api_response = client.get(f"{base_url}/api")
            reachable = api_response.status_code < 400
            if reachable:
                version = _extract_version(api_response)

            streams_response = client.get(f"{base_url}/api/streams")
            if streams_response.status_code < 400:
                reachable = True
                stream_count = _extract_stream_count(streams_response)

            if not reachable:
                root_response = client.get(f"{base_url}/")
                reachable = root_response.status_code < 400
    except (httpx.HTTPError, OSError) as exc:
        return {"reachable": False, "version": None, "stream_count": None, "error": str(exc)}
    return {"reachable": reachable, "version": version, "stream_count": stream_count, "error": None if reachable else "go2rtc API not reachable"}


def fetch_go2rtc_streams(
    go2rtc_url: str,
    *,
    timeout: float = 2.0,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    base_url = go2rtc_url.rstrip("/")
    try:
        client_kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
        if transport is not None:
            client_kwargs["transport"] = transport
        with httpx.Client(**client_kwargs) as client:
            response = client.get(f"{base_url}/api/streams")
            response.raise_for_status()
            try:
                streams: Any = response.json()
            except ValueError:
                streams = response.text
    except (httpx.HTTPError, OSError) as exc:
        return {"reachable": False, "streams": None, "error": sanitize_text(str(exc))}
    sanitized_streams = sanitize_sensitive_object(streams)
    return {"reachable": True, "streams": sanitized_streams, "error": None}


def _stream_descriptors_for_camera(
    camera: Camera,
    *,
    include_unstable_streams: bool = False,
    include_diagnostic_streams: bool = False,
) -> list[StreamDescriptor]:
    metadata = _probe_metadata_by_path(camera)
    descriptors: list[StreamDescriptor] = []
    for role, path in _stream_entries_for_camera(camera, include_unstable_streams=include_unstable_streams):
        stream_metadata = metadata.get(path, {})
        video_codec = _str_or_none(stream_metadata.get("video_codec")) or camera.video_codec
        audio_codec = _str_or_none(stream_metadata.get("audio_codec")) or camera.audio_codec
        resolution = _str_or_none(stream_metadata.get("resolution"))
        fps = _float_or_none(stream_metadata.get("fps"))
        has_audio = bool(stream_metadata.get("has_audio")) if "has_audio" in stream_metadata else bool(camera.has_audio)
        quality_role = _quality_role(role)
        descriptors.append(
            StreamDescriptor(
                stream_name=f"{camera.slug}_{role}",
                camera_id=camera.id,
                camera_name=camera.name,
                camera_slug=camera.slug,
                location_id=camera.location_id,
                stream_role=role,
                path=path,
                video_codec=video_codec,
                audio_codec=audio_codec,
                resolution=resolution,
                fps=fps,
                has_audio=has_audio,
                quality_role=quality_role,
                quality_label=_quality_label(quality_role),
                is_recommended_for_grid=quality_role == "sub",
                is_recommended_for_focus=quality_role == "main",
                is_recommended_for_recording=quality_role == "main",
                is_recommended_for_detection=quality_role == "sub",
                playback_status=_playback_status(video_codec),
                warnings=_stream_warnings(video_codec),
                host=camera.host,
                rtsp_username=camera.rtsp_username,
                rtsp_password_secret_ref=camera.rtsp_password_secret_ref,
            )
        )
    if include_diagnostic_streams:
        descriptors.extend(_diagnostic_stream_descriptors_for_camera(camera, metadata))
    return descriptors


def _diagnostic_stream_descriptors_for_camera(camera: Camera, metadata: dict[str, dict[str, Any]]) -> list[StreamDescriptor]:
    if "c8c_60" not in camera.slug.lower():
        return []
    if C8C60_DIAGNOSTIC_PATH not in metadata:
        return []
    stream_metadata = metadata.get(C8C60_DIAGNOSTIC_PATH, {})
    video_codec = _str_or_none(stream_metadata.get("video_codec")) or camera.video_codec
    audio_codec = _str_or_none(stream_metadata.get("audio_codec")) or camera.audio_codec
    resolution = _str_or_none(stream_metadata.get("resolution"))
    fps = _float_or_none(stream_metadata.get("fps"))
    has_audio = bool(stream_metadata.get("has_audio")) if "has_audio" in stream_metadata else bool(camera.has_audio)
    warnings = _stream_warnings(video_codec)
    warnings.append(C8C60_DIAGNOSTIC_WARNING)
    return [
        StreamDescriptor(
            stream_name=f"{camera.slug}_sub_ch1",
            camera_id=camera.id,
            camera_name=camera.name,
            camera_slug=camera.slug,
            location_id=camera.location_id,
            stream_role="sub_ch1",
            path=C8C60_DIAGNOSTIC_PATH,
            video_codec=video_codec,
            audio_codec=audio_codec,
            resolution=resolution,
            fps=fps,
            has_audio=has_audio,
            quality_role="sub",
            quality_label=_quality_label("sub"),
            is_recommended_for_grid=False,
            is_recommended_for_focus=False,
            is_recommended_for_recording=False,
            is_recommended_for_detection=True,
            playback_status=_playback_status(video_codec),
            warnings=warnings,
            host=camera.host,
            rtsp_username=camera.rtsp_username,
            rtsp_password_secret_ref=camera.rtsp_password_secret_ref,
        )
    ]


def _stream_entries_for_camera(camera: Camera, *, include_unstable_streams: bool = False) -> list[tuple[str, str]]:
    if camera.video_status in {"failed", "unavailable"}:
        return []
    reliability = camera_reliability_status(camera)
    if reliability == "unstable" and not include_unstable_streams:
        return []
    suffix = "_experimental" if reliability == "unstable" else ""
    entries = [
        (f"main{suffix}", camera.main_stream_path),
        (f"sub{suffix}", camera.sub_stream_path),
        (f"lens2_main{suffix}", camera.secondary_main_stream_path),
        (f"lens2_sub{suffix}", camera.secondary_sub_stream_path),
    ]
    return [(role, path) for role, path in entries if path]


def _probe_metadata_by_path(camera: Camera) -> dict[str, dict[str, Any]]:
    latest = max(camera.probe_results, key=lambda result: result.created_at, default=None)
    if latest is None:
        return {}
    try:
        raw = json.loads(latest.raw_result_json)
    except json.JSONDecodeError:
        return {}
    streams = raw.get("working_rtsp_paths")
    if not isinstance(streams, list):
        return {}
    metadata: dict[str, dict[str, Any]] = {}
    for item in streams:
        if not isinstance(item, dict) or item.get("error"):
            continue
        path = item.get("path")
        if isinstance(path, str):
            metadata[path] = item
    return metadata


def _experimental_transcode_stream(streams: list[StreamDescriptor]) -> StreamDescriptor | None:
    source = next((stream for stream in streams if stream.stream_name == "lukow_h9c_98_sub"), None)
    if source is None:
        source = next((stream for stream in streams if stream.stream_role == "sub"), None)
    if source is None:
        return None
    return StreamDescriptor(
        stream_name=f"{source.stream_name}_h264",
        camera_id=source.camera_id,
        camera_name=source.camera_name,
        camera_slug=source.camera_slug,
        location_id=source.location_id,
        stream_role=f"{source.stream_role}_h264",
        path=source.path,
        video_codec="h264",
        audio_codec=source.audio_codec,
        resolution=source.resolution,
        fps=source.fps,
        has_audio=source.has_audio,
        quality_role="sub",
        quality_label="Szybka",
        is_recommended_for_grid=True,
        is_recommended_for_focus=False,
        is_recommended_for_recording=False,
        is_recommended_for_detection=True,
        playback_status="candidate",
        warnings=["experimental single-stream H.264 transcode; do not enable for all cameras by default"],
        host=source.host,
        rtsp_username=source.rtsp_username,
        rtsp_password_secret_ref=source.rtsp_password_secret_ref,
        experimental=True,
    )


def _render_runtime_yaml(streams: list[StreamDescriptor], secrets: dict[str, str]) -> str:
    lines = [
        "api:",
        '  listen: ":1984"',
        "rtsp:",
        '  listen: ":8554"',
        "streams:",
    ]
    for stream in streams:
        lines.append(f"  {stream.stream_name}:")
        if stream.experimental:
            source = stream.stream_name.removesuffix("_h264")
            lines.append(f"    - ffmpeg:{source}#video=h264#audio=copy")
        else:
            lines.append(f"    - {build_rtsp_runtime_url_for_stream(stream, secrets)}")
    if not streams:
        lines.append("  # no streams configured yet")
    return "\n".join(lines) + "\n"


def _missing_secret_refs(streams: list[StreamDescriptor], secrets: dict[str, str]) -> list[str]:
    missing: list[str] = []
    for stream in streams:
        if stream.experimental:
            continue
        secret_ref = stream.rtsp_password_secret_ref
        if not secret_ref:
            missing.append(f"{stream.stream_name}=<missing secret ref>")
        elif not secrets.get(secret_ref):
            missing.append(secret_ref)
    return sorted(set(missing))


def _runtime_warnings(
    session: Session,
    *,
    include_unstable_streams: bool = False,
    include_diagnostic_streams: bool = False,
) -> list[str]:
    warnings = [skipped.warning() for skipped in list_skipped_cameras(session, include_unstable_streams=include_unstable_streams)]
    if any(
        _is_hevc(stream.video_codec)
        for stream in list_go2rtc_streams(
            session,
            include_unstable_streams=include_unstable_streams,
            include_diagnostic_streams=include_diagnostic_streams,
        )
    ):
        warnings.append(HEVC_WARNING)
    if include_diagnostic_streams and any(
        stream.stream_name.endswith("_sub_ch1")
        for stream in list_go2rtc_streams(session, include_diagnostic_streams=True)
    ):
        warnings.append("Diagnostic C8C 60 /ch1/sub alias included; do not make it default until the 120 s TCP video-only test passes.")
    return warnings


def _unstable_camera_slugs(session: Session) -> list[str]:
    return [
        camera.slug
        for camera in session.query(Camera).order_by(Camera.slug).all()
        if camera.enabled and camera_reliability_status(camera) == "unstable"
    ]


def _stream_warnings(video_codec: str | None) -> list[str]:
    return [HEVC_WARNING] if _is_hevc(video_codec) else []


def _playback_status(video_codec: str | None) -> str:
    if _is_hevc(video_codec):
        return "needs_transcode"
    if video_codec:
        return "candidate"
    return "unknown"


def _quality_role(stream_role: str) -> str:
    role = stream_role.lower()
    if "main" in role:
        return "main"
    if "sub" in role:
        return "sub"
    return "unknown"


def _quality_label(quality_role: str) -> str:
    if quality_role == "main":
        return "Wysoka"
    if quality_role == "sub":
        return "Szybka"
    return "Nieznana"


def _is_hevc(video_codec: str | None) -> bool:
    return (video_codec or "").lower() in {"hevc", "h265", "h.265"}


def _normalized_path(path: str) -> str:
    return path if path.startswith("/") else f"/{path}"


def _extract_version(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        value = payload.get("version") or payload.get("go2rtc")
        return str(value) if value else None
    return None


def _extract_stream_count(response: httpx.Response) -> int | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, dict):
        return len(payload)
    if isinstance(payload, list):
        return len(payload)
    return None


def _str_or_none(value: Any) -> str | None:
    return str(value) if value not in {None, ""} else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
