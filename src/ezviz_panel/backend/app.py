from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path
import subprocess
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ezviz_panel.camera_probe.config import ConfigError

from .database import SessionLocal, engine as default_engine, init_db
from .frigate import (
    fetch_frigate_cameras,
    fetch_frigate_event,
    fetch_frigate_events,
    fetch_frigate_health,
    fetch_frigate_recordings,
    get_or_create_recording_policy,
    recording_policy_response,
    render_frigate_preview,
    render_frigate_runtime_config,
    update_recording_policy,
)
from .go2rtc import (
    Go2RtcConfigError,
    HEVC_WARNING,
    MissingSecretError,
    best_snapshot_path,
    build_rtsp_runtime_url_for_camera,
    fetch_go2rtc_health,
    fetch_go2rtc_streams,
    find_go2rtc_stream,
    list_go2rtc_streams,
    list_skipped_cameras,
    mask_secret_values,
    render_go2rtc_preview,
    render_go2rtc_runtime_config,
)
from .models import Admin, Camera, CameraProbeResult, Location, RecordingPolicy
from .onvif_ptz import PtzAdapter, PtzError, execute_ptz_command
from .probe_importer import ProbeImportError, apply_probe_result, camera_reliability_status, import_probe_result
from .schemas import (
    AdminResponse,
    ApplyProbeResponse,
    CameraCreate,
    CameraResponse,
    CameraUpdate,
    Go2RtcHealthResponse,
    Go2RtcPreviewResponse,
    Go2RtcRuntimeRenderResponse,
    Go2RtcStreamsProxyResponse,
    FrigateCamerasProxyResponse,
    FrigateEventProxyResponse,
    FrigateEventsProxyResponse,
    FrigateHealthResponse,
    FrigatePreviewResponse,
    FrigateRecordingsProxyResponse,
    FrigateRuntimeRenderResponse,
    HealthResponse,
    LiveDiagnosticsResponse,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
    LoginRequest,
    ProbeResultDetail,
    ProbeResultResponse,
    PtzCommandRequest,
    PtzCommandResponse,
    RecordingPolicyResponse,
    RecordingPolicyUpdate,
    SnapshotResponse,
    StreamResponse,
    TokenResponse,
)
from .secrets import load_secret_refs, secret_configured
from .security import create_access_token, decode_access_token, verify_password
from .settings import Settings, load_settings
from .utils import slugify


bearer = HTTPBearer(auto_error=False)


