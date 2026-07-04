from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ezviz_panel.backend import probe_importer
from ezviz_panel.backend.database import init_db
from ezviz_panel.backend.go2rtc import (
    Go2RtcConfigError,
    apply_stream_path_override,
    list_go2rtc_streams,
    render_go2rtc_preview,
    render_go2rtc_runtime_config,
)
from ezviz_panel.backend.models import Camera, CameraProbeResult, Location
from tests.fixtures.probe_payloads import SANITIZED_RESULT, VPN_FULL_RESULT, VPN_RECHECK_RESULT


class BootstrapProbeImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.secrets_path = self.root / "secrets.local.env"
        self.secrets_path.write_text(
            "\n".join(
                [
                    "CAMERA101_PASSWORD=secret-h8",
                    "CAMERA97_PASSWORD=secret-c8w",
                    "CAMERA98_PASSWORD=secret-h9c",
                    "CAMERA60_PASSWORD=secret-c8c60",
                    "CAMERA102_PASSWORD=secret-c8c102",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_import_without_create_missing_keeps_empty_bootstrap_safe(self) -> None:
        with Session(self.engine) as session:
            records = probe_importer.import_probe_file(session, VPN_FULL_RESULT)

            self.assertEqual(records, [])
            self.assertEqual(session.query(Location).count(), 0)
            self.assertEqual(session.query(Camera).count(), 0)

    def test_create_missing_bootstraps_locations_cameras_and_secret_refs(self) -> None:
        with Session(self.engine) as session:
            records = probe_importer.import_probe_files(
                session,
                [VPN_FULL_RESULT],
                create_missing=True,
                apply=True,
            )

            self.assertEqual(len(records), 5)
            self.assertEqual(session.query(Location).count(), 1)
            cameras = {camera.slug: camera for camera in session.query(Camera).all()}
            self.assertEqual(set(cameras), {"demo_h8_101", "demo_c8w_97", "demo_h9c_98", "demo_c8c_60", "demo_c8c_102"})
            self.assertEqual(cameras["demo_h8_101"].rtsp_password_secret_ref, "CAMERA101_PASSWORD")
            self.assertEqual(cameras["demo_c8w_97"].rtsp_password_secret_ref, "CAMERA97_PASSWORD")
            self.assertEqual(cameras["demo_h9c_98"].rtsp_password_secret_ref, "CAMERA98_PASSWORD")
            self.assertEqual(cameras["demo_c8c_60"].rtsp_password_secret_ref, "CAMERA60_PASSWORD")
            self.assertEqual(cameras["demo_c8c_102"].rtsp_password_secret_ref, "CAMERA102_PASSWORD")
            self.assertEqual(cameras["demo_h8_101"].rtsp_username, "admin")
            self.assertNotIn("secret-h8", str(cameras["demo_h8_101"].__dict__))

    def test_prefer_best_merges_capabilities_and_marks_unstable_streams(self) -> None:
        with Session(self.engine) as session:
            records = probe_importer.import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

            self.assertEqual(len(records), 7)
            self.assertEqual(session.query(CameraProbeResult).count(), 7)
            c8c60 = session.query(Camera).filter(Camera.slug == "demo_c8c_60").one()
            c8c102 = session.query(Camera).filter(Camera.slug == "demo_c8c_102").one()
            self.assertEqual(c8c60.main_stream_path, "/Streaming/Channels/101")
            self.assertEqual(c8c60.sub_stream_path, "/Streaming/Channels/102")
            self.assertTrue(c8c60.has_snapshot)
            self.assertIn(probe_importer.camera_reliability_status(c8c60), {"stable", "degraded"})
            self.assertEqual(probe_importer.camera_reliability_status(c8c102), "unstable")

            default_streams = list_go2rtc_streams(session)
            default_names = [stream.stream_name for stream in default_streams]
            self.assertEqual(len(default_names), 10)
            self.assertIn("demo_h9c_98_lens2_sub", default_names)
            self.assertIn("demo_h8_101_main", default_names)
            self.assertIn("demo_c8w_97_main", default_names)
            self.assertIn("demo_c8c_60_sub", default_names)
            self.assertNotIn("demo_c8c_102_main_experimental", default_names)

            unstable_streams = list_go2rtc_streams(session, include_unstable_streams=True)
            self.assertIn("demo_c8c_102_main_experimental", [stream.stream_name for stream in unstable_streams])

    def test_runtime_render_reports_unstable_and_does_not_leak_secrets(self) -> None:
        output_path = self.root / "runtime" / "config" / "go2rtc.yaml"
        with Session(self.engine) as session:
            probe_importer.import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

            result = render_go2rtc_runtime_config(
                session,
                secrets_env_file=str(self.secrets_path),
                output_path=output_path,
            )

            self.assertEqual(result.stream_count, 10)
            self.assertIn("demo_c8c_102", result.unstable_cameras)
            self.assertNotIn("secret-h9c", str(result.to_public_dict()))
            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("secret-h9c", rendered)
            self.assertNotIn("demo_c8c_102_main_experimental", rendered)

    def test_c8c60_diagnostic_alias_uses_ch1_sub_only_when_requested(self) -> None:
        output_path = self.root / "runtime" / "config" / "go2rtc-diagnostic.yaml"
        with Session(self.engine) as session:
            probe_importer.import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

            default_names = [stream.stream_name for stream in list_go2rtc_streams(session)]
            diagnostic_streams = list_go2rtc_streams(session, include_diagnostic_streams=True)
            diagnostic_names = [stream.stream_name for stream in diagnostic_streams]
            alias = next(stream for stream in diagnostic_streams if stream.stream_name == "demo_c8c_60_sub_ch1")
            yaml_text, warnings = render_go2rtc_preview(session, include_diagnostic_streams=True)
            result = render_go2rtc_runtime_config(
                session,
                secrets_env_file=str(self.secrets_path),
                output_path=output_path,
                include_diagnostic_streams=True,
            )

            self.assertNotIn("demo_c8c_60_sub_ch1", default_names)
            self.assertIn("demo_c8c_60_sub_ch1", diagnostic_names)
            self.assertEqual(alias.path, "/ch1/sub")
            self.assertIn("diagnostic alternate C8C 60 /ch1/sub stream", alias.warnings)
            self.assertIn("demo_c8c_60_sub_ch1", yaml_text)
            self.assertIn("${CAMERA60_PASSWORD}", yaml_text)
            self.assertNotIn("secret-c8c60", yaml_text)
            self.assertTrue(any("diagnostic" in warning.lower() for warning in warnings))
            self.assertEqual(result.stream_count, 11)
            rendered = output_path.read_text(encoding="utf-8")
            self.assertIn("demo_c8c_60_sub_ch1", rendered)
            self.assertIn("/ch1/sub", rendered)
            self.assertNotIn("secret-c8c60", str(result.to_public_dict()))

    def test_stream_path_override_updates_preferred_sub_path_without_credentials(self) -> None:
        with Session(self.engine) as session:
            probe_importer.import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

            updated = apply_stream_path_override(session, "demo_c8c_60", "sub", "/ch1/sub")

            self.assertEqual(updated.sub_stream_path, "/ch1/sub")
            self.assertNotIn("rtsp://", str(updated.__dict__))
            self.assertNotIn("secret-c8c60", str(updated.__dict__))

            with self.assertRaises(Go2RtcConfigError):
                apply_stream_path_override(session, "demo_c8c_60", "sub", "rtsp://admin:secret@10.20.1.60:554/ch1/sub")

    def test_sanitized_json_is_rejected_for_bootstrap_import(self) -> None:
        with Session(self.engine) as session:
            with self.assertRaisesRegex(probe_importer.ProbeImportError, "Sanitized probe result"):
                probe_importer.import_probe_files(session, [SANITIZED_RESULT], create_missing=True, apply=True)


if __name__ == "__main__":
    unittest.main()
