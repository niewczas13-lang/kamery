from pathlib import Path
import json
import sys
import tempfile
import unittest

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend.database import Base
from ezviz_panel.backend.frigate import (
    fetch_frigate_events,
    fetch_frigate_health,
    get_or_create_recording_policy,
    render_frigate_preview,
    render_frigate_runtime_config,
    sync_frigate_events,
)
from ezviz_panel.backend.models import Camera, Event, Location, RecordingPolicy


class FrigateConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            location = Location(name="Lukow", slug="lukow")
            session.add(location)
            session.flush()
            _camera(
                session,
                location.id,
                "lukow_h9c_98",
                main="/Streaming/Channels/101",
                sub="/Streaming/Channels/102",
                lens2_main="/Streaming/Channels/201",
                lens2_sub="/Streaming/Channels/202",
                codec="hevc",
            )
            _camera(session, location.id, "lukow_c8w_97", main=None, sub="/Streaming/Channels/102", codec="hevc")
            _camera(session, location.id, "lukow_c8c_60", main="/Streaming/Channels/101", sub="/Streaming/Channels/102", codec="hevc")
            _camera(
                session,
                location.id,
                "lukow_c8c_102",
                main="/Streaming/Channels/101",
                sub="/Streaming/Channels/102",
                codec="hevc",
                probe_status="failed",
            )
            _camera(session, location.id, "lukow_h8_101", main="/Streaming/Channels/101", sub="/Streaming/Channels/102")
            session.commit()

    def test_preview_uses_go2rtc_restreams_and_no_secret_values(self) -> None:
        with Session(self.engine) as session:
            result = render_frigate_preview(session)

        self.assertIn("mqtt:", result.yaml)
        self.assertIn("enabled: false", result.yaml)
        self.assertIn("threshold: 45", result.yaml)
        self.assertIn("contour_area: 35", result.yaml)
        self.assertIn("min_score: 0.7", result.yaml)
        self.assertIn("threshold: 0.85", result.yaml)
        self.assertIn("rtsp://go2rtc:8554/lukow_h9c_98_sub", result.yaml)
        self.assertIn("rtsp://go2rtc:8554/lukow_h9c_98_lens2_main", result.yaml)
        self.assertNotIn("CAMERA98_PASSWORD", result.yaml)
        self.assertNotIn("secret-h9c", result.yaml)
        self.assertNotIn("rtsp://admin:", result.yaml)

    def test_h9c_lenses_are_separate_frigate_cameras(self) -> None:
        with Session(self.engine) as session:
            result = render_frigate_preview(session)

        names = [camera.name for camera in result.cameras]
        self.assertIn("lukow_h9c_98", names)
        self.assertIn("lukow_h9c_98_lens2", names)

    def test_c8w_record_falls_back_to_substream_when_main_missing(self) -> None:
        with Session(self.engine) as session:
            result = render_frigate_preview(session)

        c8w = next(camera for camera in result.cameras if camera.name == "lukow_c8w_97")
        self.assertEqual(c8w.detect_stream, "lukow_c8w_97_sub")
        self.assertEqual(c8w.record_stream, "lukow_c8w_97_sub")

    def test_unstable_or_degraded_cameras_are_skipped_from_default_nvr(self) -> None:
        with Session(self.engine) as session:
            result = render_frigate_preview(session)

        names = [camera.name for camera in result.cameras]
        self.assertNotIn("lukow_c8c_60", names)
        self.assertNotIn("lukow_c8c_102", names)
        self.assertNotIn("lukow_h8_101", names)
        self.assertIn("lukow_c8c_60: skipped unstable/disabled NVR target", result.warnings)
        self.assertIn("lukow_c8c_102: skipped unstable/disabled NVR target", result.warnings)
        self.assertIn("lukow_h8_101: skipped until CAMERA101_PASSWORD is available", result.warnings)

    def test_runtime_config_writes_to_runtime_path_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "runtime" / "config" / "frigate" / "config.yml"
            with Session(self.engine) as session:
                result = render_frigate_runtime_config(session, output_path=output)

            content = output.read_text(encoding="utf-8")
            self.assertEqual(result.output_path, output)
            self.assertNotIn("lukow_c8c_60", content)
            self.assertNotIn("secret-h9c", content)

    def test_c8c_60_recording_policy_defaults_to_disabled(self) -> None:
        with Session(self.engine) as session:
            camera = session.query(Camera).filter_by(slug="lukow_c8c_60").one()
            policy = get_or_create_recording_policy(session, camera)

            self.assertEqual(policy.mode, "disabled")
            self.assertEqual(policy.retention_days, 7)
            self.assertFalse(policy.enabled)
            self.assertFalse(policy.record_main_stream)
            self.assertFalse(policy.detect_sub_stream)

    def test_explicit_disabled_recording_policy_is_respected(self) -> None:
        with Session(self.engine) as session:
            camera = session.query(Camera).filter_by(slug="lukow_h9c_98").one()
            policy = camera.recording_policy
            self.assertIsNotNone(policy)
            policy.mode = "disabled"
            policy.retention_days = 2
            policy.enabled = False
            policy.record_main_stream = False
            policy.detect_sub_stream = False
            session.commit()

            result = render_frigate_preview(session)

        names = [camera.name for camera in result.cameras]
        self.assertNotIn("lukow_h9c_98", names)
        self.assertNotIn("lukow_h9c_98_lens2", names)
        self.assertIn("lukow_h9c_98: recording policy disabled", result.warnings)

    def test_selected_hours_policy_warns_without_invented_schedule_fields(self) -> None:
        with Session(self.engine) as session:
            camera = session.query(Camera).filter_by(slug="lukow_c8w_97").one()
            policy = camera.recording_policy
            self.assertIsNotNone(policy)
            policy.mode = "continuous_selected_hours"
            policy.retention_days = 1
            policy.enabled = True
            policy.record_main_stream = True
            policy.detect_sub_stream = True
            session.commit()

            result = render_frigate_preview(session)

        self.assertIn(
            "lukow_c8w_97: continuous_selected_hours schedule is deferred; rendering event-based retention only",
            result.warnings,
        )