def create_app(
    *,
    settings: Settings | None = None,
    database_engine: Engine | None = None,
    ptz_adapter: PtzAdapter | None = None,
    frigate_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    app_settings = settings or load_settings()
    db_engine = database_engine or default_engine
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    app = FastAPI(title="EZVIZ Panel API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_db() -> Session:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def current_admin(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
        session: Session = Depends(get_db),
    ) -> Admin:
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
        username = decode_access_token(credentials.credentials, secret_key=app_settings.secret_key)
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        admin = session.query(Admin).filter(Admin.username == username).first()
        if admin is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
        return admin

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health(session: Session = Depends(get_db)) -> HealthResponse:
        session.execute(text("select 1"))
        return HealthResponse(ok=True, database="ok")

    @app.post("/api/v1/auth/login", response_model=TokenResponse)
    def login(payload: LoginRequest, session: Session = Depends(get_db)) -> TokenResponse:
        admin = session.query(Admin).filter(Admin.username == payload.username).first()
        if admin is None or not verify_password(payload.password, admin.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
        return TokenResponse(
            access_token=create_access_token(
                username=admin.username,
                secret_key=app_settings.secret_key,
                expires_minutes=app_settings.access_token_expire_minutes,
            )
        )

    @app.get("/api/v1/auth/me", response_model=AdminResponse)
    def me(admin: Admin = Depends(current_admin)) -> Admin:
        return admin

    @app.post("/api/v1/auth/logout", status_code=204)
    def logout(_: Admin = Depends(current_admin)) -> Response:
        return Response(status_code=204)

    @app.get("/api/v1/locations", response_model=list[LocationResponse])
    def list_locations(_: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> list[Location]:
        return session.query(Location).order_by(Location.slug).all()

    @app.post("/api/v1/locations", response_model=LocationResponse, status_code=201)
    def create_location(
        payload: LocationCreate,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> Location:
        location = Location(
            name=payload.name,
            slug=payload.slug or slugify(payload.name),
            network_cidr=payload.network_cidr,
            description=payload.description,
        )
        session.add(location)
        session.commit()
        session.refresh(location)
        return location

    @app.get("/api/v1/locations/{location_id}", response_model=LocationResponse)
    def get_location(location_id: int, _: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> Location:
        return _get_location(session, location_id)

    @app.patch("/api/v1/locations/{location_id}", response_model=LocationResponse)
    def update_location(
        location_id: int,
        payload: LocationUpdate,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> Location:
        location = _get_location(session, location_id)
        updates = payload.model_dump(exclude_unset=True)
        if "slug" in updates and updates["slug"] is None and "name" in updates:
            updates["slug"] = slugify(updates["name"])
        for key, value in updates.items():
            if value is not None:
                setattr(location, key, value)
        session.commit()
        session.refresh(location)
        return location

    @app.delete("/api/v1/locations/{location_id}", status_code=204)
    def delete_location(location_id: int, _: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> Response:
        location = _get_location(session, location_id)
        session.delete(location)
        session.commit()
        return Response(status_code=204)

    @app.get("/api/v1/cameras", response_model=list[CameraResponse])
    def list_cameras(_: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> list[CameraResponse]:
        secrets = load_secret_refs(app_settings.secrets_env_file)
        return [_camera_response(camera, secrets) for camera in session.query(Camera).order_by(Camera.slug).all()]

    @app.post("/api/v1/cameras", response_model=CameraResponse, status_code=201)
    def create_camera(
        payload: CameraCreate,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> CameraResponse:
        _get_location(session, payload.location_id)
        camera = Camera(
            location_id=payload.location_id,
            name=payload.name,
            slug=payload.slug or slugify(payload.name),
            model=payload.model,
            serial_number=payload.serial_number,
            host=payload.host,
            rtsp_username=payload.rtsp_username,
            rtsp_password_secret_ref=payload.rtsp_password_secret_ref,
            onvif_username=payload.onvif_username,
            onvif_password_secret_ref=payload.onvif_password_secret_ref,
            has_audio=payload.has_audio if payload.has_audio is not None else False,
            has_ptz=payload.has_ptz if payload.has_ptz is not None else False,
            has_onvif=payload.has_onvif if payload.has_onvif is not None else False,
            has_snapshot=payload.has_snapshot if payload.has_snapshot is not None else False,
            has_two_way_audio_candidate=(
                payload.has_two_way_audio_candidate if payload.has_two_way_audio_candidate is not None else False
            ),
            enabled=payload.enabled,
            notes=payload.notes,
        )
        session.add(camera)
        session.flush()
        session.add(RecordingPolicy(camera_id=camera.id))
        session.commit()
        session.refresh(camera)
        return _camera_response(camera, load_secret_refs(app_settings.secrets_env_file))

    @app.get("/api/v1/cameras/{camera_id}", response_model=CameraResponse)
    def get_camera(camera_id: int, _: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> CameraResponse:
        return _camera_response(_get_camera(session, camera_id), load_secret_refs(app_settings.secrets_env_file))

    @app.patch("/api/v1/cameras/{camera_id}", response_model=CameraResponse)
    def update_camera(
        camera_id: int,
        payload: CameraUpdate,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> CameraResponse:
        camera = _get_camera(session, camera_id)
        updates = payload.model_dump(exclude_unset=True)
        if "slug" in updates and updates["slug"] is None and updates.get("name"):
            updates["slug"] = slugify(updates["name"])
        for key, value in updates.items():
            if value is not None:
                setattr(camera, key, value)
        session.commit()
        session.refresh(camera)
        return _camera_response(camera, load_secret_refs(app_settings.secrets_env_file))

    @app.delete("/api/v1/cameras/{camera_id}", status_code=204)
    def delete_camera(camera_id: int, _: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> Response:
        camera = _get_camera(session, camera_id)
        session.delete(camera)
        session.commit()
        return Response(status_code=204)

    @app.post("/api/v1/cameras/{camera_id}/probe-results/import", response_model=ProbeResultResponse, status_code=201)
    def import_camera_probe_result(
        camera_id: int,
        payload: dict[str, Any],
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> CameraProbeResult:
        camera = _get_camera(session, camera_id)
        probe_payload = payload.get("probe_result") if "probe_result" in payload else payload
        if not isinstance(probe_payload, dict):
            raise HTTPException(status_code=400, detail="probe_result must be an object")
        try:
            return import_probe_result(session, camera, probe_payload)
        except ProbeImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/cameras/{camera_id}/probe-results", response_model=list[ProbeResultResponse])
    def list_probe_results(
        camera_id: int,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> list[CameraProbeResult]:
        _get_camera(session, camera_id)
        return (
            session.query(CameraProbeResult)
            .filter(CameraProbeResult.camera_id == camera_id)
            .order_by(CameraProbeResult.created_at.desc())
            .all()
        )

    @app.get("/api/v1/cameras/{camera_id}/probe-results/latest", response_model=ProbeResultDetail)
    def latest_probe_result(
        camera_id: int,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> CameraProbeResult:
        _get_camera(session, camera_id)
        result = (
            session.query(CameraProbeResult)
            .filter(CameraProbeResult.camera_id == camera_id)
            .order_by(CameraProbeResult.created_at.desc())
            .first()
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Probe result not found")
        return result

    @app.post("/api/v1/cameras/{camera_id}/apply-probe-result/{probe_result_id}", response_model=ApplyProbeResponse)
    def apply_probe(
        camera_id: int,
        probe_result_id: int,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> ApplyProbeResponse:
        camera = _get_camera(session, camera_id)
        probe = (
            session.query(CameraProbeResult)
            .filter(CameraProbeResult.id == probe_result_id, CameraProbeResult.camera_id == camera_id)
            .first()
        )
        if probe is None:
            raise HTTPException(status_code=404, detail="Probe result not found")
        analysis = apply_probe_result(session, camera, probe)
        return ApplyProbeResponse(camera=_camera_response(camera, load_secret_refs(app_settings.secrets_env_file)), applied=analysis.to_update_dict())

    @app.post("/api/v1/cameras/{camera_id}/ptz/{command}", response_model=PtzCommandResponse)
    def ptz_command(
        camera_id: int,
        command: str,
        payload: PtzCommandRequest | None = Body(default=None),
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        camera = _get_camera(session, camera_id)
        request = payload or PtzCommandRequest()
        try:
            result = execute_ptz_command(
                camera,
                command,
                secrets=load_secret_refs(app_settings.secrets_env_file),
                adapter=ptz_adapter,
                duration_ms=request.duration_ms,
                speed=request.speed,
            )
        except PtzError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return result.to_public_dict()

    @app.get("/api/v1/streams", response_model=list[StreamResponse])
    def list_streams(_: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> list[dict[str, Any]]:
        return [
            stream.to_public_dict()
            for stream in list_go2rtc_streams(
                session,
                enable_experimental_transcode=app_settings.enable_experimental_transcode,
                include_unstable_streams=True,
            )
        ]

    @app.get("/api/v1/streams/{stream_name}", response_model=StreamResponse)
    def get_stream(
        stream_name: str,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        stream = find_go2rtc_stream(
            session,
            stream_name,
            enable_experimental_transcode=app_settings.enable_experimental_transcode,
            include_unstable_streams=True,
        )
        if stream is None:
            raise HTTPException(status_code=404, detail="Stream not found")
        return stream.to_public_dict()

    @app.get("/api/v1/config/go2rtc/preview", response_model=Go2RtcPreviewResponse)
    def go2rtc_preview(_: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> Go2RtcPreviewResponse:
        yaml_text, warnings = render_go2rtc_preview(
            session,
            enable_experimental_transcode=app_settings.enable_experimental_transcode,
            include_unstable_streams=True,
        )
        return Go2RtcPreviewResponse(yaml=yaml_text, warnings=warnings)

    @app.post("/api/v1/config/go2rtc/render-preview", response_model=Go2RtcPreviewResponse)
    def go2rtc_render_preview(_: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> Go2RtcPreviewResponse:
        yaml_text, warnings = render_go2rtc_preview(
            session,
            enable_experimental_transcode=app_settings.enable_experimental_transcode,
            include_unstable_streams=True,
        )
        return Go2RtcPreviewResponse(yaml=yaml_text, warnings=warnings)

    @app.post("/api/v1/config/go2rtc/render-runtime", response_model=Go2RtcRuntimeRenderResponse)
    def go2rtc_render_runtime(
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        try:
            result = render_go2rtc_runtime_config(
                session,
                secrets_env_file=app_settings.secrets_env_file,
                output_path=app_settings.go2rtc_config_path,
                enable_experimental_transcode=app_settings.enable_experimental_transcode,
                include_unstable_streams=True,
            )
        except Go2RtcConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result.to_public_dict()

    @app.get("/api/v1/go2rtc/health", response_model=Go2RtcHealthResponse)
    def go2rtc_health(_: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_go2rtc_health(app_settings.go2rtc_url)

    @app.get("/api/v1/go2rtc/streams", response_model=Go2RtcStreamsProxyResponse)
    def go2rtc_runtime_streams(_: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_go2rtc_streams(app_settings.go2rtc_url)

    @app.get("/api/v1/diagnostics/live", response_model=LiveDiagnosticsResponse)
    def live_diagnostics(_: Admin = Depends(current_admin), session: Session = Depends(get_db)) -> dict[str, Any]:
        session.execute(text("select 1"))
        streams = list_go2rtc_streams(
            session,
            enable_experimental_transcode=app_settings.enable_experimental_transcode,
            include_unstable_streams=True,
        )
        cameras = session.query(Camera).order_by(Camera.slug).all()
        go2rtc_payload = fetch_go2rtc_health(app_settings.go2rtc_url)
        frigate_payload = fetch_frigate_health(app_settings.frigate_url, transport=frigate_transport)
        warnings = _live_diagnostics_warnings(cameras, streams)
        return {
            "backend": {"ok": True, "database": "ok"},
            "go2rtc": go2rtc_payload,
            "frigate": frigate_payload,
            "stream_count": len(streams),
            "active_streams": {
                "current": None,
                "source": "frontend video wall",
                "note": "Aktywne iframe'y są limitowane w UI, backend nie widzi lokalnego stanu przeglądarki.",
            },
            "active_stream_limit": {
                "default": 4,
                "options": [2, 4, 6, 9, "bez limitu"],
                "eco_mode": 2,
            },
            "stream_stability": [_stream_stability_summary(camera) for camera in cameras if camera.enabled],
            "warnings": warnings,
        }

    @app.get("/api/v1/recording-policies", response_model=list[RecordingPolicyResponse])
    def list_recording_policies(
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> list[dict[str, Any]]:
        policies = []
        for camera in session.query(Camera).order_by(Camera.slug).all():
            policy = get_or_create_recording_policy(session, camera)
            policies.append(recording_policy_response(policy, camera))
        session.commit()
        return policies

    @app.get("/api/v1/cameras/{camera_id}/recording-policy", response_model=RecordingPolicyResponse)
    def get_recording_policy(
        camera_id: int,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        camera = _get_camera(session, camera_id)
        policy = get_or_create_recording_policy(session, camera)
        session.commit()
        return recording_policy_response(policy, camera)

    @app.patch("/api/v1/cameras/{camera_id}/recording-policy", response_model=RecordingPolicyResponse)
    def patch_recording_policy(
        camera_id: int,
        payload: RecordingPolicyUpdate,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        camera = _get_camera(session, camera_id)
        policy = get_or_create_recording_policy(session, camera)
        updates = payload.model_dump(exclude_unset=True)
        try:
            update_recording_policy(policy, mode=updates.get("mode"), retention_days=updates.get("retention_days"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session.commit()
        session.refresh(policy)
        return recording_policy_response(policy, camera)

    @app.get("/api/v1/frigate/config/preview", response_model=FrigatePreviewResponse)
    def frigate_config_preview(
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return render_frigate_preview(session).to_public_dict()

    @app.post("/api/v1/frigate/config/render-runtime", response_model=FrigateRuntimeRenderResponse)
    def frigate_config_render_runtime(
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> dict[str, Any]:
        return render_frigate_runtime_config(session, output_path=app_settings.frigate_config_path).to_public_dict()

    @app.get("/api/v1/frigate/health", response_model=FrigateHealthResponse)
    def frigate_health(_: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_frigate_health(app_settings.frigate_url, transport=frigate_transport)

    @app.get("/api/v1/frigate/cameras", response_model=FrigateCamerasProxyResponse)
    def frigate_cameras(_: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_frigate_cameras(app_settings.frigate_url, transport=frigate_transport)

    @app.get("/api/v1/frigate/events", response_model=FrigateEventsProxyResponse)
    def frigate_events(_: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_frigate_events(app_settings.frigate_url, transport=frigate_transport)

    @app.get("/api/v1/frigate/events/{event_id}", response_model=FrigateEventProxyResponse)
    def frigate_event(event_id: str, _: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_frigate_event(app_settings.frigate_url, event_id, transport=frigate_transport)

    @app.get("/api/v1/frigate/recordings", response_model=FrigateRecordingsProxyResponse)
    def frigate_recordings(_: Admin = Depends(current_admin)) -> dict[str, Any]:
        return fetch_frigate_recordings(app_settings.frigate_url, transport=frigate_transport)

    @app.post("/api/v1/cameras/{camera_id}/snapshot", response_model=SnapshotResponse)
    def create_camera_snapshot(
        camera_id: int,
        _: Admin = Depends(current_admin),
        session: Session = Depends(get_db),
    ) -> SnapshotResponse:
        camera = _get_camera(session, camera_id)
        source_path = best_snapshot_path(camera)
        if source_path is None or camera.video_status == "unavailable":
            raise HTTPException(status_code=409, detail="Camera has no video stream for snapshot")
        try:
            secrets = load_secret_refs(app_settings.secrets_env_file)
            rtsp_url = build_rtsp_runtime_url_for_camera(camera, source_path, secrets)
        except (ConfigError, MissingSecretError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        created_at = datetime.now(UTC)
        output_dir = Path(app_settings.snapshot_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{camera.slug}-{created_at.strftime('%Y%m%dT%H%M%SZ')}.jpg"
        command = [
            app_settings.ffmpeg_bin,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-frames:v",
            "1",
            str(output_path),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=25, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(status_code=502, detail=f"ffmpeg snapshot failed: {exc}") from exc
        if completed.returncode != 0:
            stderr = mask_secret_values(completed.stderr.strip() or "ffmpeg returned an error", secrets)
            raise HTTPException(status_code=502, detail=f"ffmpeg snapshot failed: {stderr}")
        return SnapshotResponse(
            camera_id=camera.id,
            camera_name=camera.name,
            path=str(output_path),
            source_path=source_path,
            created_at=created_at,
        )

    @app.get("/debug/streams", response_class=HTMLResponse)
    def debug_streams(request: Request, session: Session = Depends(get_db)) -> HTMLResponse:
        if not _is_local_debug_request(request):
            raise HTTPException(status_code=403, detail="Debug streams page is local-only")
        streams = list_go2rtc_streams(
            session,
            enable_experimental_transcode=app_settings.enable_experimental_transcode,
            include_unstable_streams=True,
        )
        skipped = list_skipped_cameras(session, include_unstable_streams=True)
        return HTMLResponse(_render_debug_streams_html(streams, skipped, app_settings.go2rtc_url))

    init_db(db_engine)
    return app


app = create_app()


def _get_location(session: Session, location_id: int) -> Location:
    location = session.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


def _get_camera(session: Session, camera_id: int) -> Camera:
    camera = session.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


def _camera_response(camera: Camera, secrets: dict[str, str]) -> CameraResponse:
    return CameraResponse(
        id=camera.id,
        location_id=camera.location_id,
        name=camera.name,
        slug=camera.slug,
        model=camera.model,
        serial_number=camera.serial_number,
        host=camera.host,
        rtsp_username=camera.rtsp_username,
        rtsp_password_secret_ref=camera.rtsp_password_secret_ref,
        onvif_username=camera.onvif_username,
        onvif_password_secret_ref=camera.onvif_password_secret_ref,
        main_stream_path=camera.main_stream_path,
        sub_stream_path=camera.sub_stream_path,
        secondary_main_stream_path=camera.secondary_main_stream_path,
        secondary_sub_stream_path=camera.secondary_sub_stream_path,
        video_status=camera.video_status,
        control_status=camera.control_status,
        probe_status=camera.probe_status,
        reliability_status=camera_reliability_status(camera),
        has_audio=camera.has_audio,
        has_ptz=camera.has_ptz,
        has_onvif=camera.has_onvif,
        has_snapshot=camera.has_snapshot,
        has_two_way_audio_candidate=camera.has_two_way_audio_candidate,
        enabled=camera.enabled,
        notes=camera.notes,
        rtsp_secret_configured=secret_configured(camera.rtsp_password_secret_ref, secrets),
        onvif_secret_configured=secret_configured(camera.onvif_password_secret_ref, secrets),
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


def _is_local_debug_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _render_debug_streams_html(streams: list[Any], skipped_cameras: list[Any], go2rtc_url: str) -> str:
    rows = []
    base_url = go2rtc_url.rstrip("/")
    for stream in streams:
        stream_name = escape(stream.stream_name)
        player_url = f"{base_url}/stream.html?src={quote(stream.stream_name)}"
        hls_url = f"{base_url}/api/stream.m3u8?src={quote(stream.stream_name)}"
        webrtc_url = f"{base_url}/api/webrtc?src={quote(stream.stream_name)}"
        warnings = "<br>".join(escape(warning) for warning in stream.warnings) or "-"
        rows.append(
            "<tr>"
            f"<td>{stream_name}</td>"
            f"<td>{escape(stream.camera_name)}</td>"
            f"<td>{escape(stream.stream_role)}</td>"
            f"<td>{escape(stream.video_codec or '-')}</td>"
            f"<td>{escape(stream.playback_status)}</td>"
            f"<td>{warnings}</td>"
            f"<td><a href=\"{escape(player_url)}\">player</a> "
            f"<a href=\"{escape(hls_url)}\">HLS</a> "
            f"<a href=\"{escape(webrtc_url)}\">WebRTC</a></td>"
            "</tr>"
        )

    skipped_items = "\n".join(
        "<li>"
        f"{escape(item.camera_slug)}: video_status {escape(item.video_status)}, "
        f"control_status {escape(item.control_status)}, {escape(item.reason)}"
        "</li>"
        for item in skipped_cameras
    )
    if not skipped_items:
        skipped_items = "<li>No skipped cameras.</li>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>EZVIZ stream diagnostics</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #172026; background: #f6f7f9; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; }}
    th, td {{ border: 1px solid #d8dde3; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #e9edf2; }}
    a {{ color: #0759a5; margin-right: 10px; }}
    .panel {{ margin-top: 20px; padding: 12px 16px; background: #fff; border: 1px solid #d8dde3; }}
  </style>
</head>
<body>
  <h1>EZVIZ stream diagnostics</h1>
  <table>
    <thead>
      <tr>
        <th>Stream</th>
        <th>Camera</th>
        <th>Role</th>
        <th>Codec</th>
        <th>Status</th>
        <th>Warnings</th>
        <th>Links</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows) if rows else '<tr><td colspan="7">No go2rtc streams generated.</td></tr>'}
    </tbody>
  </table>
  <div class="panel">
    <h2>Skipped cameras</h2>
    <ul>{skipped_items}</ul>
  </div>
</body>
</html>"""


def _live_diagnostics_warnings(cameras: list[Camera], streams: list[Any]) -> list[str]:
    warnings: list[str] = []
    if any((stream.video_codec or "").lower() in {"hevc", "h265", "h.265"} for stream in streams):
        warnings.append("HEVC/H.265: kilka streamów naraz może obciążać przeglądarkę lub GPU nawet na SUB.")
        warnings.append(HEVC_WARNING)
    camera_slugs = {camera.slug.lower() for camera in cameras if camera.enabled}
    if any("c8c_60" in slug for slug in camera_slugs):
        warnings.append("C8C 60: domyślny SUB ma obniżoną stabilność; przetestuj diagnostyczny /ch1/sub przed override.")
    if any("c8c_102" in slug for slug in camera_slugs):
        warnings.append("C8C 102: eksperymentalna kamera, nie włączaj jej do domyślnego video walla.")
    warnings.append("Limit aktywnych podglądów domyślnie wynosi 4; bez limitu może powodować lagi przy HEVC/H.265.")
    warnings.append("Audio w gridzie jest wyłączone; focus startuje wyciszony i audio wymaga ręcznego włączenia.")
    return warnings


def _stream_stability_summary(camera: Camera) -> dict[str, Any]:
    label, tone = _stream_stability_label(camera)
    return {
        "camera_slug": camera.slug,
        "camera_name": camera.name,
        "stability_status": label,
        "tone": tone,
        "reliability_status": camera_reliability_status(camera),
    }


def _stream_stability_label(camera: Camera) -> tuple[str, str]:
    slug = camera.slug.lower()
    reliability = camera_reliability_status(camera)
    if "c8c_102" in slug:
        return "eksperymentalny", "bad"
    if "c8c_60" in slug:
        return ("niestabilny", "bad") if reliability == "unstable" else ("obniżona stabilność", "warn")
    if reliability == "unstable":
        return "niestabilny", "bad"
    if reliability == "degraded":
        return "obniżona stabilność", "warn"
    return "stabilny", "good"
