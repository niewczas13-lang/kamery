from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import CameraConfig, LocationConfig, ProbeConfig


class ConfigError(ValueError):
    """Raised when the camera configuration cannot be loaded."""


def load_config(path: str | Path, *, secrets_env_file: str | Path | None = None) -> ProbeConfig:
    config_path = Path(path)
    try:
        parsed = parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {config_path}") from exc

    secrets = load_env_file(secrets_env_file) if secrets_env_file else {}

    locations = [
        LocationConfig(
            id=_required(item, "id", "location"),
            name=str(item.get("name", item.get("id", ""))),
            network_cidr=str(item.get("network_cidr", "")),
        )
        for item in _as_list(parsed.get("locations"), "locations")
    ]

    cameras = []
    for item in _as_list(parsed.get("cameras"), "cameras"):
        cameras.append(
            CameraConfig(
                id=_required(item, "id", "camera"),
                name=str(item.get("name", item.get("id", ""))),
                location_id=str(item.get("location_id", "")),
                model=str(item.get("model", "")),
                host=_required(item, "host", "camera"),
                serial_number=str(item.get("serial_number", "")),
                rtsp_username=_resolve_value(item, "rtsp_username", "rtsp_username_env", secrets, "admin"),
                rtsp_password=_resolve_value(item, "rtsp_password", "rtsp_password_env", secrets, ""),
                onvif_username=_resolve_value(
                    item,
                    "onvif_username",
                    "onvif_username_env",
                    secrets,
                    _resolve_value(item, "rtsp_username", "rtsp_username_env", secrets, "admin"),
                ),
                onvif_password=_resolve_value(
                    item,
                    "onvif_password",
                    "onvif_password_env",
                    secrets,
                    _resolve_value(item, "rtsp_password", "rtsp_password_env", secrets, ""),
                ),
                enabled=bool(item.get("enabled", True)),
                notes=str(item.get("notes", "")),
            )
        )

    return ProbeConfig(locations=locations, cameras=cameras)


def load_env_file(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}

    env_path = Path(path)
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ConfigError(f"Secrets env file not found: {env_path}") from exc

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"Secrets env line {line_number}: expected KEY=value")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Secrets env line {line_number}: empty key")
        values[key] = _unquote_env_value(value.strip())
    return values


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small YAML subset used by cameras.example.yml.

    It intentionally supports only top-level lists of scalar mappings. This
    keeps the stage-1 probe dependency-free; the API stage can replace it with
    PyYAML/Pydantic when dependencies are introduced.
    """

    root: dict[str, Any] = {}
    active_key: str | None = None
    active_item: dict[str, Any] | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0:
            if not stripped.endswith(":"):
                raise ConfigError(f"Line {line_number}: expected top-level section ending with ':'")
            active_key = stripped[:-1].strip()
            root[active_key] = []
            active_item = None
            continue

        if active_key is None:
            raise ConfigError(f"Line {line_number}: value outside a section")

        if indent == 2 and stripped.startswith("- "):
            active_item = {}
            root[active_key].append(active_item)
            remainder = stripped[2:].strip()
            if remainder:
                key, value = _split_key_value(remainder, line_number)
                active_item[key] = _parse_scalar(value)
            continue

        if indent >= 4 and active_item is not None:
            key, value = _split_key_value(stripped, line_number)
            active_item[key] = _parse_scalar(value)
            continue

        raise ConfigError(f"Line {line_number}: unsupported YAML structure")

    return root


def _split_key_value(text: str, line_number: int) -> tuple[str, str]:
    if ":" not in text:
        raise ConfigError(f"Line {line_number}: expected 'key: value'")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise ConfigError(f"Line {line_number}: empty key")
    return key, value.strip()


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _resolve_value(
    item: dict[str, Any],
    literal_key: str,
    env_key: str,
    secrets: dict[str, str],
    default: str,
) -> str:
    if item.get(env_key):
        variable_name = str(item[env_key])
        if variable_name not in secrets:
            identifier = item.get("id", "<missing id>")
            raise ConfigError(f"camera {identifier!r} references missing secret {variable_name!r}")
        return secrets[variable_name]
    return str(item.get(literal_key, default))


def _unquote_env_value(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def _as_list(value: Any, key: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"Section {key} must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise ConfigError(f"Section {key} must contain mapping items")
    return value


def _required(item: dict[str, Any], key: str, item_type: str) -> str:
    value = item.get(key)
    if value is None or str(value).strip() == "":
        identifier = item.get("id", "<missing id>")
        raise ConfigError(f"{item_type} {identifier!r} is missing required field {key!r}")
    return str(value)
