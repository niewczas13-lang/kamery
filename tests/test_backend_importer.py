from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend.probe_importer import ProbeImportError, analyze_probe_result, extract_result_items
from tests.fixtures.probe_payloads import C8C_CONTROL_ONLY_RESULT, C8W_RESULT, H8_RESULT, H9C_RESULT, SANITIZED_RESULT


class ProbeImporterTests(unittest.TestCase):
    def test_h8_main_sub_selection(self) -> None:
        analysis = analyze_probe_result(H8_RESULT)

        self.assertEqual(analysis.video_status, "ok")
        self.assertEqual(analysis.control_status, "ptz_ok")
        self.assertEqual(analysis.main_stream_path, "/Streaming/Channels/101")
        self.assertEqual(analysis.sub_stream_path, "/Streaming/Channels/102")
        self.assertIsNone(analysis.secondary_main_stream_path)

    def test_h9c_dual_lens_selection(self) -> None:
        analysis = analyze_probe_result(H9C_RESULT)

        self.assertEqual(analysis.video_status, "ok")
        self.assertEqual(analysis.main_stream_path, "/Streaming/Channels/101")
        self.assertEqual(analysis.sub_stream_path, "/Streaming/Channels/102")
        self.assertEqual(analysis.secondary_main_stream_path, "/Streaming/Channels/201")
        self.assertEqual(analysis.secondary_sub_stream_path, "/Streaming/Channels/202")
        self.assertTrue(analysis.has_audio)

    def test_c8w_substream_only(self) -> None:
        analysis = analyze_probe_result(C8W_RESULT)

        self.assertEqual(analysis.video_status, "partial")
        self.assertIsNone(analysis.main_stream_path)
        self.assertEqual(analysis.sub_stream_path, "/Streaming/Channels/102")
        self.assertEqual(analysis.control_status, "unavailable")

    def test_c8c_control_only(self) -> None:
        analysis = analyze_probe_result(C8C_CONTROL_ONLY_RESULT)

        self.assertEqual(analysis.video_status, "unavailable")
        self.assertEqual(analysis.control_status, "ptz_ok")
        self.assertTrue(analysis.has_ptz)

    def test_rejects_sanitized_probe_result(self) -> None:
        with self.assertRaisesRegex(ProbeImportError, "Sanitized probe result"):
            extract_result_items(SANITIZED_RESULT)


if __name__ == "__main__":
    unittest.main()
