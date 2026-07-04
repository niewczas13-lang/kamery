from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ezviz_panel.backend.app import create_app
from ezviz_panel.backend.models import Admin
from ezviz_panel.backend.security import hash_password
from ezviz_panel.backend.settings import Settings
from tests.fixtures.probe_payloads import C8C_CONTROL_ONLY_RESULT, C8W_RESULT, H8_RESULT, H9C_RESULT


class Go2RtcRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.secrets_path = self.root / "secrets.local.env"
        self.secrets_path.write_text(
            "\n".join(
                [
                    "CAMERA98_PASSWORD=secret-h9c",
                    "CAMERA101_PASSWORD=secret-h8",
                    "CAMERA97_PASSWORD=secret-c8w",
                    "CAMERA60_PASSWORD=secret-c8c",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.runtime_config_path = self.root / "runtime" / "config" / "go2rtc" / "go2rtc.yaml"
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.app = create_app(
            settings=Settings(
                database_url="sqlite://",
                secret_key="test-secret-key-that-is-long-enough-for-hs256",
                secrets_env_file=str(self.secrets_path),
                cors_origins=(),
                go2rtc_config_path=str(self.runtime_config_path),
                snapshot_dir=str(self.root / "runtime" / "snapshots"),
            ),
            database_engine=self.engine,
        )
        with Session(self.engine) as session:
            session.add(Admin(username="admin", password_hash=hash_password("pass123")))
            session.commit()
        self.client = TestClient(self.app)
        token = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "pass123"}).json()[
            "access_token"
        ]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.location_id = self._create_location()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_stream_inventory_matches_probe_scope_and_hides_secrets(self) -> None:
        self._seed_stage_3a_cameras()

        response = self.client.get("/api/v1/streams", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        names = [item["stream_name"] for item in payload]
        self.assertEqual(
            names,
            [
                "lukow_c8w_97_sub",
                "lukow_h8_101_main",
                "lukow_h8_101_sub",
                "lukow_h9c_98_main",
                "lukow_h9c_98_sub",
                "lukow_h9c_98_lens2_main",
                "lukow_h9c_98_lens2_sub",
            ],
        )
        self.assertNotIn("secret-h9c", str(payload))
        self.assertNotIn("secret-h8", str(payload))
        self.assertTrue(any("HEVC" in warning for item in payload for warning in item["warnings"]))
        h9c = [item for item in payload if item["camera_name"] == "H9C 98"]
        h8 = [item for item in payload if item["camera_name"] == "H8 101"]
        c8w = [item for item in payload if item["camera_name"] == "C8W 97"]
        c8c = [item for item in payload if item["camera_name"].startswith("C8C")]
        self.assertEqual(len(h9c), 4)
        self.assertEqual(len(h8), 2)
        self.assertEqual(len(c8w), 1)
        self.assertEqual(len(c8c), 0)
        main_stream = next(item for item in payload if item["stream_name"] == "lukow_h9c_98_main")
        sub_stream = next(item for item in payload if item["stream_name"] == "lukow_h9c_98_sub")
        lens2_main = next(item for item in payload if item["stream_name"] == "lukow_h9c_98_lens2_main")
        self.assertEqual(main_stream["quality_role"], "main")
        self.assertEqual(main_stream["quality_label"], "Wysoka")
        self.assertFalse(main_stream["is_recommended_for_grid"])
        self.assertTrue(main_stream["is_recommended_for_focus"])
        self.assertTrue(main_stream["is_recommended_for_recording"])
        self.assertFalse(main_stream["is_recommended_for_detection"])
        self.assertEqual(sub_stream["quality_role"], "sub")
        self.assertEqual(sub_stream["quality_label"], "Szybka")
        self.assertTrue(sub_stream["is_recommended_for_grid"])
        self.assertFalse(sub_stream["is_recommended_for_focus"])
        self.assertFalse(sub_stream["is_recommended_for_recording"])
        self.assertTrue(sub_stream["is_recommended_for_detection"])
        self.assertEqual(lens2_main["quality_role"], "main")

    def test_stream_detail_404s_for_control_only_camera(self) -> None:
        self._seed_stage_3a_cameras()

        found = self.client.get("/api/v1/streams/lukow_h9c_98_lens2_main", headers=self.headers)
        missing = self.client.get("/api/v1/streams/lukow_c8c_60_main", headers=self.headers)

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.json()["path"], "/Streaming/Channels/201")
        self.assertEqual(missing.status_code, 404)

    def test_runtime_render_writes_resolved_config_but_masks_response(self) -> None:
        self._seed_stage_3a_cameras()

        response = self.client.post("/api/v1/config/go2rtc/render-runtime", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stream_count"], 7)
        self.assertEqual(payload["output_path"], str(self.runtime_config_path))
        self.assertIn("lukow_c8c_60", payload["skipped_cameras"])
        self.assertNotIn("secret-h9c", str(payload))
        rendered = self.runtime_config_path.read_text(encoding="utf-8")
        self.assertIn("secret-h9c", rendered)
        self.assertIn("lukow_h9c_98_lens2_sub", rendered)

    def test_runtime_render_requires_all_stream_secrets(self) -> None:
        self._seed_stage_3a_cameras()
        self.secrets_path.write_text("CAMERA98_PASSWORD=secret-h9c\n", encoding="utf-8")

        response = self.client.post("/api/v1/config/go2rtc/render-runtime", headers=self.headers)

        self.assertEqual(response.status_code, 400)
        self.assertIn("CAMERA101_PASSWORD", response.json()["detail"])
        self.assertFalse(self.runtime_config_path.exists())

    def test_preview_uses_secret_refs_not_real_values(self) -> None:
        self._seed_stage_3a_cameras()

        response = self.client.get("/api/v1/config/go2rtc/preview", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        yaml_text = response.json()["yaml"]
        self.assertIn("${CAMERA98_PASSWORD}", yaml_text)
        self.assertIn("${CAMERA101_PASSWORD}", yaml_text)
        self.assertNotIn("secret-h9c", yaml_text)
        self.assertNotIn("secret-h8", yaml_text)

    def test_snapshot_for_control_only_camera_returns_409(self) -> None:
        camera_ids = self._seed_stage_3a_cameras()

        response = self.client.post(f"/api/v1/cameras/{camera_ids['lukow_c8c_60']}/snapshot", headers=self.headers)

        self.assertEqual(response.status_code, 409)
        self.assertIn("no video stream", response.json()["detail"].lower())

    def test_debug_streams_page_hides_secrets_and_shows_control_only_warning(self) -> None:
        self._seed_stage_3a_cameras()

        response = self.client.get("/debug/streams")

        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn("lukow_h9c_98_main", html)
        self.assertIn("lukow_c8c_60", html)
        self.assertIn("no go2rtc stream generated", html)
        self.assertIn("HEVC", html)
        self.assertNotIn("secret-h9c", html)

    def _seed_stage_3a_cameras(self) -> dict[str, int]:
        camera_specs = [
            ("lukow_h9c_98", "H9C 98", "10.20.1.98", "CS-H9c-R100-8G55WKFL", "CAMERA98_PASSWORD", H9C_RESULT),
            ("lukow_h8_101", "H8 101", "10.20.1.101", "CS-H8", "CAMERA101_PASSWORD", H8_RESULT),
            ("lukow_c8w_97", "C8W 97", "10.20.1.97", "CS-C8W", "CAMERA97_PASSWORD", C8W_RESULT),
            ("lukow_c8c_60", "C8C 60", "10.20.1.60", "CS-C8c-R100-1J5WKFL", "CAMERA60_PASSWORD", C8C_CONTROL_ONLY_RESULT),
        ]
        camera_ids: dict[str, int] = {}
        for slug, name, host, model, secret_ref, probe in camera_specs:
            camera_id = self._create_camera(slug, name, host, model, secret_ref)
            camera_ids[slug] = camera_id
            imported = self.client.post(
                f"/api/v1/cameras/{camera_id}/probe-results/import",
                headers=self.headers,
                json=probe,
            )
            self.client.post(
                f"/api/v1/cameras/{camera_id}/apply-probe-result/{imported.json()['id']}",
                headers=self.headers,
            )
        return camera_ids

    def _create_location(self) -> int:
        response = self.client.post(
            "/api/v1/locations",
            headers=self.headers,
            json={"name": "Lukow", "slug": "lukow"},
        )
        return response.json()["id"]

    def _create_camera(self, slug: str, name: str, host: str, model: str, secret_ref: str) -> int:
        response = self.client.post(
            "/api/v1/cameras",
            headers=self.headers,
            json={
                "location_id": self.location_id,
                "name": name,
                "slug": slug,
                "model": model,
                "host": host,
                "rtsp_password_secret_ref": secret_ref,
                "onvif_password_secret_ref": secret_ref,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]


if __name__ == "__main__":
    unittest.main()
