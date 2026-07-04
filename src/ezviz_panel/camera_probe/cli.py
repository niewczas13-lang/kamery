from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import ConfigError, load_config
from .masking import sanitize_for_sharing, sanitize_text
from .probe import DEFAULT_RTSP_PATHS, format_results_table, probe_config, to_json
from .tooling import format_tool_report, verify_tools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe local EZVIZ/RTSP/ONVIF cameras safely.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run RTSP/ONVIF probe for one or more cameras.")
    _add_run_args(run_parser)

    tools_parser = subparsers.add_parser("verify-tools", help="Check ffmpeg and ffprobe availability.")
    _add_tool_args(tools_parser)

    sanitize_parser = subparsers.add_parser("sanitize-result", help="Sanitize a probe JSON file for sharing.")
    sanitize_parser.add_argument("input", help="Private probe JSON file to sanitize.")
    sanitize_parser.add_argument("--output", "-o", help="Optional sanitized JSON output file.")

    return parser


def main(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        raw_args = ["run"]
    elif raw_args[0].startswith("-") and raw_args[0] not in {"-h", "--help"}:
        raw_args.insert(0, "run")

    parser = build_parser()
    args = parser.parse_args(raw_args)

    if args.command == "verify-tools":
        return _verify_tools_command(args)
    if args.command == "sanitize-result":
        return _sanitize_result_command(args)
    return _run_command(args)


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default="cameras.local.yml",
        help="Path to local camera config. Default: cameras.local.yml",
    )
    parser.add_argument("--camera-id", help="Probe only one camera id from the config.")
    parser.add_argument(
        "--secrets-env-file",
        default=os.environ.get("CAMERA_PROBE_SECRETS_ENV_FILE"),
        help="Optional KEY=value file with RTSP/ONVIF secrets referenced by *_env config fields.",
    )
    parser.add_argument(
        "--format",
        choices=("all", "table", "json"),
        default="all",
        help="Terminal output format. Default: all",
    )
    parser.add_argument("--output", "--json-out", dest="output", help="Optional file path for JSON results.")
    parser.add_argument(
        "--sanitize-for-sharing",
        action="store_true",
        help="Mask host/IP, private identifiers, and snapshot paths in the printed/saved JSON.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="Timeout per network/probe operation in seconds.")
    _add_tool_args(parser)
    parser.add_argument(
        "--rtsp-transport",
        choices=("tcp", "udp"),
        default="tcp",
        help="RTSP transport passed to ffprobe/ffmpeg. Default: tcp",
    )
    parser.add_argument("--snapshot-dir", default="snapshots/probe", help="Directory for test snapshots.")
    parser.add_argument("--include-disabled", action="store_true", help="Probe cameras marked enabled: false.")
    parser.add_argument(
        "--rtsp-path",
        action="append",
        dest="rtsp_paths",
        help="RTSP path to test. May be repeated. Defaults to common EZVIZ/Hikvision paths.",
    )
    parser.add_argument(
        "--fail-on-camera-error",
        action="store_true",
        help="Return exit code 1 when any camera status is partial, failed, or unknown.",
    )


def _add_tool_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--ffprobe-bin",
        default=os.environ.get("FFPROBE_BIN", "ffprobe"),
        help="ffprobe binary/path. Can also be set with FFPROBE_BIN.",
    )
    parser.add_argument(
        "--ffmpeg-bin",
        default=os.environ.get("FFMPEG_BIN", "ffmpeg"),
        help="ffmpeg binary/path. Can also be set with FFMPEG_BIN.",
    )


def _verify_tools_command(args: argparse.Namespace) -> int:
    payload = verify_tools(ffmpeg_bin=args.ffmpeg_bin, ffprobe_bin=args.ffprobe_bin)
    print(format_tool_report(payload))
    return 0 if payload["ok"] else 1


def _run_command(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config, secrets_env_file=args.secrets_env_file)
    except ConfigError as exc:
        print(sanitize_text(str(exc)), file=sys.stderr)
        return 2

    if args.camera_id and not any(camera.id == args.camera_id for camera in config.cameras):
        print(f"Camera id not found in config: {args.camera_id}", file=sys.stderr)
        return 3

    payload = probe_config(
        config,
        rtsp_paths=tuple(args.rtsp_paths or DEFAULT_RTSP_PATHS),
        camera_id=args.camera_id,
        timeout_seconds=args.timeout,
        ffprobe_bin=args.ffprobe_bin,
        ffmpeg_bin=args.ffmpeg_bin,
        rtsp_transport=args.rtsp_transport,
        snapshot_dir=args.snapshot_dir,
        include_disabled=args.include_disabled,
    )

    output_payload = sanitize_for_sharing(payload) if args.sanitize_for_sharing else payload
    output_json = to_json(output_payload)

    if args.format in {"all", "table"}:
        print(format_results_table(output_payload))
    if args.format in {"all", "json"}:
        if args.format == "all":
            print()
        print(output_json)

    if args.output:
        _write_text(args.output, output_json + "\n")

    if args.fail_on_camera_error:
        statuses = [item.get("status") for item in payload.get("results", []) if isinstance(item, dict)]
        return 1 if any(status != "ok" for status in statuses) else 0
    return 0


def _sanitize_result_command(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(sanitize_text(f"Cannot read probe result: {exc}"), file=sys.stderr)
        return 2

    sanitized = to_json(sanitize_for_sharing(payload))
    if args.output:
        _write_text(args.output, sanitized + "\n")
    else:
        print(sanitized)
    return 0


def _write_text(path: str, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
