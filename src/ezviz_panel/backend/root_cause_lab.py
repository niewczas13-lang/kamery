from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from ezviz_panel.camera_probe.masking import sanitize_sensitive_object, sanitize_text

from .log_sanitizer import VERIFICATION_FIELD_RE


FRAME_RE = re.compile(r"frame=\s*(\d+)")
FPS_RE = re.compile(r"\bfps=\s*([0-9]*\.?[0-9]+)")
SPEED_RE = re.compile(r"\bspeed=\s*([0-9]*\.?[0-9]+)x")
TIME_RE = re.compile(r"\btime=(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")
HEVC_ERROR_PATTERNS = (
    "pps id out of range",
    "could not find ref",
    "skipping invalid undecodable nalu",
    "error while decoding",
    "invalid data found",
)


@dataclass(frozen=True)
class FfmpegMetrics:
    connected: bool
    target_duration_seconds: int
    actual_duration_seconds: float
    frames: int
    fps: float | None
    speed: float | None
    eof_count: int
    timeout: bool
    hevc_error_count: int
    stable: bool
    exit_code: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sanitize_root_cause_text(text: str, secret_values: list[str] | tuple[str, ...] = ()) -> str:
    sanitized = sanitize_text(text, secret_values)
    return VERIFICATION_FIELD_RE.sub(lambda match: f"{match.group(1)}***", sanitized)


def parse_ffmpeg_log(text: str, *, target_duration_seconds: int, exit_code: int | None = None) -> FfmpegMetrics:
    frames = _last_int(FRAME_RE, text, default=0)
    fps = _last_float(FPS_RE, text)
    speed = _last_float(SPEED_RE, text)
    actual_duration = _last_duration_seconds(text)
    lowered = text.lower()
    eof_count = lowered.count("end of file") + lowered.count("eof")
    timeout = "timed out" in lowered or "timeout" in lowered
    hevc_errors = sum(1 for line in lowered.splitlines() if any(pattern in line for pattern in HEVC_ERROR_PATTERNS))
    connected = "input #0" in lowered or "stream #0:" in lowered or frames > 0
    exit_ok = exit_code in {None, 0}
    reached_duration = actual_duration >= (target_duration_seconds * 0.95)
    stable = bool(exit_ok and connected and frames > 0 and reached_duration and eof_count == 0 and not timeout)
    return FfmpegMetrics(
        connected=connected,
        target_duration_seconds=target_duration_seconds,
        actual_duration_seconds=actual_duration,
        frames=frames,
        fps=fps,
        speed=speed,
        eof_count=eof_count,
        timeout=timeout,
        hevc_error_count=hevc_errors,
        stable=stable,
        exit_code=exit_code,
    )


def classify_root_cause(
    *,
    direct_stable: bool | None = None,
    go2rtc_stable: bool | None = None,
    panel_stable: bool | None = None,
    frigate_off_improves: bool | None = None,
    recorder_off_improves: bool | None = None,
    lan_stable: bool | None = None,
    vpn_stable: bool | None = None,
    cpu_or_gpu_saturated: bool | None = None,
) -> list[str]:
    conclusions: list[str] = []
    if direct_stable is False and go2rtc_stable is False:
        conclusions.append("Problem jest prawdopodobnie w: kamera, sieć, Wi-Fi, VPN albo rejestrator.")
    if direct_stable is True and go2rtc_stable is False:
        conclusions.append("Problem jest prawdopodobnie w konfiguracji go2rtc albo restreamu.")
    if direct_stable is True and go2rtc_stable is True and panel_stable is False:
        conclusions.append("Problem jest prawdopodobnie w frontendzie, przeglądarce, HEVC decode albo zbyt wielu aktywnych streamach.")
    if frigate_off_improves:
        conclusions.append("Frigate zwiększa obciążenie lub konkurencję o streamy.")
    if recorder_off_improves:
        conclusions.append("Rejestrator lub dodatkowe sesje RTSP obciążają kamerę albo sieć.")
    if lan_stable is True and vpn_stable is False:
        conclusions.append("Problem jest prawdopodobnie w VPN, upload/download, routingu albo jitterze.")
    if cpu_or_gpu_saturated:
        conclusions.append("Problem jest prawdopodobnie w dekodowaniu HEVC albo zbyt wielu aktywnych streamach.")
    if not conclusions:
        conclusions.append("Brak jednoznacznej klasyfikacji; porównaj direct RTSP, go2rtc, panel, Frigate, rejestrator i VPN.")
    return conclusions


