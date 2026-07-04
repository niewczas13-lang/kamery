from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///runtime/db/ezviz-panel.db"
    secret_key: str = "change-this-local-dev-secret"
    secrets_env_file: str | None = None
    access_token_expire_minutes: int = 720
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    go2rtc_url: str = "http://127.0.0.1:1984"
    go2rtc_config_path: str = "runtime/config/go2rtc/go2rtc.yaml"
    frigate_url: str = "http://127.0.0.1:5000"
    frigate_config_path: str = "runtime/config/frigate/config.yml"
    enable_experimental_transcode: bool = False
    snapshot_dir: str = "runtime/snapshots"
    ffmpeg_bin: str = "ffmpeg"


def load_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", "sqlite:///runtime/db/ezviz-panel.db"),
        secret_key=os.environ.get("EZVIZ_BACKEND_SECRET_KEY", "change-this-local-dev-secret"),
        secrets_env_file=os.environ.get("EZVIZ_SECRETS_ENV_FILE") or None,
        access_token_expire_minutes=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "720")),
        cors_origins=tuple(
            origin.strip()
            for origin in os.environ.get(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ),
        go2rtc_url=os.environ.get("GO2RTC_API_URL") or os.environ.get("GO2RTC_URL", "http://127.0.0.1:1984"),
        go2rtc_config_path=os.environ.get("GO2RTC_CONFIG_PATH", "runtime/config/go2rtc/go2rtc.yaml"),
        frigate_url=os.environ.get("FRIGATE_API_URL") or os.environ.get("FRIGATE_URL", "http://127.0.0.1:5000"),
        frigate_config_path=os.environ.get("FRIGATE_CONFIG_PATH", "runtime/config/frigate/config.yml"),
        enable_experimental_transcode=_env_bool(os.environ.get("ENABLE_EXPERIMENTAL_TRANSCODE"), default=False),
        snapshot_dir=os.environ.get("EZVIZ_SNAPSHOT_DIR", "runtime/snapshots"),
        ffmpeg_bin=os.environ.get("FFMPEG_BIN", "ffmpeg"),
    )


def ensure_runtime_dirs() -> None:
    for path in (
        Path("runtime/db"),
        Path("runtime/config/go2rtc"),
        Path("runtime/config/frigate"),
        Path("runtime/media/frigate"),
        Path("runtime/cache/frigate"),
        Path("runtime/logs"),
        Path("runtime/logs/go2rtc"),
        Path("runtime/diagnostics"),
        Path("runtime/tmp"),
        Path("runtime/recordings"),
        Path("runtime/snapshots"),
    ):
        path.mkdir(parents=True, exist_ok=True)


def _env_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
