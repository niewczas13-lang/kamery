from __future__ import annotations

import json
import shutil
import subprocess
from time import monotonic
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from .ffprobe import FFProbeFailed, FFProbeUnavailable, guess_stream_role, probe_rtsp_url
from .masking import sanitize_sensitive_object, sanitize_text
from .models import CameraConfig, ProbeConfig, StreamInfo
from .network import host_resolves, ping_host, tcp_port_open
from .onvif import probe_onvif

DEFAULT_RTSP_PATHS = (
    "/ch1/main",
    "/ch1/sub",
    "/Streaming/Channels/101",
    "/Streaming/Channels/102",
    "/Streaming/Channels/201",
    "/Streaming/Channels/202",
)


def probe_config(
    config: ProbeConfig,
    *,
    rtsp_paths: tuple[str, ...] = DEFAULT_RTSP_PATHS,
    camera_id: str | None = None,
    timeout_seconds: float = 8.0,
    ffprobe_bin: str = "ffprobe",
    ffmpeg_bin: str = "ffmpeg",
    rtsp_transport: str = "tcp",
    snapshot_dir: str | Path | None = None,
    include_disabled: bool = False,
) -> dict[str, object]:
    selected_cameras = [
        camera
        for camera in config.cameras
        if (include_disabled or camera.enabled) and (camera_id is None or camera.id == camera_id)
    ]
    results = [
        probe_camera(
            camera,
            rtsp_paths=rtsp_paths,
            timeout_seconds=timeout_seconds,
            ffprobe_bin=ffprobe_bin,
            ffmpeg_bin=ffmpeg_bin,
            rtsp_transport=rtsp_transport,
            snapshot_dir=snapshot_dir,
        )
        for camera in selected_cameras
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "rtsp_transport": rtsp_transport,
        "selected_camera_id": camera_id,
        "results": results,
    }


def probe_camera(
    camera: CameraConfig,
    *,
    rtsp_paths: tuple[str, ...] = DEFAULT_RTSP_PATHS,
    timeout_seconds: float = 8.0,
    ffprobe_bin: str = "ffprobe",
    ffmpeg_bin: str = "ffmpeg",
    rtsp_transport: str = "tcp",
    snapshot_dir: str | Path | None = None,
) -> dict[str, object]:
    errors: list[str] = []
    secrets = camera.secrets()

    resolves = host_resolves(camera.host)
    ping_result = ping_host(camera.host, timeout_seconds=min(timeout_seconds, 2.0)) if resolves else False
    rtsp_port_open = tcp_port_open(camera.host, 554, timeout_seconds=min(timeout_seconds, 2.0)) if resolves else False

    rtsp_path_results: list[StreamInfo] = []
    if rtsp_port_open:
        for path in rtsp_paths:
            url = build_rtsp_url(camera, path)
            started = monotonic()
            try:
                stream = probe_rtsp_url(
                    url,
                    path,
                    ffprobe_bin=ffprobe_bin,
                    rtsp_transport=rtsp_transport,
                    timeout_seconds=timeout_seconds,
                    secrets=secrets,
                )
                stream.probe_duration_ms = _duration_ms(started)
                rtsp_path_results.append(stream)
            except (FFProbeUnavailable, FFProbeFailed) as exc:
                rtsp_path_results.append(
                    StreamInfo(
                        path=path,
                        stream_role=guess_stream_role(path),
                        probe_duration_ms=_duration_ms(started),
                        error=sanitize_text(str(exc), secrets),
                    )
                )
    else:
        reason = "RTSP port 554 is not reachable"
        errors.append(reason)
        rtsp_path_results.extend(
            StreamInfo(path=path, stream_role=guess_stream_role(path), probe_duration_ms=0, error=reason)
            for path in rtsp_paths
        )

    working_streams = [stream for stream in rtsp_path_results if stream.error is None]
    if rtsp_port_open and not working_streams:
        errors.append("No RTSP paths returned a usable video stream")

    onvif = probe_onvif(camera, timeout_seconds=min(timeout_seconds, 3.0)) if resolves else None
    if onvif and onvif.errors and not onvif.reachable:
        errors.extend(onvif.errors)

    snapshot_possible = False
    snapshot_path = None
    if working_streams:
        snapshot_possible, snapshot_path, snapshot_error = capture_snapshot(
            build_rtsp_url(camera, working_streams[0].path),
            camera.id,
            ffmpeg_bin=ffmpeg_bin,
            timeout_seconds=timeout_seconds,
            rtsp_transport=rtsp_transport,
            snapshot_dir=snapshot_dir,
            secrets=secrets,
        )
        if snapshot_error:
            errors.append(snapshot_error)

    has_audio = any(stream.has_audio for stream in working_streams)
    onvif_reachable = bool(onvif and onvif.reachable)
    ptz_supported = bool(onvif and onvif.ptz_supported)
    two_way_audio_candidate = bool(has_audio and onvif and onvif.audio_output_supported)

    status = _status(
        working_streams=working_streams,
        onvif_reachable=onvif_reachable,
        snapshot_possible=snapshot_possible,
        rtsp_path_results=rtsp_path_results,
    )

    return {
        "camera_id": camera.id,
        "location_id": camera.location_id,
        "name": camera.name,
        "model": camera.model,
        "serial_number": camera.serial_number,
        "host": camera.host,
        "status": status,
        "host_resolves": resolves,
        "host_ping": ping_result,
        "rtsp_port_open": rtsp_port_open,
        "rtsp_transport": rtsp_transport,
        "rtsp_path_results": [stream.to_dict() for stream in rtsp_path_results],
        "working_rtsp_paths": [stream.to_dict() for stream in working_streams],
        "rtsp_tested_paths": list(rtsp_paths),
        "onvif_reachable": onvif_reachable,
        "onvif_status": onvif.status if onvif else "unknown",
        "onvif_open_ports": onvif.open_ports if onvif else [],
        "onvif_port_results": onvif.port_results if onvif else [],
        "onvif_profiles_detected": bool(onvif and onvif.profiles_detected),
        "onvif_profiles_status": onvif.profiles_status if onvif else "unknown",
        "ptz_supported": ptz_supported,
        "ptz_status": onvif.ptz_status if onvif else "unknown",
        "snapshot_possible": snapshot_possible,
        "snapshot_path": snapshot_path,
        "has_audio": has_audio,
        "two_way_audio_candidate": two_way_audio_candidate,
        "errors": [sanitize_text(error, secrets) for error in errors],
    }


