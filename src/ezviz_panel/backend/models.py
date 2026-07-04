from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    network_cidr: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    cameras: Mapped[list["Camera"]] = relationship(back_populates="location", cascade="all, delete-orphan")


class Camera(Base, TimestampMixin):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(260))
    host: Mapped[str] = mapped_column(String(260), nullable=False)
    rtsp_username: Mapped[str] = mapped_column(String(160), default="admin")
    rtsp_password_secret_ref: Mapped[str | None] = mapped_column(String(160))
    onvif_username: Mapped[str] = mapped_column(String(160), default="admin")
    onvif_password_secret_ref: Mapped[str | None] = mapped_column(String(160))
    main_stream_path: Mapped[str | None] = mapped_column(String(260))
    sub_stream_path: Mapped[str | None] = mapped_column(String(260))
    secondary_main_stream_path: Mapped[str | None] = mapped_column(String(260))
    secondary_sub_stream_path: Mapped[str | None] = mapped_column(String(260))
    video_codec: Mapped[str | None] = mapped_column(String(64))
    audio_codec: Mapped[str | None] = mapped_column(String(64))
    video_status: Mapped[str] = mapped_column(String(32), default="unknown")
    control_status: Mapped[str] = mapped_column(String(32), default="unknown")
    probe_status: Mapped[str] = mapped_column(String(32), default="unknown")
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ptz: Mapped[bool] = mapped_column(Boolean, default=False)
    has_onvif: Mapped[bool] = mapped_column(Boolean, default=False)
    has_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    has_two_way_audio_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    location: Mapped[Location] = relationship(back_populates="cameras")
    probe_results: Mapped[list["CameraProbeResult"]] = relationship(back_populates="camera", cascade="all, delete-orphan")
    recording_policy: Mapped["RecordingPolicy | None"] = relationship(
        back_populates="camera",
        cascade="all, delete-orphan",
        uselist=False,
    )
    events: Mapped[list["Event"]] = relationship(back_populates="camera", cascade="all, delete-orphan")


class CameraProbeResult(Base):
    __tablename__ = "camera_probe_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    raw_result_json: Mapped[str] = mapped_column(Text, nullable=False)
    sanitized_result_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    camera: Mapped[Camera] = relationship(back_populates="probe_results")


class RecordingPolicy(Base):
    __tablename__ = "recording_policies"
    __table_args__ = (UniqueConstraint("camera_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(64), default="disabled")
    retention_days: Mapped[int] = mapped_column(Integer, default=7)
    record_main_stream: Mapped[bool] = mapped_column(Boolean, default=False)
    detect_sub_stream: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    camera: Mapped[Camera] = relationship(back_populates="recording_policy")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    camera_id: Mapped[int] = mapped_column(ForeignKey("cameras.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str | None] = mapped_column(String(120))
    score: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    clip_path: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[str | None] = mapped_column(Text)

    camera: Mapped[Camera] = relationship(back_populates="events")


class Admin(Base, TimestampMixin):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(260), nullable=False)
