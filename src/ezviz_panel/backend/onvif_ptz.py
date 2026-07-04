from __future__ import annotations

from dataclasses import dataclass
from time import sleep as default_sleep
from typing import Any, Callable, Protocol

from ezviz_panel.camera_probe.masking import sanitize_text

from .models import Camera


SUPPORTED_PTZ_COMMANDS = {"up", "down", "left", "right", "zoom_in", "zoom_out", "stop"}
MOVEMENT_COMMANDS = SUPPORTED_PTZ_COMMANDS - {"stop"}
DEFAULT_DURATION_MS = 300
MAX_DURATION_MS = 1500
DEFAULT_SPEED = 0.3
MIN_SPEED = 0.05
MAX_SPEED = 1.0
DEFAULT_ONVIF_PORT = 80
DEFAULT_TIMEOUT_SECONDS = 5.0


class PtzAdapter(Protocol):
    def connect(self, camera: Camera, password: str, timeout: float) -> Any:
        ...

    def get_profiles(self, connection: Any) -> list[Any]:
        ...

    def get_ptz_capabilities(self, connection: Any) -> Any:
        ...

    def continuous_move(self, connection: Any, profile: Any, command: str, speed: float) -> None:
        ...

    def stop(self, connection: Any, profile: Any) -> None:
        ...


class PtzError(RuntimeError):
    status_code = 502
    stopped = False

    def __init__(self, message: str, *, stopped: bool = False, warning: str | None = None) -> None:
        super().__init__(message)
        self.stopped = stopped
        self.warning = warning


class PtzUnsupportedError(PtzError):
    status_code = 409


class PtzSecretMissingError(PtzError):
    status_code = 409


class PtzInvalidCommandError(PtzError):
    status_code = 400


class PtzConnectionError(PtzError):
    status_code = 502


class PtzCommandError(PtzError):
    status_code = 502


@dataclass(frozen=True)
class PtzCommandResult:
    camera_id: int
    command: str
    status: str
    duration_ms: int
    stopped: bool
    warning: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "camera_id": self.camera_id,
            "command": self.command,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "stopped": self.stopped,
        }
        if self.warning:
            payload["warning"] = self.warning
        return payload


def execute_ptz_command(
    camera: Camera,
    command: str,
    *,
    secrets: dict[str, str],
    adapter: PtzAdapter | None = None,
    duration_ms: int = DEFAULT_DURATION_MS,
    speed: float = DEFAULT_SPEED,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = default_sleep,
) -> PtzCommandResult:
    _validate_command(command)
    _validate_camera(camera)
    password = _onvif_password(camera, secrets)
    safe_values = [password]
    safe_duration = _clamp_duration(duration_ms)
    safe_speed = _clamp_speed(speed)
    ptz_adapter = adapter or OnvifZeepPtzAdapter()

    connection = _connect(ptz_adapter, camera, password, timeout, safe_values)
    profile = _first_ptz_profile(_profiles(ptz_adapter, connection, safe_values))

    if command == "stop":
        _stop(ptz_adapter, connection, profile, safe_values)
        return PtzCommandResult(
            camera_id=camera.id,
            command=command,
            status="stopped",
            duration_ms=0,
            stopped=True,
        )

    move_error: Exception | None = None
    try:
        ptz_adapter.continuous_move(connection, profile, command, safe_speed)
        sleep(safe_duration / 1000)
    except Exception as exc:  # noqa: BLE001 - adapter errors are normalized below.
        move_error = exc

    stopped, stop_warning = _try_stop(ptz_adapter, connection, profile, safe_values)
    if move_error is not None:
        message = sanitize_text(f"ONVIF PTZ command failed: {move_error}", safe_values)
        raise PtzCommandError(message, stopped=stopped, warning=stop_warning) from move_error

    return PtzCommandResult(
        camera_id=camera.id,
        command=command,
        status="moved",
        duration_ms=safe_duration,
        stopped=stopped,
        warning=stop_warning,
    )


