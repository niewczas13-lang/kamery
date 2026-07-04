from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LocationConfig:
    id: str
    name: str
    network_cidr: str = ""


@dataclass(slots=True)
class CameraConfig:
    id: str
    name: str
    location_id: str
    model: str
    host: str
    serial_number: str = ""
    rtsp_username: str = "admin"
    rtsp_password: str = ""
    onvif_username: str = "admin"
    onvif_password: str = ""
    enabled: bool = True
    notes: str = ""

    def secrets(self) -> list[str]:
        return [
            value
            for value in (self.rtsp_password, self.onvif_password)
            if value and value != "PUT_VERIFICATION_CODE_HERE"
        ]


@dataclass(slots=True)
class ProbeConfig:
    locations: list[LocationConfig] = field(default_factory=list)
    cameras: list[CameraConfig] = field(default_factory=list)


@dataclass(slots=True)
class StreamInfo:
    path: str
    stream_role: str = "unknown"
    video_codec: str | None = None
    audio_codec: str | None = None
    resolution: str | None = None
    fps: float | None = None
    bitrate: int | None = None
    has_audio: bool = False
    probe_duration_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "stream_role": self.stream_role,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "resolution": self.resolution,
            "fps": self.fps,
            "bitrate": self.bitrate,
            "has_audio": self.has_audio,
            "probe_duration_ms": self.probe_duration_ms,
            "error": self.error,
        }


@dataclass(slots=True)
class OnvifProbeResult:
    reachable: bool = False
    status: str = "unknown"
    open_ports: list[int] = field(default_factory=list)
    port_results: list[dict[str, Any]] = field(default_factory=list)
    service_url: str | None = None
    profiles_detected: bool = False
    profiles_status: str = "unknown"
    ptz_supported: bool = False
    ptz_status: str = "unknown"
    audio_output_supported: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "status": self.status,
            "open_ports": self.open_ports,
            "port_results": self.port_results,
            "service_url": self.service_url,
            "profiles_detected": self.profiles_detected,
            "profiles_status": self.profiles_status,
            "ptz_supported": self.ptz_supported,
            "ptz_status": self.ptz_status,
            "audio_output_supported": self.audio_output_supported,
            "errors": self.errors,
        }
