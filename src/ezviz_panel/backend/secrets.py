from __future__ import annotations

from pathlib import Path

from ezviz_panel.camera_probe.config import load_env_file


def load_secret_refs(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    return load_env_file(Path(path))


def secret_configured(secret_ref: str | None, secrets: dict[str, str]) -> bool:
    return bool(secret_ref and secret_ref in secrets and secrets[secret_ref])
