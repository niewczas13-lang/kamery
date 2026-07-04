from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend import cli
from ezviz_panel.backend.models import Camera
from ezviz_panel.backend.onvif_ptz import PtzCommandResult
from ezviz_panel.backend.settings import Settings


class FakeSessionLocal:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class PtzCliTests(unittest.TestCase):
    def test_ptz_test_mocked_path_does_not_print_secret(self) -> None:
        out = StringIO()
        camera = _camera()
        result = PtzCommandResult(
            camera_id=98,
            command="left",
            status="moved",
            duration_ms=300,
            stopped=True,
        )

        with (
            patch("ezviz_panel.backend.cli.init_db"),
            patch("ezviz_panel.backend.cli.SessionLocal", return_value=FakeSessionLocal()),
            patch("ezviz_panel.backend.cli.load_settings", return_value=Settings(secrets_env_file="secrets.local.env")),
            patch("ezviz_panel.backend.cli.load_secret_refs", return_value={"CAMERA98_PASSWORD": "secret-h9c"}),
            patch("ezviz_panel.backend.cli._get_camera_by_slug", return_value=camera),
            patch("ezviz_panel.backend.cli.execute_ptz_command", return_value=result),
            redirect_stdout(out),
        ):
            code = cli.main(["ptz-test", "--camera-slug", "lukow_h9c_98", "--command", "left", "--duration-ms", "300"])

        self.assertEqual(code, 0)
        self.assertIn('"stopped": true', out.getvalue())
        self.assertNotIn("secret-h9c", out.getvalue())

    def test_ptz_test_missing_camera_returns_error(self) -> None:
        err = StringIO()

        with (
            patch("ezviz_panel.backend.cli.init_db"),
            patch("ezviz_panel.backend.cli.SessionLocal", return_value=FakeSessionLocal()),
            patch("ezviz_panel.backend.cli.load_settings", return_value=Settings(secrets_env_file="secrets.local.env")),
            patch("ezviz_panel.backend.cli.load_secret_refs", return_value={"CAMERA98_PASSWORD": "secret-h9c"}),
            patch("ezviz_panel.backend.cli._get_camera_by_slug", return_value=None),
            redirect_stderr(err),
        ):
            code = cli.main(["ptz-test", "--camera-slug", "missing", "--command", "left"])

        self.assertEqual(code, 2)
        self.assertIn("Camera not found", err.getvalue())

    def test_ptz_test_missing_secret_returns_error_without_value(self) -> None:
        err = StringIO()

        with (
            patch("ezviz_panel.backend.cli.init_db"),
            patch("ezviz_panel.backend.cli.SessionLocal", return_value=FakeSessionLocal()),
            patch("ezviz_panel.backend.cli.load_settings", return_value=Settings(secrets_env_file="secrets.local.env")),
            patch("ezviz_panel.backend.cli.load_secret_refs", return_value={}),
            patch("ezviz_panel.backend.cli._get_camera_by_slug", return_value=_camera()),
            redirect_stderr(err),
        ):
            code = cli.main(["ptz-test", "--camera-slug", "lukow_h9c_98", "--command", "left"])

        self.assertEqual(code, 2)
        self.assertIn("PTZ secret is not configured", err.getvalue())
        self.assertNotIn("secret-h9c", err.getvalue())


def _camera() -> Camera:
    return Camera(
        id=98,
        location_id=1,
        name="H9C",
        slug="lukow_h9c_98",
        model="CS-H9c-R100-8G55WKFL",
        host="10.20.1.98",
        onvif_username="admin",
        onvif_password_secret_ref="CAMERA98_PASSWORD",
        has_ptz=True,
        has_onvif=True,
    )


if __name__ == "__main__":
    unittest.main()