def build_rtsp_url(camera: CameraConfig, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    username = quote(camera.rtsp_username, safe="")
    password = quote(camera.rtsp_password, safe="")
    auth = f"{username}:{password}@" if username else ""
    return f"rtsp://{auth}{camera.host}:554{normalized_path}"


def capture_snapshot(
    url: str,
    camera_id: str,
    *,
    ffmpeg_bin: str = "ffmpeg",
    timeout_seconds: float = 8.0,
    rtsp_transport: str = "tcp",
    snapshot_dir: str | Path | None = None,
    secrets: list[str] | tuple[str, ...] = (),
) -> tuple[bool, str | None, str | None]:
    executable = shutil.which(ffmpeg_bin) or ffmpeg_bin
    if shutil.which(ffmpeg_bin) is None and not _path_exists(ffmpeg_bin):
        return False, None, f"ffmpeg not found: {ffmpeg_bin}; snapshot not tested"

    directory = Path(snapshot_dir or "snapshots/probe")
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / f"{camera_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.jpg"

    command = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-rtsp_transport",
        rtsp_transport,
        "-i",
        url,
        "-frames:v",
        "1",
        str(output_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return False, None, f"ffmpeg not found: {ffmpeg_bin}; snapshot not tested"
    except subprocess.TimeoutExpired:
        return False, None, "ffmpeg timed out while capturing snapshot"

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "ffmpeg failed while capturing snapshot"
        return False, None, sanitize_text(message, secrets)

    if output_path.exists() and output_path.stat().st_size > 0:
        return True, str(output_path), None
    return False, None, "ffmpeg did not create a snapshot file"


def format_results_table(payload: dict[str, object]) -> str:
    results = payload.get("results", [])
    if not isinstance(results, list):
        return "No results"

    headers = ["camera", "host", "status", "rtsp", "onvif", "ptz", "snapshot", "errors"]
    rows = []
    for item in results:
        if not isinstance(item, dict):
            continue
        streams = item.get("working_rtsp_paths") or []
        errors = item.get("errors") or []
        rows.append(
            [
                str(item.get("camera_id", "")),
                str(item.get("host", "")),
                str(item.get("status", "")),
                str(len(streams)),
                _yes_no(bool(item.get("onvif_reachable"))),
                _yes_no(bool(item.get("ptz_supported"))),
                _yes_no(bool(item.get("snapshot_possible"))),
                str(len(errors)),
            ]
        )

    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    lines = [_format_row(headers, widths), _format_row(["-" * width for width in widths], widths)]
    lines.extend(_format_row(row, widths) for row in rows)
    return "\n".join(lines)


def _status(
    *,
    working_streams: list[StreamInfo],
    onvif_reachable: bool,
    snapshot_possible: bool,
    rtsp_path_results: list[StreamInfo],
) -> str:
    if working_streams and onvif_reachable and snapshot_possible:
        return "ok"
    if working_streams or onvif_reachable:
        return "partial"
    if any((stream.error or "").startswith("ffprobe not found") for stream in rtsp_path_results):
        return "unknown"
    return "failed"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _format_row(values: list[str], widths: list[int]) -> str:
    return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))


def to_json(payload: dict[str, object]) -> str:
    return json.dumps(sanitize_sensitive_object(payload), indent=2, ensure_ascii=False)


def _duration_ms(started: float) -> int:
    return int((monotonic() - started) * 1000)


def _path_exists(value: str) -> bool:
    try:
        return Path(value).exists()
    except OSError:
        return False
