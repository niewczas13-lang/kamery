from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.camera_probe.masking import (
    mask_ip,
    mask_url,
    sanitize_for_sharing,
    sanitize_sensitive_object,
    sanitize_text,
)


class MaskingTests(unittest.TestCase):
    def test_masks_rtsp_password_in_url(self) -> None:
        masked = mask_url("rtsp://admin:secret-code@10.10.1.101:554/Streaming/Channels/101")

        self.assertNotIn("secret-code", masked)
        self.assertEqual(masked, "rtsp://admin:***@10.10.1.101:554/Streaming/Channels/101")

    def test_masks_secret_query_in_url(self) -> None:
        masked = mask_url("http://10.10.1.101/onvif?password=secret-code")

        self.assertNotIn("secret-code", masked)
        self.assertEqual(masked, "http://10.10.1.101/onvif?***")

    def test_sanitizes_urls_and_raw_secret_values(self) -> None:
        sanitized = sanitize_text(
            "failed rtsp://admin:secret-code@10.0.0.1:554/ch1/main with VERIF123",
            ["VERIF123"],
        )

        self.assertNotIn("VERIF123", sanitized)
        self.assertIn("***", sanitized)

    def test_does_not_change_plain_host(self) -> None:
        self.assertEqual(sanitize_text("host 10.0.0.1 unavailable"), "host 10.0.0.1 unavailable")

    def test_masks_passwords_in_nested_json(self) -> None:
        payload = {
            "rtsp_password": "VERIF123",
            "items": [
                {
                    "onvif_password": "VERIF123",
                    "error": "bad rtsp://admin:VERIF123@10.10.1.101:554/ch1/main",
                }
            ],
        }

        sanitized = sanitize_sensitive_object(payload, ["VERIF123"])

        self.assertEqual(sanitized["rtsp_password"], "***")
        self.assertEqual(sanitized["items"][0]["onvif_password"], "***")
        self.assertNotIn("VERIF123", str(sanitized))

    def test_masks_ip_for_sharing(self) -> None:
        self.assertEqual(mask_ip("10.10.1.101"), "10.10.1.xxx")
        self.assertEqual(mask_ip("camera at 192.168.1.55"), "camera at 192.168.1.xxx")

    def test_sanitize_for_sharing_masks_private_fields(self) -> None:
        payload = {
            "selected_camera_id": "lukow_h9c_01",
            "camera_id": "lukow_h9c_01",
            "location_id": "lukow",
            "name": "Lukow gate camera",
            "host": "10.10.1.101",
            "serial_number": "BD0776201",
            "snapshot_path": "snapshots/probe/lukow_h9c_01.jpg",
            "errors": ["failed rtsp://admin:VERIF123@10.10.1.101:554/ch1/main"],
        }

        sanitized = sanitize_for_sharing(payload, ["VERIF123"])

        self.assertEqual(sanitized["host"], "10.10.1.xxx")
        self.assertNotEqual(sanitized["selected_camera_id"], "lukow_h9c_01")
        self.assertEqual(sanitized["name"], "<name>")
        self.assertEqual(sanitized["serial_number"], "BD0****01")
        self.assertEqual(sanitized["snapshot_path"], "<snapshot_path>")
        self.assertNotIn("VERIF123", str(sanitized))
        self.assertNotIn("10.10.1.101", str(sanitized))


if __name__ == "__main__":
    unittest.main()
