from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction
from typing import Any

from .masking import sanitize_text
from .models import StreamInfo


class FFProbeUnavailable(RuntimeError):
    """Raised when ffprobe is not installed or cannot be executed."""


class FFProbeFailed(RuntimeError):
    """Raised when ffprobe runs but cannot inspect the stream."""


def find_binary(name_or_path: str) -> str | None:
    return shutil.which(name_or_path) or (name_or_path if shutil.which(name_or_path) else None)


def probe_rtsp_url(
    url: str,
    path: str,
    *,
    ffprobe_bin: str = "ffprobe",
    rtsp_transport: str = "tcp",
    timeout_seconds: float = 8.0,
    secrets: list[str] | tuple[str, ...] = (),
) -> StreamInfo:
    executable = shutil.which(ffprobe_bin) or ffprobe_bin
    if shutil.which(ffprobe_bin) is None and not _looks_like_existing_path(ffprobe_bin):
        raise FFProbeUnavailable(f"ffprobe not found: {ffprobe_bin}")

    command = [
        executable,
        "-hide_banner",
        "-v",
        "error",
        "-rtsp_transport",
        rtsp_transport,
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        url,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise FFProbeUnavailable(f"ffprobe not found: {ffprobe_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFProbeFailed(f"ffprobe timed out for {path}") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"ffprobe failed for {path}"
        raise FFProbeFailed(sanitize_text(message, secrets))

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FFProbeFailed(f"ffprobe returned invalid JSON for {path}") from exc

    return parse_ffprobe_json(payload, path)


def parse_ffprobe_json(payload: dict[str, Any], path: str) -> StreamInfo:
    streams = payload.get("streams") or []
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)

    if video_stream is None:
        raise FFProbeFailed(f"No video stream detected for {path}")

    width = video_stream.get("width")
    height = video_stream.get("height")
    resolution = f"{width}x{height}" if width and height else None

    bitrate = _first_int(
        video_stream.get("bit_rate"),
        (payload.get("format") or {}).get("bit_rate"),
    )

    return StreamInfo(
        path=path,
        stream_role=guess_stream_role(path),
        video_codec=video_stream.get("codec_name"),
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        resolution=resolution,
        fps=_parse_rate(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        bitrate=bitrate,
        has_audio=audio_stream is not None,
    )


def guess_stream_role(path: str) -> str:
    normalized = path.strip().lower()
    if normalized == "/ch1/main":
        return "main"
    if normalized == "/ch1/sub":
        return "sub"
    if normalized.endswith("/101"):
        return "lens1_main"
    if normalized.endswith("/102"):
        return "lens1_sub"
    if normalized.endswith("/201"):
        return "lens2_main"
    if normalized.endswith("/202"):
        return "lens2_sub"
    return "unknown"


def _parse_rate(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        rate = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return round(rate, 2)


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _looks_like_existing_path(value: str) -> bool:
    try:
        from pathlib import Path

        return Path(value).exists()
    except OSError:
        return False
