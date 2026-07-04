from pathlib import Path
import logging
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from ezviz_panel.backend.app import create_app
from ezviz_panel.backend.models import Admin, Camera
from ezviz_panel.backend.onvif_ptz import PtzCommandResult
from ezviz_panel.backend.probe_importer import import_probe_files
from ezviz_panel.backend.security import hash_password, verify_password
from ezviz_panel.backend.settings import Settings
from tests.fixtures.probe_payloads import C8C_CONTROL_ONLY_RESULT, H9C_RESULT, SANITIZED_RESULT, VPN_FULL_RESULT, VPN_RECHECK_RESULT


class BackendApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        secrets_path = Path(self.tmp.name) / "secrets.local.env"
        secrets_path.write_text("CAMERA98_PASSWORD=secret-h9c\nCAMERA98_USER=admin\n", encoding="utf-8")
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.ptz_adapter = ApiFakePtzAdapter()
        self.app = create_app(
            settings=Settings(
                database_url="sqlite://",
                secret_key="test-secret-key-that-is-long-enough-for-hs256",
                secrets_env_file=str(secrets_path),
                frigate_url="http://frigate.test",
                cors_origins=(),
            ),
            database_engine=self.engine,
            ptz_adapter=self.ptz_adapter,
            frigate_transport=httpx.MockTransport(self._frigate_handler),
        )
        with Session(self.engine) as session:
            session.add(Admin(username="admin", password_hash=hash_password("pass123")))
            session.commit()
        self.client = TestClient(self.app)
        token = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "pass123"}).json()[
            "access_token"
        ]
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _frigate_handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text="Frigate is running. Alive and healthy!")
        if request.url.path == "/api/events":
            return httpx.Response(200, json=[])
        if request.url.path == "/api/config":
            return httpx.Response(200, json={"cameras": {"lukow_h9c_98": {}}})
        if request.url.path == "/api/review":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={"detail": "not found"})

    def test_password_hashing(self) -> None:
        password_hash = hash_password("example")

        self.assertNotIn("example", password_hash)
        self.assertTrue(verify_password("example", password_hash))
        self.assertFalse(verify_password("wrong", password_hash))

    def test_location_and_camera_crud_do_not_return_secret_values(self) -> None:
        location = self.client.post(
            "/api/v1/locations",
            headers=self.headers,
            json={"name": "Lukow", "slug": "lukow", "network_cidr": "10.20.1.0/24"},
        )
        self.assertEqual(location.status_code, 201)
        location_id = location.json()["id"]

        camera = self.client.post(
            "/api/v1/cameras",
            headers=self.headers,
            json={
                "location_id": location_id,
                "name": "H9C",
                "slug": "demo_h9c_98",
                "model": "CS-H9c-R100-8G55WKFL",
                "host": "10.20.1.98",
                "rtsp_password_secret_ref": "CAMERA98_PASSWORD",
                "onvif_password_secret_ref": "CAMERA98_PASSWORD",
            },
        )

        self.assertEqual(camera.status_code, 201)
        payload = camera.json()
        self.assertEqual(payload["rtsp_password_secret_ref"], "CAMERA98_PASSWORD")
        self.assertTrue(payload["rtsp_secret_configured"])
        self.assertNotIn("secret-h9c", str(payload))

    def test_import_apply_probe_and_go2rtc_preview(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_h9c_98", "10.20.1.98", "CS-H9c-R100-8G55WKFL")

        imported = self.client.post(
            f"/api/v1/cameras/{camera_id}/probe-results/import",
            headers=self.headers,
            json=H9C_RESULT,
        )
        self.assertEqual(imported.status_code, 201)
        probe_id = imported.json()["id"]

        applied = self.client.post(
            f"/api/v1/cameras/{camera_id}/apply-probe-result/{probe_id}",
            headers=self.headers,
        )
        self.assertEqual(applied.status_code, 200)
        camera = applied.json()["camera"]
        self.assertEqual(camera["main_stream_path"], "/Streaming/Channels/101")
        self.assertEqual(camera["secondary_main_stream_path"], "/Streaming/Channels/201")
        self.assertTrue(camera["has_ptz"])

        preview = self.client.get("/api/v1/config/go2rtc/preview", headers=self.headers)
        self.assertEqual(preview.status_code, 200)
        yaml_text = preview.json()["yaml"]
        self.assertIn("demo_h9c_98_lens2_main", yaml_text)
        self.assertIn("${CAMERA98_PASSWORD}", yaml_text)
        self.assertNotIn("secret-h9c", yaml_text)

    def test_api_rejects_sanitized_probe_import(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_h8_101", "10.20.1.101", "CS-H8")

        response = self.client.post(
            f"/api/v1/cameras/{camera_id}/probe-results/import",
            headers=self.headers,
            json=SANITIZED_RESULT,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Sanitized probe result", response.json()["detail"])

    def test_camera_list_exposes_dynamic_reliability_status(self) -> None:
        with Session(self.engine) as session:
            import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

        response = self.client.get("/api/v1/cameras", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        cameras = {camera["slug"]: camera for camera in response.json()}
        self.assertEqual(cameras["demo_c8c_102"]["reliability_status"], "unstable")

    def test_ptz_rejects_camera_without_ptz(self) -> None:
        location_id = self._create_location()
        no_ptz_camera_id = self._create_camera(location_id, "demo_no_ptz", "10.20.1.10", "Demo")

        no_ptz = self.client.post(f"/api/v1/cameras/{no_ptz_camera_id}/ptz/up", headers=self.headers)
        self.assertEqual(no_ptz.status_code, 409)
        self.assertEqual(no_ptz.json()["detail"], "PTZ not supported or not detected")

    def test_ptz_rejects_missing_secret(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(
            location_id,
            "demo_missing_secret",
            "10.20.1.11",
            "Demo",
            onvif_password_secret_ref="CAMERA_MISSING_PASSWORD",
            has_ptz=True,
        )

        response = self.client.post(f"/api/v1/cameras/{camera_id}/ptz/left", headers=self.headers)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "PTZ secret is not configured")

    def test_ptz_rejects_invalid_command(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_ptz", "10.20.1.12", "Demo", has_ptz=True)

        response = self.client.post(f"/api/v1/cameras/{camera_id}/ptz/spin", headers=self.headers)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Unsupported PTZ command")

    def test_ptz_adapter_connection_failure_is_sanitized(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_ptz_fail", "10.20.1.13", "Demo", has_ptz=True)
        self.ptz_adapter.fail_connect = True

        response = self.client.post(f"/api/v1/cameras/{camera_id}/ptz/left", headers=self.headers)

        self.assertEqual(response.status_code, 502)
        self.assertIn("ONVIF connection failed", response.json()["detail"])
        self.assertNotIn("secret-h9c", str(response.json()))

    def test_ptz_successful_move_returns_status_and_stops(self) -> None:
        location_id = self._create_location()
        ptz_camera_id = self._create_camera(location_id, "demo_c8c_60", "10.20.1.60", "CS-C8c-R100-1J5WKFL")
        imported = self.client.post(
            f"/api/v1/cameras/{ptz_camera_id}/probe-results/import",
            headers=self.headers,
            json=C8C_CONTROL_ONLY_RESULT,
        )
        self.client.post(
            f"/api/v1/cameras/{ptz_camera_id}/apply-probe-result/{imported.json()['id']}",
            headers=self.headers,
        )

        ptz = self.client.post(
            f"/api/v1/cameras/{ptz_camera_id}/ptz/up",
            headers=self.headers,
            json={"duration_ms": 1, "speed": 0.2},
        )

        self.assertEqual(ptz.status_code, 200)
        payload = ptz.json()
        self.assertEqual(payload["camera_id"], ptz_camera_id)
        self.assertEqual(payload["command"], "up")
        self.assertEqual(payload["status"], "moved")
        self.assertTrue(payload["stopped"])
        self.assertIn(("move", "up", 0.2), self.ptz_adapter.events)
        self.assertIn("stop", self.ptz_adapter.events)
        self.assertNotIn("secret-h9c", str(payload))

    def test_ptz_stop_command_returns_status(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_ptz_stop", "10.20.1.14", "Demo", has_ptz=True)

        response = self.client.post(f"/api/v1/cameras/{camera_id}/ptz/stop", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "stopped")
        self.assertTrue(response.json()["stopped"])

    def test_ptz_move_error_still_attempts_stop_and_sanitizes_response(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_ptz_move_fail", "10.20.1.15", "Demo", has_ptz=True)
        self.ptz_adapter.fail_move = True

        response = self.client.post(f"/api/v1/cameras/{camera_id}/ptz/right", headers=self.headers)

        self.assertEqual(response.status_code, 502)
        self.assertIn("stop", self.ptz_adapter.events)
        self.assertNotIn("secret-h9c", str(response.json()))

    def test_ptz_request_does_not_log_secrets(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "demo_ptz_log", "10.20.1.16", "Demo", has_ptz=True)
        log_stream = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        handler = logging.StreamHandler(log_stream)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            self.client.post(f"/api/v1/cameras/{camera_id}/ptz/left", headers=self.headers)
        finally:
            root_logger.removeHandler(handler)

        log_stream.seek(0)
        self.assertNotIn("secret-h9c", log_stream.read())
        log_stream.close()

    def test_database_stores_secret_refs_not_values(self) -> None:
        location_id = self._create_location()
        self._create_camera(location_id, "demo_h9c_98", "10.20.1.98", "CS-H9c-R100-8G55WKFL")

        with Session(self.engine) as session:
            camera = session.query(Camera).filter(Camera.slug == "demo_h9c_98").one()
            self.assertEqual(camera.rtsp_password_secret_ref, "CAMERA98_PASSWORD")
            self.assertNotIn("secret-h9c", str(camera.__dict__))

    def test_frigate_config_preview_endpoint_does_not_return_secrets(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "lukow_h9c_98", "10.20.1.98", "CS-H9c-R100-8G55WKFL")
        self.client.patch(
            f"/api/v1/cameras/{camera_id}",
            headers=self.headers,
            json={
                "main_stream_path": "/Streaming/Channels/101",
                "sub_stream_path": "/Streaming/Channels/102",
                "secondary_main_stream_path": "/Streaming/Channels/201",
                "secondary_sub_stream_path": "/Streaming/Channels/202",
                "video_codec": "hevc",
                "video_status": "ok",
            },
        )

        response = self.client.get("/api/v1/frigate/config/preview", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("lukow_h9c_98_lens2", payload["yaml"])
        self.assertNotIn("secret-h9c", str(payload))
        self.assertNotIn("rtsp://admin:", str(payload))

    def test_frigate_health_and_events_endpoints_return_safe_payloads(self) -> None:
        health = self.client.get("/api/v1/frigate/health", headers=self.headers)
        events = self.client.get("/api/v1/frigate/events", headers=self.headers)

        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.json()["reachable"])
        self.assertEqual(events.status_code, 200)
        self.assertTrue(events.json()["reachable"])
        self.assertNotIn("secret-h9c", str(health.json()) + str(events.json()))

    def test_live_diagnostics_endpoint_returns_safe_stream_stability_summary(self) -> None:
        with Session(self.engine) as session:
            import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

        response = self.client.get("/api/v1/diagnostics/live", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["backend"]["ok"])
        self.assertIn("active_stream_limit", payload)
        self.assertEqual(payload["active_stream_limit"]["default"], 4)
        self.assertTrue(any("HEVC" in warning for warning in payload["warnings"]))
        self.assertTrue(any("C8C 60" in warning for warning in payload["warnings"]))
        self.assertTrue(any("C8C 102" in warning for warning in payload["warnings"]))
        status_by_slug = {item["camera_slug"]: item["stability_status"] for item in payload["stream_stability"]}
        self.assertIn(status_by_slug["demo_h9c_98"], {"stabilny", "obniżona stabilność"})
        self.assertIn(status_by_slug["demo_c8c_60"], {"obniżona stabilność", "niestabilny"})
        self.assertEqual(status_by_slug["demo_c8c_102"], "eksperymentalny")
        self.assertNotIn("secret-h9c", str(payload))
        self.assertNotIn("rtsp://admin:", str(payload))

    def test_stream_inventory_includes_unstable_experimental_streams_for_manual_wall_tiles(self) -> None:
        with Session(self.engine) as session:
            import_probe_files(
                session,
                [VPN_FULL_RESULT, VPN_RECHECK_RESULT],
                create_missing=True,
                apply=True,
                prefer_best=True,
            )

        response = self.client.get("/api/v1/streams", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        names = [item["stream_name"] for item in payload]
        self.assertIn("demo_c8c_102_main_experimental", names)
        experimental = next(item for item in payload if item["stream_name"] == "demo_c8c_102_main_experimental")
        self.assertEqual(experimental["camera_name"], "Demo C8C 102")
        self.assertEqual(experimental["stream_role"], "main_experimental")
        self.assertFalse(experimental["is_recommended_for_grid"])
        self.assertNotIn("secret-h9c", str(payload))
        self.assertNotIn("rtsp://admin:", str(payload))

    def test_recording_policy_patch_validates_mode_and_retention(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "lukow_c8c_60", "10.20.1.60", "CS-C8c")

        invalid_mode = self.client.patch(
            f"/api/v1/cameras/{camera_id}/recording-policy",
            headers=self.headers,
            json={"mode": "forever", "retention_days": 1},
        )
        invalid_retention = self.client.patch(
            f"/api/v1/cameras/{camera_id}/recording-policy",
            headers=self.headers,
            json={"mode": "events_only", "retention_days": 0},
        )
        valid = self.client.patch(
            f"/api/v1/cameras/{camera_id}/recording-policy",
            headers=self.headers,
            json={"mode": "events_only", "retention_days": 2},
        )

        self.assertEqual(invalid_mode.status_code, 422)
        self.assertEqual(invalid_retention.status_code, 422)
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["mode"], "events_only")
        self.assertEqual(valid.json()["retention_days"], 2)

    def test_recording_policy_endpoint_enables_c8c60_on_substream_by_default(self) -> None:
        location_id = self._create_location()
        camera_id = self._create_camera(location_id, "lukow_c8c_60", "10.20.1.60", "CS-C8c")

        response = self.client.get(f"/api/v1/cameras/{camera_id}/recording-policy", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["mode"], "events_only")
        self.assertEqual(payload["retention_days"], 1)
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["record_main_stream"])
        self.assertTrue(payload["detect_sub_stream"])

    def _create_location(self) -> int:
        response = self.client.post(
            "/api/v1/locations",
            headers=self.headers,
            json={"name": "Demo", "slug": "demo"},
        )
        return response.json()["id"]

    def _create_camera(
        self,
        location_id: int,
        slug: str,
        host: str,
        model: str,
        *,
        onvif_password_secret_ref: str = "CAMERA98_PASSWORD",
        has_ptz: bool = False,
    ) -> int:
        response = self.client.post(
            "/api/v1/cameras",
            headers=self.headers,
            json={
                "location_id": location_id,
                "name": slug,
                "slug": slug,
                "model": model,
                "host": host,
                "rtsp_password_secret_ref": "CAMERA98_PASSWORD",
                "onvif_password_secret_ref": onvif_password_secret_ref,
                "has_ptz": has_ptz,
            },
        )
        return response.json()["id"]


class ApiFakeProfile:
    token = "profile-token"
    PTZConfiguration = object()


class ApiFakePtzAdapter:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.fail_connect = False
        self.fail_move = False

    def connect(self, camera: Camera, password: str, timeout: float) -> object:
        self.events.append(("connect", camera.slug, password, timeout))
        if self.fail_connect:
            raise RuntimeError(f"connect failed with {password}")
        return object()

    def get_profiles(self, connection: object) -> list[ApiFakeProfile]:
        self.events.append("profiles")
        return [ApiFakeProfile()]

    def get_ptz_capabilities(self, connection: object) -> dict[str, bool]:
        self.events.append("capabilities")
        return {"continuous_move": True}

    def continuous_move(self, connection: object, profile: object, command: str, speed: float) -> None:
        self.events.append(("move", command, speed))
        if self.fail_move:
            raise RuntimeError("move failed with secret-h9c")

    def stop(self, connection: object, profile: object) -> None:
        self.events.append("stop")


if __name__ == "__main__":
    unittest.main()
