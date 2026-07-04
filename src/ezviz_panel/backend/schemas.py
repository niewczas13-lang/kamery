from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    ok: bool
    database: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime
    updated_at: datetime


class LocationBase(BaseModel):
    name: str | None = None
    slug: str | None = None
    network_cidr: str | None = None
    description: str | None = None


class LocationCreate(LocationBase):
    name: str


class LocationUpdate(LocationBase):
    pass


class LocationResponse(LocationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class CameraBase(BaseModel):
    location_id: int | None = None
    name: str | None = None
    slug: str | None = None
    model: str | None = None
    serial_number: str | None = None
    host: str | None = None
    rtsp_username: str | None = None
    rtsp_password_secret_ref: str | None = None
    onvif_username: str | None = None
    onvif_password_secret_ref: str | None = None
    main_stream_path: str | None = None
    sub_stream_path: str | None = None
    secondary_main_stream_path: str | None = None
    secondary_sub_stream_path: str | None = None
    video_status: str | None = None
    control_status: str | None = None
    probe_status: str | None = None
    reliability_status: str | None = None
    has_audio: bool | None = None
    has_ptz: bool | None = None
    has_onvif: bool | None = None
    has_snapshot: bool | None = None
    has_two_way_audio_candidate: bool | None = None
    enabled: bool | None = None
    notes: str | None = None


class CameraCreate(CameraBase):
    location_id: int
    name: str
    model: str
    host: str
    rtsp_username: str = "admin"
    onvif_username: str = "admin"
    enabled: bool = True


class CameraUpdate(CameraBase):
    pass


class CameraResponse(CameraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: int
    name: str
    slug: str
    model: str
    host: str
    rtsp_username: str
    onvif_username: str
    video_status: str
    control_status: str
    probe_status: str
    reliability_status: str
    has_audio: bool
    has_ptz: bool
    has_onvif: bool
    has_snapshot: bool
    has_two_way_audio_candidate: bool
    enabled: bool
    rtsp_secret_configured: bool = False
    onvif_secret_configured: bool = False
    created_at: datetime
    updated_at: datetime


class ProbeImportRequest(BaseModel):
    probe_result: dict[str, Any] = Field(default_factory=dict)
    sanitized_result: dict[str, Any] | None = None


class ProbeResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: int
    status: str
    created_at: datetime


class ProbeResultDetail(ProbeResultResponse):
    raw_result_json: str
    sanitized_result_json: str | None = None


class ApplyProbeResponse(BaseModel):
    camera: CameraResponse
    applied: dict[str, Any]


class Go2RtcPreviewResponse(BaseModel):
    yaml: str
    warnings: list[str]


class StreamResponse(BaseModel):
    stream_name: str
    camera_id: int
    camera_name: str
    location_id: int
    stream_role: str
    path: str
    video_codec: str | None = None
    audio_codec: str | None = None
    resolution: str | None = None
    fps: float | None = None
    has_audio: bool
    quality_role: Literal["main", "sub", "unknown"]
    quality_label: str
    is_recommended_for_grid: bool
    is_recommended_for_focus: bool
    is_recommended_for_recording: bool
    is_recommended_for_detection: bool
    playback_status: Literal["unknown", "candidate", "unsupported", "needs_transcode", "ok"]
    warnings: list[str]


class Go2RtcRuntimeRenderResponse(BaseModel):
    output_path: str
    stream_count: int
    skipped_cameras: list[str]
    unstable_cameras: list[str] = Field(default_factory=list)
    warnings: list[str]


class Go2RtcHealthResponse(BaseModel):
    reachable: bool
    version: str | None = None
    stream_count: int | None = None
    error: str | None = None


class Go2RtcStreamsProxyResponse(BaseModel):
    reachable: bool
    streams: Any | None = None
    error: str | None = None


class LiveDiagnosticsResponse(BaseModel):
    backend: dict[str, Any]
    go2rtc: dict[str, Any]
    frigate: dict[str, Any]
    stream_count: int
    active_streams: dict[str, Any]
    active_stream_limit: dict[str, Any]
    stream_stability: list[dict[str, Any]]
    warnings: list[str]


class FrigateCameraConfigResponse(BaseModel):
    name: str
    camera_slug: str
    camera_id: int
    detect_stream: str
    record_stream: str
    retention_days: int
    mode: str
    warnings: list[str] = Field(default_factory=list)


class FrigatePreviewResponse(BaseModel):
    yaml: str
    cameras: list[FrigateCameraConfigResponse]
    warnings: list[str]


class FrigateRuntimeRenderResponse(FrigatePreviewResponse):
    output_path: str


class FrigateHealthResponse(BaseModel):
    reachable: bool
    version: str | None = None
    error: str | None = None


class FrigateCamerasProxyResponse(BaseModel):
    reachable: bool
    cameras: Any | None = None
    error: str | None = None


class FrigateEventsProxyResponse(BaseModel):
    reachable: bool
    events: Any | None = None
    error: str | None = None


class FrigateEventProxyResponse(BaseModel):
    reachable: bool
    event: Any | None = None
    error: str | None = None


class FrigateRecordingsProxyResponse(BaseModel):
    reachable: bool
    recordings: Any | None = None
    error: str | None = None


class SnapshotResponse(BaseModel):
    camera_id: int
    camera_name: str
    path: str
    source_path: str
    created_at: datetime


PTZCommand = Literal["up", "down", "left", "right", "zoom_in", "zoom_out", "stop"]


class PtzCommandRequest(BaseModel):
    duration_ms: int = Field(default=300, ge=1, le=1500)
    speed: float = Field(default=0.3, ge=0.05, le=1.0)


class PtzCommandResponse(BaseModel):
    camera_id: int
    command: PTZCommand
    status: Literal["moved", "stopped"]
    duration_ms: int
    stopped: bool
    warning: str | None = None


RecordingMode = Literal["disabled", "events_only", "continuous", "continuous_selected_hours"]


class RecordingPolicyResponse(BaseModel):
    camera_id: int
    camera_name: str
    camera_slug: str
    mode: RecordingMode
    retention_days: int
    record_main_stream: bool
    detect_sub_stream: bool
    enabled: bool


class RecordingPolicyUpdate(BaseModel):
    mode: RecordingMode | None = None
    retention_days: int | None = Field(default=None, ge=1, le=30)
