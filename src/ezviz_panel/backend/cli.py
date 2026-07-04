from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from .database import SessionLocal, init_db
from .frigate import (
    fetch_frigate_events,
    fetch_frigate_health,
    render_frigate_preview,
    render_frigate_runtime_config,
    sync_frigate_events,
)
from .go2rtc import (
    Go2RtcConfigError,
    apply_stream_path_override,
    fetch_go2rtc_health,
    list_go2rtc_streams,
    render_go2rtc_preview,
    render_go2rtc_runtime_config,
)
from .lukow_seed import seed_lukow_cameras
from .models import Admin, CameraProbeResult
from .onvif_ptz import PtzError, execute_ptz_command, probe_ptz_camera
from .probe_importer import ProbeImportError, apply_probe_result, import_probe_files
from .security import hash_password
from .secrets import load_secret_refs
from .settings import ensure_runtime_dirs, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EZVIZ Panel backend utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create local database tables.")
    subparsers.add_parser("seed-lukow-cameras", help="Create or update the local Lukow camera inventory.")

    admin_parser = subparsers.add_parser("create-admin", help="Create or update the single admin account.")
    admin_parser.add_argument("--username", default=os.environ.get("ADMIN_USERNAME", "admin"))
    admin_parser.add_argument("--password", help="Development-only password value. Prefer --password-env or prompt.")
    admin_parser.add_argument("--password-env", default="ADMIN_PASSWORD")

    import_parser = subparsers.add_parser("import-probe", help="Import private camera-probe JSON into the database.")
    import_parser.add_argument(
        "--file",
        required=True,
        action="append",
        help="Path to private probe JSON. May be repeated.",
    )
    import_parser.add_argument("--apply", action="store_true", help="Apply imported probe results to matching cameras.")
    import_parser.add_argument("--create-missing", action="store_true", help="Create missing locations and cameras from probe metadata.")
    import_parser.add_argument("--prefer-best", action="store_true", help="When multiple probe results exist per camera, apply the best scored result.")

    preview_parser = subparsers.add_parser("go2rtc-preview", help="Render go2rtc YAML preview without real secrets.")
    preview_parser.add_argument("--output", help="Optional file path for preview YAML.")
    preview_parser.add_argument("--include-diagnostic-streams", action="store_true", help="Include local diagnostic aliases such as C8C 60 /ch1/sub.")

    render_parser = subparsers.add_parser("go2rtc-render-runtime", help="Write private runtime go2rtc config.")
    render_parser.add_argument("--output", help="Override runtime config output path.")
    render_parser.add_argument("--include-unstable-streams", action="store_true", help="Include experimental streams from unstable cameras.")
    render_parser.add_argument("--include-diagnostic-streams", action="store_true", help="Include local diagnostic aliases such as C8C 60 /ch1/sub.")

    subparsers.add_parser("go2rtc-health", help="Check the configured go2rtc HTTP API.")

    subparsers.add_parser("list-streams", help="List generated logical go2rtc streams.")

    override_parser = subparsers.add_parser("stream-override", help="Set a preferred camera stream path without storing credentials.")
    override_parser.add_argument("--camera-slug", required=True)
    override_parser.add_argument("--role", required=True, choices=["main", "sub", "lens2_main", "lens2_sub"])
    override_parser.add_argument("--path", required=True, help="Camera RTSP path, for example /ch1/sub. Do not pass a full RTSP URL.")

    frigate_preview_parser = subparsers.add_parser("frigate-preview", help="Render Frigate YAML preview without camera secrets.")
    frigate_preview_parser.add_argument("--output", help="Optional file path for preview YAML.")

    frigate_render_parser = subparsers.add_parser("frigate-render-runtime", help="Write local Frigate runtime config.")
    frigate_render_parser.add_argument("--output", help="Override runtime config output path.")

    subparsers.add_parser("frigate-health", help="Check the configured Frigate HTTP API.")
    subparsers.add_parser("frigate-events", help="Fetch Frigate events through the configured API.")
    subparsers.add_parser("sync-frigate-events", help="Import current Frigate events into the local database.")

    ptz_probe_parser = subparsers.add_parser("ptz-probe", help="Check ONVIF PTZ connectivity and profiles.")
    ptz_probe_parser.add_argument("--camera-slug", required=True)

    ptz_test_parser = subparsers.add_parser("ptz-test", help="Run one short ONVIF PTZ command with automatic stop.")
    ptz_test_parser.add_argument("--camera-slug", required=True)
    ptz_test_parser.add_argument(
        "--command",
        dest="ptz_command",
        required=True,
        choices=["up", "down", "left", "right", "zoom_in", "zoom_out", "stop"],
    )
    ptz_test_parser.add_argument("--duration-ms", type=int, default=300)
    ptz_test_parser.add_argument("--speed", type=float, default=0.3)

    server_parser = subparsers.add_parser("runserver", help="Run local FastAPI app with uvicorn.")
    server_parser.add_argument("--host", default="127.0.0.1")
    server_parser.add_argument("--port", type=int, default=8000)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        ensure_runtime_dirs()
        init_db()
        print("Database initialized")
        return 0
    if args.command == "seed-lukow-cameras":
        return _seed_lukow_cameras(args)
    if args.command == "create-admin":
        return _create_admin(args)
    if args.command == "import-probe":
        return _import_probe(args)
    if args.command == "go2rtc-preview":
        return _go2rtc_preview(args)
    if args.command == "go2rtc-render-runtime":
        return _go2rtc_render_runtime(args)
    if args.command == "go2rtc-health":
        return _go2rtc_health(args)
    if args.command == "list-streams":
        return _list_streams(args)
    if args.command == "stream-override":
        return _stream_override(args)
    if args.command == "frigate-preview":
        return _frigate_preview(args)
    if args.command == "frigate-render-runtime":
        return _frigate_render_runtime(args)
    if args.command == "frigate-health":
        return _frigate_health(args)
    if args.command == "frigate-events":
        return _frigate_events(args)
    if args.command == "sync-frigate-events":
        return _sync_frigate_events(args)
    if args.command == "ptz-probe":
        return _ptz_probe(args)
    if args.command == "ptz-test":
        return _ptz_test(args)
    if args.command == "runserver":
        return _runserver(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


def _seed_lukow_cameras(_: argparse.Namespace) -> int:
    init_db()
    with SessionLocal() as session:
        result = seed_lukow_cameras(session)
    print(f"Seeded Lukow cameras: total={result['total']} created={len(result['created'])} updated={len(result['updated'])}")
    if result["created"]:
        print("Created:")
        for slug in result["created"]:
            print(f"- {slug}")
    if result["updated"]:
        print("Updated:")
        for slug in result["updated"]:
            print(f"- {slug}")
    return 0


def _create_admin(args: argparse.Namespace) -> int:
    init_db()
    password = args.password or os.environ.get(args.password_env)
    if not password:
        password = getpass.getpass("Admin password: ")
    if not password:
        print("Admin password cannot be empty", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        admin = session.query(Admin).filter(Admin.username == args.username).first()
        if admin is None:
            admin = Admin(username=args.username, password_hash=hash_password(password))
            session.add(admin)
            action = "created"
        else:
            admin.password_hash = hash_password(password)
            action = "updated"
        session.commit()
    print(f"Admin {action}: {args.username}")
    return 0


def _import_probe(args: argparse.Namespace) -> int:
    init_db()
    payloads = []
    for file_path in args.file:
        try:
            payloads.append(json.loads(Path(file_path).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Cannot read probe result: {exc}", file=sys.stderr)
            return 2

    try:
        with SessionLocal() as session:
            records = import_probe_files(
                session,
                payloads,
                create_missing=args.create_missing,
                apply=args.apply,
                prefer_best=args.prefer_best,
            )
            print(f"Imported probe results: {len(records)}")
    except ProbeImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _apply_records(session: Session, records: list[CameraProbeResult]) -> None:
    for record in records:
        session.refresh(record)
        apply_probe_result(session, record.camera, record)


def _go2rtc_preview(args: argparse.Namespace) -> int:
    init_db()
    settings = load_settings()
    with SessionLocal() as session:
        yaml_text, warnings = render_go2rtc_preview(
            session,
            enable_experimental_transcode=settings.enable_experimental_transcode,
            include_diagnostic_streams=args.include_diagnostic_streams,
        )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_text, encoding="utf-8")
    else:
        print(yaml_text, end="")
    if warnings:
        print("Warnings:", file=sys.stderr)
        for warning in warnings:
            print(f"- {warning}", file=sys.stderr)
    return 0


def _go2rtc_render_runtime(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    init_db()
    settings = load_settings()
    output = args.output or settings.go2rtc_config_path
    try:
        with SessionLocal() as session:
            result = render_go2rtc_runtime_config(
                session,
                secrets_env_file=settings.secrets_env_file,
                output_path=output,
                enable_experimental_transcode=settings.enable_experimental_transcode,
                include_unstable_streams=args.include_unstable_streams,
                include_diagnostic_streams=args.include_diagnostic_streams,
            )
    except Go2RtcConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Generated go2rtc runtime config: {result.output_path}")
    print(f"Streams: {result.stream_count}")
    if result.skipped_cameras:
        print("Skipped cameras:")
        for camera_slug in result.skipped_cameras:
            print(f"- {camera_slug}")
    if result.unstable_cameras:
        print("Unstable cameras:")
        for camera_slug in result.unstable_cameras:
            print(f"- {camera_slug}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


def _go2rtc_health(_: argparse.Namespace) -> int:
    settings = load_settings()
    payload = fetch_go2rtc_health(settings.go2rtc_url)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["reachable"] else 1


def _list_streams(_: argparse.Namespace) -> int:
    init_db()
    settings = load_settings()
    with SessionLocal() as session:
        streams = list_go2rtc_streams(
            session,
            enable_experimental_transcode=settings.enable_experimental_transcode,
        )
    for stream in streams:
        warnings = "; ".join(stream.warnings)
        suffix = f" [{warnings}]" if warnings else ""
        print(f"{stream.stream_name}\t{stream.camera_name}\t{stream.stream_role}\t{stream.video_codec or '-'}{suffix}")
    if not streams:
        print("No go2rtc streams generated")
    return 0


def _stream_override(args: argparse.Namespace) -> int:
    init_db()
    try:
        with SessionLocal() as session:
            camera = apply_stream_path_override(session, args.camera_slug, args.role, args.path)
    except Go2RtcConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"Updated {camera.slug} {args.role} path: {getattr(camera, {'main': 'main_stream_path', 'sub': 'sub_stream_path', 'lens2_main': 'secondary_main_stream_path', 'lens2_sub': 'secondary_sub_stream_path'}[args.role])}")
    return 0


def _frigate_preview(args: argparse.Namespace) -> int:
    init_db()
    with SessionLocal() as session:
        result = render_frigate_preview(session)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.yaml, encoding="utf-8")
    else:
        print(result.yaml, end="")
    if result.warnings:
        print("Warnings:", file=sys.stderr)
        for warning in result.warnings:
            print(f"- {warning}", file=sys.stderr)
    return 0


def _frigate_render_runtime(args: argparse.Namespace) -> int:
    ensure_runtime_dirs()
    init_db()
    settings = load_settings()
    output = args.output or settings.frigate_config_path
    with SessionLocal() as session:
        result = render_frigate_runtime_config(session, output_path=output)
    print(f"Generated Frigate runtime config: {result.output_path}")
    print(f"Cameras: {len(result.cameras)}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


def _frigate_health(_: argparse.Namespace) -> int:
    settings = load_settings()
    payload = fetch_frigate_health(settings.frigate_url)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["reachable"] else 1


def _frigate_events(_: argparse.Namespace) -> int:
    settings = load_settings()
    payload = fetch_frigate_events(settings.frigate_url)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["reachable"] else 1


def _sync_frigate_events(_: argparse.Namespace) -> int:
    init_db()
    settings = load_settings()
    payload = fetch_frigate_events(settings.frigate_url)
    if not payload["reachable"]:
        print(payload["error"] or "Frigate API not reachable", file=sys.stderr)
        return 1
    events = payload["events"] if isinstance(payload["events"], list) else []
    with SessionLocal() as session:
        imported = sync_frigate_events(session, events)
    print(f"Imported Frigate events: {imported}")
    return 0


def _ptz_probe(args: argparse.Namespace) -> int:
    init_db()
    settings = load_settings()
    secrets = load_secret_refs(settings.secrets_env_file)
    with SessionLocal() as session:
        camera = _get_camera_by_slug(session, args.camera_slug)
        if camera is None:
            print("Camera not found", file=sys.stderr)
            return 2
        try:
            payload = probe_ptz_camera(camera, secrets=secrets)
        except PtzError as exc:
            print(str(exc), file=sys.stderr)
            return 2 if exc.status_code in {400, 409} else 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _ptz_test(args: argparse.Namespace) -> int:
    init_db()
    settings = load_settings()
    secrets = load_secret_refs(settings.secrets_env_file)
    with SessionLocal() as session:
        camera = _get_camera_by_slug(session, args.camera_slug)
        if camera is None:
            print("Camera not found", file=sys.stderr)
            return 2
        try:
            result = execute_ptz_command(
                camera,
                args.ptz_command,
                secrets=secrets,
                duration_ms=args.duration_ms,
                speed=args.speed,
            )
        except PtzError as exc:
            print(str(exc), file=sys.stderr)
            return 2 if exc.status_code in {400, 409} else 1
    print(json.dumps(result.to_public_dict(), indent=2, ensure_ascii=False))
    return 0


def _get_camera_by_slug(session: Session, camera_slug: str):
    from .models import Camera

    return session.query(Camera).filter(Camera.slug == camera_slug).first()


def _runserver(args: argparse.Namespace) -> int:
    import uvicorn

    init_db()
    uvicorn.run("ezviz_panel.backend.app:app", host=args.host, port=args.port, reload=False)
    return 0
