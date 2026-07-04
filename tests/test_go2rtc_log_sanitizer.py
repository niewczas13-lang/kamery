from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend.log_sanitizer import sanitize_go2rtc_log_text


class Go2RtcLogSanitizerTests(unittest.TestCase):
    def test_masks_rtsp_url_password(self) -> None:
        raw = "upstream error: EOF rtsp://admin:camera-secret@10.20.1.98:554/Streaming/Channels/102"

        sanitized = sanitize_go2rtc_log_text(raw)

        self.assertIn("rtsp://admin:***@10.20.1.98:554/Streaming/Channels/102", sanitized)
        self.assertNotIn("camera-secret", sanitized)

    def test_masks_secret_values_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            secrets_path = Path(tmp) / "secrets.local.env"
            secrets_path.write_text("CAMERA98_PASSWORD=plain-verification-code\n", encoding="utf-8")

            sanitized = sanitize_go2rtc_log_text(
                "go2rtc retry with plain-verification-code in stderr",
                secrets_env_file=secrets_path,
            )

        self.assertIn("***", sanitized)
        self.assertNotIn("plain-verification-code", sanitized)

    def test_masks_verification_code_fields(self) -> None:
        sanitized = sanitize_go2rtc_log_text("verification code: ABCD12EF")

        self.assertIn("verification code: ***", sanitized)
        self.assertNotIn("ABCD12EF", sanitized)


if __name__ == "__main__":
    unittest.main()
