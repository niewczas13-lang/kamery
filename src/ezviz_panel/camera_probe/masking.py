from __future__ import annotations

import re
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

MASK = "***"
URL_RE = re.compile(r"\b(rtsp|http|https)://[^\s'\"]+", re.IGNORECASE)
IPV4_RE = re.compile(r"\b((?:\d{1,3}\.){3})(\d{1,3})\b")
SERIAL_RE = re.compile(r"\b([A-Z]{2,3}[A-Z0-9]*\d[A-Z0-9]{5,})\b")
SECRET_KEY_PARTS = ("password", "secret", "token", "verification", "credential")
PRIVATE_ID_KEYS = {
    "camera_id",
    "selected_camera_id",
    "location_id",
    "serial_number",
    "id",
    "name",
    "host",
    "snapshot_path",
    "clip_path",
    "thumbnail_path",
}


def mask_value(text: str, secret_values: list[str] | tuple[str, ...]) -> str:
    masked = text
    for secret in secret_values:
        if secret:
            masked = masked.replace(secret, MASK)
    return masked


def mask_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return URL_RE.sub(_mask_url_match, url)

    if not parts.scheme or not parts.netloc:
        return URL_RE.sub(_mask_url_match, url)

    hostname = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    if parts.username is not None:
        user = parts.username
        auth = f"{user}:{MASK}@"
    else:
        auth = ""

    netloc = f"{auth}{hostname}{port}"
    query = MASK if _is_secret_query(parts.query) else parts.query
    return urlunsplit(SplitResult(parts.scheme, netloc, parts.path, query, parts.fragment))


def sanitize_text(text: str, secret_values: list[str] | tuple[str, ...] = ()) -> str:
    without_urls = URL_RE.sub(_mask_url_match, text)
    return mask_value(without_urls, secret_values)


def sanitize_sensitive_object(data: Any, secret_values: list[str] | tuple[str, ...] = ()) -> Any:
    """Recursively mask credentials without hiding operational camera details."""

    if isinstance(data, dict):
        return {
            key: MASK if _is_secret_key(str(key)) else sanitize_sensitive_object(value, secret_values)
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [sanitize_sensitive_object(item, secret_values) for item in data]
    if isinstance(data, tuple):
        return tuple(sanitize_sensitive_object(item, secret_values) for item in data)
    if isinstance(data, str):
        return sanitize_text(data, secret_values)
    return data


def sanitize_for_sharing(data: Any, secret_values: list[str] | tuple[str, ...] = ()) -> Any:
    """Create a result that can be pasted into a support/chat thread."""

    sensitive_clean = sanitize_sensitive_object(data, secret_values)
    return _sanitize_share_value(sensitive_clean)


def mask_ip(value: str) -> str:
    return IPV4_RE.sub(lambda match: f"{match.group(1)}xxx", value)


def mask_private_identifier(value: str) -> str:
    if not value:
        return value
    if len(value) <= 4:
        return MASK
    if len(value) <= 6:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:3]}****{value[-2:]}"


def _mask_url_match(match: re.Match[str]) -> str:
    return mask_url(match.group(0))


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SECRET_KEY_PARTS)


def _is_secret_query(query: str) -> bool:
    lowered = query.lower()
    return any(part in lowered for part in SECRET_KEY_PARTS)


def _sanitize_share_value(data: Any, key: str | None = None) -> Any:
    if isinstance(data, dict):
        return {item_key: _sanitize_share_value(value, str(item_key)) for item_key, value in data.items()}
    if isinstance(data, list):
        return [_sanitize_share_value(item, key) for item in data]
    if isinstance(data, tuple):
        return tuple(_sanitize_share_value(item, key) for item in data)
    if isinstance(data, str):
        if key and key.lower() in PRIVATE_ID_KEYS:
            return _sanitize_private_field(key.lower(), data)
        return _mask_serials(mask_ip(data))
    return data


def _sanitize_private_field(key: str, value: str) -> str:
    if key == "snapshot_path":
        return "<snapshot_path>" if value else value
    if key in {"clip_path", "thumbnail_path"}:
        return f"<{key}>" if value else value
    if key == "serial_number":
        return mask_private_identifier(value)
    if key == "name":
        return "<name>" if value else value
    if key == "host":
        masked = mask_ip(value)
        return masked if masked != value else "<host>"
    return mask_private_identifier(mask_ip(value))


def _mask_serials(value: str) -> str:
    return SERIAL_RE.sub(lambda match: mask_private_identifier(match.group(1)), value)
