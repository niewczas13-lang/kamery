from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend.models import Camera
from ezviz_panel.backend.onvif_ptz import (
    PtzCommandError,
    PtzSecretMissingError,
    PtzUnsupportedError,
    execute_ptz_command,
    probe_ptz_camera,
)


class FakeProfile:
    token = "profile-token"
    PTZConfiguration = object()


class FakePtzAdapter:
    def __init__(self) -> None:
        self.events: list[object] = []
        self.fail_connect = False
        self.fail_move = False
        self.fail_stop = False

    def connect(self, camera: Camera, password: str, timeout: float) -> object:
        self.events.append(("connect", camera.slug, password, timeout))
        if self.fail_connect:
            raise RuntimeError(f"cannot connect with {password}")
        return object()

    def get_profiles(self, connection: object) -> list[FakeProfile]:
        self.events.append("profiles")
        return [FakeProfile()]

    def get_ptz_capabilities(self, connection: object) -> dict[str, bool]:
        self.events.append("capabilities")
        return {"continuous_move": True}

    def continuous_move(self, connection: object, profile: object, command: str, speed: float) -> None:
        self.events.append(("move", command, speed))
        if self.fail_move:
            raise RuntimeError("move failed with secret-h9c")

    def stop(self, connection: object, profile: object) -> None:
        self.events.append("stop")
        if self.fail_stop:
            raise RuntimeError("stop failed with secret-h9c")


class OnvifPtzTests(unittest.TestCase):
    def test_move_calls_stop_after_duration(self) -> None:
        adapter = FakePtzAdapter()

        result = execute_ptz_command(
            _camera(),
            "left",
            secrets={"CAMERA98_PASSWORD": "secret-h9c"},
            adapter=adapter,
            duration_ms=300,
            sleep=lambda _: None,
        )

        self.assertEqual(result.status, "moved")
        self.assertTrue(result.stopped)
        self.assertIn(("move", "left", 0.3), adapter.events)
        self.assertEqual(adapter.events[-1], "stop")
        self.assertNotIn("secret-h9c", str(result.to_public_dict()))

    def test_stop_command_only_stops(self) -> None:
        adapter = FakePtzAdapter()

        result = execute_ptz_command(
            _camera(),
            "stop",
            secrets={"CAMERA98_PASSWORD": "secret-h9c"},
            adapter=adapter,
            sleep=lambda _: None,
        )

        self.assertEqual(result.status, "stopped")
        self.assertTrue(result.stopped)
        self.assertIn("stop", adapter.events)
        self.assertNotIn("move", str(adapter.events))

    def test_exception_during_move_still_attempts_stop(self) -> None:
        adapter = FakePtzAdapter()
        adapter.fail_move = True

        with self.assertRaises(PtzCommandError) as raised:
            execute_ptz_command(
                _camera(),
                "right",
                secrets={"CAMERA98_PASSWORD": "secret-h9c"},
                adapter=adapter,
                sleep=lambda _: None,
            )

        self.assertTrue(raised.exception.stopped)
        self.assertIn("stop", adapter.events)
        self.assertNotIn("secret-h9c", str(raised.exception))

    def test_stop_failure_after_move_returns_warning(self) -> None:
        adapter = FakePtzAdapter()
        adapter.fail_stop = True

        result = execute_ptz_command(
            _camera(),
            "up",
            secrets={"CAMERA98_PASSWORD": "secret-h9c"},
            adapter=adapter,
            sleep=lambda _: None,
        )

        self.assertEqual(result.status, "moved")
        self.assertFalse(result.stopped)
        self.assertIn("stop failed", result.warning or "")
        self.assertNotIn("secret-h9c", result.warning or "")

    def test_missing_secret_is_rejected_before_connect(self) -> None:
        adapter = FakePtzAdapter()

        with self.assertRaises(PtzSecretMissingError):
            execute_ptz_command(_camera(), "left", secrets={}, adapter=adapter, sleep=lambda _: None)

        self.assertEqual(adapter.events, [])

    def test_camera_without_ptz_is_rejected_before_connect(self) -> None:
        adapter = FakePtzAdapter()
        camera = _camera()
        camera.has_ptz = False

        with self.assertRaises(PtzUnsupportedError):
            execute_ptz_command(
                camera,
                "left",
                secrets={"CAMERA98_PASSWORD": "secret-h9c"},
                adapter=adapter,
                sleep=lambda _: None,
            )

        self.assertEqual(adapter.events, [])

    def test_probe_reports_profiles_without_exposing_secret(self) -> None:
        adapter = FakePtzAdapter()

        result = probe_ptz_camera(_camera(), secrets={"CAMERA98_PASSWORD": "secret-h9c"}, adapter=adapter)

        self.assertTrue(result["connected"])
        self.assertEqual(result["profile_count"], 1)
        self.assertTrue(result["ptz_profile_found"])
        self.assertNotIn("secret-h9c", str(result))


def _camera() -> Camera:
    return Camera(
        id=98,
        location_id=1,
        name="H9C",
        slug="lukow_h9c_98",
        model="CS-H9c-R100-8G55WKFL",
        host="10.20.1.98",
        rtsp_username="admin",
        rtsp_password_secret_ref="CAMERA98_PASSWORD",
        onvif_username="admin",
        onvif_password_secret_ref="CAMERA98_PASSWORD",
        has_ptz=True,
        has_onvif=True,
    )


if __name__ == "__main__":
    unittest.main()
