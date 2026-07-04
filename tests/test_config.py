from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.camera_probe.config import load_config, parse_simple_yaml


class ConfigTests(unittest.TestCase):
    def test_loads_example_config(self) -> None:
        config = load_config(Path(__file__).resolve().parents[1] / "cameras.example.yml")

        self.assertEqual(len(config.locations), 1)
        self.assertEqual(len(config.cameras), 3)
        self.assertEqual(config.locations[0].network_cidr, "192.168.80.0/24")
        self.assertEqual(config.cameras[0].id, "lukow_h9c_98")
        self.assertEqual(config.cameras[0].host, "192.168.80.98")
        self.assertTrue(config.cameras[0].enabled)

    def test_ignores_comments_outside_quotes(self) -> None:
        parsed = parse_simple_yaml(
            """
locations:
  - id: test # ignored
    name: "Name # kept"
cameras:
  - id: cam1
    host: 10.0.0.10
"""
        )

        self.assertEqual(parsed["locations"][0]["id"], "test")
        self.assertEqual(parsed["locations"][0]["name"], "Name # kept")

    def test_loads_credentials_from_env_file_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "cameras.local.yml"
            secrets_path = root / "secrets.local.env"
            config_path.write_text(
                """
cameras:
  - id: cam1
    name: Camera 1
    location_id: test
    model: Test
    host: 192.168.1.10
    rtsp_username_env: CAM_USER
    rtsp_password_env: CAM_PASSWORD
""",
                encoding="utf-8",
            )
            secrets_path.write_text("CAM_USER=admin\nCAM_PASSWORD=secret-value\n", encoding="utf-8")

            config = load_config(config_path, secrets_env_file=secrets_path)

        self.assertEqual(config.cameras[0].rtsp_username, "admin")
        self.assertEqual(config.cameras[0].rtsp_password, "secret-value")
        self.assertEqual(config.cameras[0].onvif_username, "admin")
        self.assertEqual(config.cameras[0].onvif_password, "secret-value")


if __name__ == "__main__":
    unittest.main()