def probe_ptz_camera(
    camera: Camera,
    *,
    secrets: dict[str, str],
    adapter: PtzAdapter | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    _validate_camera(camera)
    password = _onvif_password(camera, secrets)
    safe_values = [password]
    ptz_adapter = adapter or OnvifZeepPtzAdapter()
    connection = _connect(ptz_adapter, camera, password, timeout, safe_values)
    profiles = _profiles(ptz_adapter, connection, safe_values)
    capabilities = _capabilities(ptz_adapter, connection, safe_values)
    return {
        "camera_id": camera.id,
        "camera_slug": camera.slug,
        "connected": True,
        "profile_count": len(profiles),
        "ptz_profile_found": _first_ptz_profile_or_none(profiles) is not None,
        "capabilities_found": capabilities is not None,
    }


class OnvifZeepPtzAdapter:
    def __init__(self, *, port: int = DEFAULT_ONVIF_PORT) -> None:
        self.port = port

    def connect(self, camera: Camera, password: str, timeout: float) -> Any:
        try:
            from onvif import ONVIFCamera  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("ONVIF dependency is not installed. Install onvif-zeep to use real PTZ.") from exc

        kwargs: dict[str, Any] = {"no_cache": True}
        try:
            from zeep.transports import Transport  # type: ignore[import-not-found]

            kwargs["transport"] = Transport(timeout=timeout, operation_timeout=timeout)
        except ImportError:
            pass

        try:
            device = ONVIFCamera(camera.host, self.port, camera.onvif_username, password, **kwargs)
        except TypeError:
            device = ONVIFCamera(camera.host, self.port, camera.onvif_username, password)
        media = device.create_media_service()
        ptz = device.create_ptz_service()
        return {"device": device, "media": media, "ptz": ptz}

    def get_profiles(self, connection: Any) -> list[Any]:
        profiles = connection["media"].GetProfiles()
        return list(profiles or [])

    def get_ptz_capabilities(self, connection: Any) -> Any:
        try:
            return connection["ptz"].GetServiceCapabilities()
        except Exception:
            return None

    def continuous_move(self, connection: Any, profile: Any, command: str, speed: float) -> None:
        ptz = connection["ptz"]
        request = ptz.create_type("ContinuousMove")
        request.ProfileToken = _profile_token(profile)
        request.Velocity = _velocity_for_command(command, speed)
        ptz.ContinuousMove(request)

    def stop(self, connection: Any, profile: Any) -> None:
        ptz = connection["ptz"]
        request = ptz.create_type("Stop")
        request.ProfileToken = _profile_token(profile)
        request.PanTilt = True
        request.Zoom = True
        ptz.Stop(request)


def _validate_command(command: str) -> None:
    if command not in SUPPORTED_PTZ_COMMANDS:
        raise PtzInvalidCommandError("Unsupported PTZ command")


def _validate_camera(camera: Camera) -> None:
    if not camera.has_ptz:
        raise PtzUnsupportedError("PTZ not supported or not detected")


def _onvif_password(camera: Camera, secrets: dict[str, str]) -> str:
    secret_ref = camera.onvif_password_secret_ref
    if not secret_ref or not secrets.get(secret_ref):
        raise PtzSecretMissingError("PTZ secret is not configured")
    return secrets[secret_ref]


def _connect(adapter: PtzAdapter, camera: Camera, password: str, timeout: float, safe_values: list[str]) -> Any:
    try:
        return adapter.connect(camera, password, timeout)
    except Exception as exc:  # noqa: BLE001 - adapter errors are normalized here.
        raise PtzConnectionError(sanitize_text(f"ONVIF connection failed: {exc}", safe_values)) from exc


def _profiles(adapter: PtzAdapter, connection: Any, safe_values: list[str]) -> list[Any]:
    try:
        profiles = adapter.get_profiles(connection)
    except Exception as exc:  # noqa: BLE001 - adapter errors are normalized here.
        raise PtzConnectionError(sanitize_text(f"ONVIF profiles unavailable: {exc}", safe_values)) from exc
    if not profiles:
        raise PtzConnectionError("ONVIF profiles unavailable")
    return profiles


def _capabilities(adapter: PtzAdapter, connection: Any, safe_values: list[str]) -> Any:
    try:
        return adapter.get_ptz_capabilities(connection)
    except Exception as exc:  # noqa: BLE001 - probe output is informational.
        return sanitize_text(str(exc), safe_values)


def _first_ptz_profile(profiles: list[Any]) -> Any:
    profile = _first_ptz_profile_or_none(profiles)
    if profile is None:
        raise PtzUnsupportedError("PTZ profile not available")
    return profile


def _first_ptz_profile_or_none(profiles: list[Any]) -> Any | None:
    for profile in profiles:
        if _profile_has_ptz(profile):
            return profile
    return None


def _profile_has_ptz(profile: Any) -> bool:
    if isinstance(profile, dict):
        return bool(profile.get("PTZConfiguration") or profile.get("ptz_configuration"))
    return getattr(profile, "PTZConfiguration", None) is not None


def _profile_token(profile: Any) -> str:
    if isinstance(profile, dict):
        return str(profile.get("token") or profile.get("Token") or "")
    return str(getattr(profile, "token", None) or getattr(profile, "Token", ""))


def _velocity_for_command(command: str, speed: float) -> dict[str, dict[str, float]]:
    if command == "up":
        return {"PanTilt": {"x": 0.0, "y": speed}}
    if command == "down":
        return {"PanTilt": {"x": 0.0, "y": -speed}}
    if command == "left":
        return {"PanTilt": {"x": -speed, "y": 0.0}}
    if command == "right":
        return {"PanTilt": {"x": speed, "y": 0.0}}
    if command == "zoom_in":
        return {"Zoom": {"x": speed}}
    if command == "zoom_out":
        return {"Zoom": {"x": -speed}}
    raise PtzInvalidCommandError("Unsupported PTZ command")


def _stop(adapter: PtzAdapter, connection: Any, profile: Any, safe_values: list[str]) -> None:
    try:
        adapter.stop(connection, profile)
    except Exception as exc:  # noqa: BLE001 - adapter errors are normalized here.
        raise PtzCommandError(sanitize_text(f"ONVIF PTZ stop failed: {exc}", safe_values), stopped=False) from exc


def _try_stop(adapter: PtzAdapter, connection: Any, profile: Any, safe_values: list[str]) -> tuple[bool, str | None]:
    try:
        adapter.stop(connection, profile)
        return True, None
    except Exception as exc:  # noqa: BLE001 - stop failure is reported as a warning for completed moves.
        return False, sanitize_text(f"ONVIF PTZ stop failed: {exc}", safe_values)


def _clamp_duration(duration_ms: int) -> int:
    return max(1, min(int(duration_ms), MAX_DURATION_MS))


def _clamp_speed(speed: float) -> float:
    return max(MIN_SPEED, min(float(speed), MAX_SPEED))