class FrigateClientTests(unittest.TestCase):
    def test_health_does_not_crash_when_frigate_is_unreachable(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        payload = fetch_frigate_health("http://127.0.0.1:5000", transport=httpx.MockTransport(handler))

        self.assertFalse(payload["reachable"])
        self.assertIn("connection refused", payload["error"])

    def test_events_are_sanitized(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/events")
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "event-1",
                        "camera": "lukow_h9c_98",
                        "label": "person",
                        "score": 0.81,
                        "has_clip": True,
                        "url": "rtsp://admin:secret-h9c@10.20.1.98:554/path",
                    }
                ],
            )

        payload = fetch_frigate_events("http://127.0.0.1:5000", transport=httpx.MockTransport(handler))

        self.assertTrue(payload["reachable"])
        self.assertNotIn("secret-h9c", str(payload))
        self.assertIn("rtsp://admin:***@", str(payload))

    def test_sync_frigate_events_imports_once(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            location = Location(name="Lukow", slug="lukow")
            session.add(location)
            session.flush()
            camera = _camera(session, location.id, "lukow_h9c_98", main="/101", sub="/102")
            session.commit()
            count = sync_frigate_events(
                session,
                [
                    {
                        "id": "event-1",
                        "camera": "lukow_h9c_98",
                        "label": "person",
                        "score": 0.87,
                        "start_time": 1710000000,
                        "end_time": 1710000030,
                        "has_clip": True,
                    }
                ],
            )
            second_count = sync_frigate_events(
                session,
                [{"id": "event-1", "camera": "lukow_h9c_98", "label": "person"}],
            )

            self.assertEqual(count, 1)
            self.assertEqual(second_count, 0)
            event = session.query(Event).one()
            self.assertEqual(event.camera_id, camera.id)
            self.assertEqual(event.source, "frigate")
            self.assertIn("event-1", event.metadata_json or "")


def _camera(
    session: Session,
    location_id: int,
    slug: str,
    *,
    main: str | None,
    sub: str | None,
    lens2_main: str | None = None,
    lens2_sub: str | None = None,
    codec: str = "h264",
    probe_status: str = "ok",
) -> Camera:
    camera = Camera(
        location_id=location_id,
        name=slug,
        slug=slug,
        model="Demo",
        host=f"10.20.1.{len(slug)}",
        rtsp_username="admin",
        rtsp_password_secret_ref="CAMERA98_PASSWORD",
        onvif_username="admin",
        onvif_password_secret_ref="CAMERA98_PASSWORD",
        main_stream_path=main,
        sub_stream_path=sub,
        secondary_main_stream_path=lens2_main,
        secondary_sub_stream_path=lens2_sub,
        video_codec=codec,
        video_status="ok",
        control_status="onvif_ok",
        probe_status=probe_status,
        has_audio=True,
        has_ptz=True,
        has_onvif=True,
        enabled=True,
    )
    session.add(camera)
    session.flush()
    session.add(RecordingPolicy(camera_id=camera.id))
    return camera


if __name__ == "__main__":
    unittest.main()