def compare_c8c60_paths(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {"preferred_sub_path": None, "preferred_stream": None, "reason": "brak wyników"}
    best = sorted(results, key=_path_score, reverse=True)[0]
    if not any(result.get("stable") for result in results):
        return {
            "preferred_sub_path": None,
            "preferred_stream": None,
            "least_bad_sub_path": best.get("path"),
            "least_bad_stream": best.get("name") or best.get("stream"),
            "reason": "Brak stabilnego pathu C8C 60; nie ustawiaj preferred_sub_path na podstawie tego przebiegu.",
            "score": _path_score(best),
            "all_candidates_unstable": True,
        }
    return {
        "preferred_sub_path": best.get("path"),
        "preferred_stream": best.get("name") or best.get("stream"),
        "least_bad_sub_path": best.get("path"),
        "least_bad_stream": best.get("name") or best.get("stream"),
        "reason": (
            "Wybrano stabilniejszy path na podstawie: stable, fps, speed, EOF i liczby błędów HEVC."
        ),
        "score": _path_score(best),
        "all_candidates_unstable": False,
    }


def render_report_json(payload: dict[str, Any], *, secret_values: list[str] | tuple[str, ...] = ()) -> str:
    sanitized = sanitize_sensitive_object(payload, secret_values)
    text = json.dumps(sanitized, indent=2, ensure_ascii=False)
    return sanitize_root_cause_text(text, secret_values)


def render_report_markdown(payload: dict[str, Any], *, secret_values: list[str] | tuple[str, ...] = ()) -> str:
    sanitized = json.loads(render_report_json(payload, secret_values=secret_values))
    sections = [
        ("Podsumowanie", sanitized.get("summary") or "Brak podsumowania."),
        ("Topologia testu", sanitized.get("topology") or "Do uzupełnienia po uruchomieniu testu."),
        ("Kamery", sanitized.get("cameras") or []),
        ("Wyniki direct camera", sanitized.get("direct_camera") or []),
        ("Wyniki go2rtc", sanitized.get("go2rtc") or []),
        ("C8C 60 path comparison", sanitized.get("c8c60_path_comparison") or {}),
        ("Frigate impact", sanitized.get("frigate_impact") or {}),
        ("Rejestrator impact", sanitized.get("recorder_impact") or {}),
        ("WireGuard/VPN impact", sanitized.get("vpn_impact") or {}),
        ("Docker stats", sanitized.get("docker_stats") or {}),
        ("Browser decode notes", sanitized.get("browser_decode_notes") or ""),
        ("Wnioski", sanitized.get("conclusions") or []),
        ("Rekomendowane następne kroki", sanitized.get("next_steps") or []),
    ]
    lines = ["# Root Cause Lab - raport", ""]
    for title, value in sections:
        lines.extend([f"## {title}", "", _markdown_value(value), ""])
    return sanitize_root_cause_text("\n".join(lines).rstrip() + "\n", secret_values)


def _path_score(result: dict[str, Any]) -> float:
    score = 0.0
    if result.get("stable"):
        score += 10_000
    score += float(result.get("fps") or 0) * 100
    score += float(result.get("speed") or 0) * 100
    score -= float(result.get("eof_count") or 0) * 500
    score -= float(result.get("hevc_error_count") or 0) * 5
    return score


def _markdown_value(value: Any) -> str:
    if isinstance(value, str):
        return value or "-"
    if isinstance(value, list):
        if not value:
            return "-"
        if all(isinstance(item, str) for item in value):
            return "\n".join(f"- {item}" for item in value)
    return f"```json\n{json.dumps(value, indent=2, ensure_ascii=False)}\n```"


def _last_int(pattern: re.Pattern[str], text: str, *, default: int) -> int:
    matches = pattern.findall(text)
    return int(matches[-1]) if matches else default


def _last_float(pattern: re.Pattern[str], text: str) -> float | None:
    matches = pattern.findall(text)
    return float(matches[-1]) if matches else None


def _last_duration_seconds(text: str) -> float:
    matches = TIME_RE.findall(text)
    if not matches:
        return 0.0
    hours, minutes, seconds = matches[-1]
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
