from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ezviz_panel.backend import lukow_seed
from ezviz_panel.backend.database import Base, init_db
from ezviz_panel.backend.go2rtc import build_rtsp_preview_url, list_go2rtc_streams
from ezviz_panel.backend.lukow_seed import seed_lukow_cameras
from ezviz_panel.backend.models import Camera, Location


CAMERA_SOURCE_COLUMNS = [
    "rtsp_source_host",
    "rtsp_source_username",
    "rtsp_source_password_secret_ref",
    "rtsp_source_main_path",
    "rtsp_source_sub_path",
    "rtsp_source_secondary_main_path",
    "rtsp_source_secondary_sub_path",
]


def _make_engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


class NvrRestreamSourceStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _make_engine()
        Base.metadata.create_all(self.engine)

    def _camera(self, session: Session, **overrides) -> Camera:
        location = Location(name="Lukow", slug="lukow")
        session.add(location)
        session.flush()
        values = dict(
            location_id=location.id,
            name="C8C 60",
            slug="lukow_c8c_60",
            model="CS-C8c-R100-1J5WKFL",
            host="192.168.80.60",
            rtsp_username="admin",
            rtsp_password_secret_ref="CAMERA60_PASSWORD",
            main_stream_path="/Streaming/Channels/101",
            sub_stream_path="/ch1/sub",
            video_status="ok",
            probe_status="manual_seed",
            enabled=True,
        )
        values.update(overrides)
        camera = Camera(**values)
        session.add(camera)
        session.commit()
        return camera

    def test_streams_stay_direct_without_source_host(self) -> None:
        with Session(self.engine) as session:
            self._camera(session)
            streams = {stream.stream_name: stream for stream in list_go2rtc_streams(session)}

        sub = streams["lukow_c8c_60_sub"]
        self.assertEqual(sub.host, "192.168.80.60")
        self.assertEqual(sub.path, "/ch1/sub")
        self.assertEqual(sub.rtsp_password_secret_ref, "CAMERA60_PASSWORD")

    def test_stream_uses_recorder_source_when_configured(self) -> None:
        with Session(self.engine) as session:
            self._camera(
                session,
                rtsp_source_host="192.168.80.200",
                rtsp_source_username="admin",
                rtsp_source_password_secret_ref="NVR_PASSWORD",
                rtsp_source_sub_path="/Streaming/Channels/402",
            )
            streams = {stream.stream_name: stream for stream in list_go2rtc_streams(session)}

        sub = streams["lukow_c8c_60_sub"]
        main = streams["lukow_c8c_60_main"]
        self.assertEqual(sub.host, "192.168.80.200")
        self.assertEqual(sub.path, "/Streaming/Channels/402")
        self.assertEqual(sub.rtsp_username, "admin")
        self.assertEqual(sub.rtsp_password_secret_ref, "NVR_PASSWORD")
        self.assertEqual(
            build_rtsp_preview_url(sub),
            "rtsp://admin:${NVR_PASSWORD}@192.168.80.200:554/Streaming/Channels/402",
        )
        self.assertTrue(any("recorder" in warning for warning in sub.warnings))
        # MAIN has no recorder path configured, so it stays direct.
        self.assertEqual(main.host, "192.168.80.60")
        self.assertEqual(main.path, "/Streaming/Channels/101")
        self.assertEqual(main.rtsp_password_secret_ref, "CAMERA60_PASSWORD")

    def test_recorder_source_adds_stream_missing_on_direct_camera(self) -> None:
        with Session(self.engine) as session:
            self._camera(
                session,
                slug="lukow_c8w_97",
                name="C8W 97",
                main_stream_path=None,
                sub_stream_path="/Streaming/Channels/102",
                rtsp_source_host="192.168.80.200",
                rtsp_source_password_secret_ref="NVR_PASSWORD",
                rtsp_source_main_path="/Streaming/Channels/301",
                rtsp_source_sub_path="/Streaming/Channels/302",
            )
            streams = {stream.stream_name: stream for stream in list_go2rtc_streams(session)}

        self.assertIn("lukow_c8w_97_main", streams)
        main = streams["lukow_c8w_97_main"]
        self.assertEqual(main.host, "192.168.80.200")
        self.assertEqual(main.path, "/Streaming/Channels/301")


