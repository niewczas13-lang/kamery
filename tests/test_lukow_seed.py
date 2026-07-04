from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ezviz_panel.backend.database import Base
from ezviz_panel.backend.go2rtc import MissingSecretError, list_go2rtc_streams, render_go2rtc_runtime_config
from ezviz_panel.backend.lukow_seed import seed_lukow_cameras
from ezviz_panel.backend.models import Camera


class LukowSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)

    def test_seed_creates_stable_lukow_stream_inventory_without_secrets(self) -> None:
        with Session(self.engine) as session:
            first = seed_lukow_cameras(session)
            second = seed_lukow_cameras(session)
            streams = list_go2rtc_streams(session)
            c8c = session.query(Camera).filter(Camera.slug == "lukow_c8c_60").one()

        self.assertEqual(first["total"], 3)
        self.assertEqual(set(first["created"]), {"lukow_h9c_98", "lukow_c8w_97", "lukow_c8c_60"})
        self.assertEqual(second["created"], [])
        self.assertEqual(second["updated"], [])
        self.assertEqual(
            [stream.stream_name for stream in streams],
            [
                "lukow_c8c_60_main",
                "lukow_c8c_60_sub",
                "lukow_c8w_97_sub",
                "lukow_h9c_98_main",
                "lukow_h9c_98_sub",
                "lukow_h9c_98_lens2_main",
                "lukow_h9c_98_lens2_sub",
            ],
        )
        self.assertEqual(c8c.video_status, "ok")
        self.assertEqual(c8c.main_stream_path, "/Streaming/Channels/101")
        self.assertEqual(c8c.sub_stream_path, "/ch1/sub")

    def test_seeded_runtime_requires_only_active_stream_secrets(self) -> None:
        with Session(self.engine) as session:
            seed_lukow_cameras(session)

            with self.assertRaises(MissingSecretError) as raised:
                render_go2rtc_runtime_config(
                    session,
                    secrets_env_file=None,
                    output_path="runtime/config/go2rtc/go2rtc.yaml",
                )

        error = str(raised.exception)
        self.assertIn("CAMERA98_PASSWORD", error)
        self.assertIn("CAMERA97_PASSWORD", error)
        self.assertIn("CAMERA60_PASSWORD", error)


if __name__ == "__main__":
    unittest.main()
