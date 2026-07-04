from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ezviz_panel.camera_probe.masking import sanitize_text

from .secrets import load_secret_refs


VERIFICATION_FIELD_RE = re.compile(r"(?i)\b(verification(?:\s+code)?\s*[:=]\s*)([^\s,;'\"]+)")


def sanitize_go2rtc_log_text(text: str, *, secrets_env_file: str | Path | None = None) -> str:
    secret_values = _secret_values(secrets_env_file)
    sanitized = sanitize_text(text, secret_values)
    return VERIFICATION_FIELD_RE.sub(lambda match: f"{match.group(1)}***", sanitized)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sanitize go2rtc logs before display or sharing.")
    parser.add_argument(
        "--secrets-env-file",
        default=None,
        help="Optional KEY=value file. Defaults to EZVIZ_SECRETS_ENV_FILE when omitted by scripts.",
    )
    args = parser.parse_args(argv)
    sys.stdout.write(sanitize_go2rtc_log_text(sys.stdin.read(), secrets_env_file=args.secrets_env_file))
    return 0


def _secret_values(secrets_env_file: str | Path | None) -> list[str]:
    if not secrets_env_file:
        return []
    return [value for value in load_secret_refs(str(secrets_env_file)).values() if value]


if __name__ == "__main__":
    raise SystemExit(main())