class SqliteSourceColumnMigrationTests(unittest.TestCase):
    def test_init_db_adds_source_columns_to_legacy_cameras_table(self) -> None:
        engine = _make_engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE cameras (id INTEGER PRIMARY KEY, host VARCHAR(260))"))

        init_db(engine)

        with engine.connect() as conn:
            columns = {row[1] for row in conn.execute(text("PRAGMA table_info(cameras)"))}
        for column in CAMERA_SOURCE_COLUMNS:
            self.assertIn(column, columns)


class LukowNvrSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = _make_engine()
        Base.metadata.create_all(self.engine)
        self._original_restream = dict(lukow_seed.LUKOW_NVR_RESTREAM)
        self._original_channels = dict(lukow_seed.LUKOW_NVR_CHANNELS)

    def tearDown(self) -> None:
        lukow_seed.LUKOW_NVR_RESTREAM.clear()
        lukow_seed.LUKOW_NVR_RESTREAM.update(self._original_restream)
        lukow_seed.LUKOW_NVR_CHANNELS.clear()
        lukow_seed.LUKOW_NVR_CHANNELS.update(self._original_channels)

    def test_seed_defaults_keep_direct_camera_sources(self) -> None:
        with Session(self.engine) as session:
            seed_lukow_cameras(session)
            cameras = session.query(Camera).all()

        for camera in cameras:
            self.assertIsNone(camera.rtsp_source_host, camera.slug)
            self.assertIsNone(camera.rtsp_source_sub_path, camera.slug)

    def test_seed_applies_recorder_channels_when_enabled(self) -> None:
        lukow_seed.LUKOW_NVR_RESTREAM.update({"enabled": True, "host": "192.168.80.200"})
        lukow_seed.LUKOW_NVR_CHANNELS.update(
            {
                "lukow_h9c_98": {"primary": 1, "secondary": 2},
                "lukow_c8c_60": {"primary": 4},
            }
        )

        with Session(self.engine) as session:
            seed_lukow_cameras(session)
            h9c = session.query(Camera).filter(Camera.slug == "lukow_h9c_98").one()
            c8c = session.query(Camera).filter(Camera.slug == "lukow_c8c_60").one()
            c8w = session.query(Camera).filter(Camera.slug == "lukow_c8w_97").one()

        self.assertEqual(c8c.rtsp_source_host, "192.168.80.200")
        self.assertEqual(c8c.rtsp_source_username, "admin")
        self.assertEqual(c8c.rtsp_source_password_secret_ref, "NVR_PASSWORD")
        self.assertEqual(c8c.rtsp_source_main_path, "/Streaming/Channels/401")
        self.assertEqual(c8c.rtsp_source_sub_path, "/Streaming/Channels/402")
        self.assertEqual(h9c.rtsp_source_main_path, "/Streaming/Channels/101")
        self.assertEqual(h9c.rtsp_source_sub_path, "/Streaming/Channels/102")
        self.assertEqual(h9c.rtsp_source_secondary_main_path, "/Streaming/Channels/201")
        self.assertEqual(h9c.rtsp_source_secondary_sub_path, "/Streaming/Channels/202")
        # No channel mapping for C8W -> stays direct.
        self.assertIsNone(c8w.rtsp_source_host)

    def test_seed_reverts_to_direct_when_restream_disabled_again(self) -> None:
        lukow_seed.LUKOW_NVR_RESTREAM.update({"enabled": True, "host": "192.168.80.200"})
        lukow_seed.LUKOW_NVR_CHANNELS.update({"lukow_c8c_60": {"primary": 4}})
        with Session(self.engine) as session:
            seed_lukow_cameras(session)
        lukow_seed.LUKOW_NVR_RESTREAM.update({"enabled": False})

        with Session(self.engine) as session:
            seed_lukow_cameras(session)
            c8c = session.query(Camera).filter(Camera.slug == "lukow_c8c_60").one()

        self.assertIsNone(c8c.rtsp_source_host)
        self.assertIsNone(c8c.rtsp_source_sub_path)


if __name__ == "__main__":
    unittest.main()
