from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend import cli


class FakeSessionLocal:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FrigateCliTests(unittest.TestCase):
    def test_frigate_health_prints_json_without_secret_values(self) -> None:
        out = StringIO()

        with (
            patch("ezviz_panel.backend.cli.load_settings") as settings,
            patch("ezviz_panel.backend.cli.fetch_frigate_health", return_value={"reachable": False, "error": "offline"}),
            redirect_stdout(out),
        ):
            settings.return_value.frigate_url = "http://127.0.0.1:5000"
            code = cli.main(["frigate-health"])

        self.assertEqual(code, 1)
        self.assertIn('"reachable": false', out.getvalue())

    def test_sync_frigate_events_uses_frigate_api_and_session(self) -> None:
        out = StringIO()

        with (
            patch("ezviz_panel.backend.cli.init_db"),
            patch("ezviz_panel.backend.cli.SessionLocal", return_value=FakeSessionLocal()),
            patch("ezviz_panel.backend.cli.load_settings") as settings,
            patch("ezviz_panel.backend.cli.fetch_frigate_events", return_value={"reachable": True, "events": []}),
            patch("ezviz_panel.backend.cli.sync_frigate_events", return_value=0),
            redirect_stdout(out),
        ):
            settings.return_value.frigate_url = "http://127.0.0.1:5000"
            code = cli.main(["sync-frigate-events"])

        self.assertEqual(code, 0)
        self.assertIn("Imported Frigate events: 0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
