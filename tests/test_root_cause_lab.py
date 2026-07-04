from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend.root_cause_lab import (
    classify_root_cause,
    compare_c8c60_paths,
    parse_ffmpeg_log,
    render_report_json,
    render_report_markdown,
    sanitize_root_cause_text,
)


class RootCauseLabTests(unittest.TestCase):
    def test_sanitizes_direct_rtsp_url_and_secret_values(self) -> None:
        raw = "ffmpeg rtsp://admin:plain-code@192.168.80.98:554/ch1/sub verification code: ABCD12EF"

        sanitized = sanitize_root_cause_text(raw, secret_values=["plain-code"])

        self.assertIn("rtsp://admin:***@192.168.80.98:554/ch1/sub", sanitized)
        self.assertIn("verification code: ***", sanitized)
        self.assertNotIn("plain-code", sanitized)
        self.assertNotIn("ABCD12EF", sanitized)

    def test_parses_ffmpeg_metrics_from_successful_video_only_log(self) -> None:
        log = """
Input #0, rtsp, from 'rtsp://127.0.0.1:8554/lukow_h9c_98_sub':
  Stream #0:0: Video: hevc, 768x432, 10 fps
frame= 1200 fps= 10 q=-0.0 Lsize=N/A time=00:02:00.10 bitrate=N/A speed=1.01x
"""

        metrics = parse_ffmpeg_log(log, target_duration_seconds=120, exit_code=0)

        self.assertTrue(metrics.connected)
        self.assertEqual(metrics.frames, 1200)
        self.assertEqual(metrics.fps, 10.0)
        self.assertAlmostEqual(metrics.speed, 1.01)
        self.assertEqual(metrics.eof_count, 0)
        self.assertEqual(metrics.hevc_error_count, 0)
        self.assertTrue(metrics.stable)

    def test_parses_ffmpeg_eof_hevc_errors_and_marks_unstable(self) -> None:
        log = """
[hevc @ 000001] PPS id out of range: 0
[hevc @ 000001] Could not find ref with POC 9
Failed reading RTSP data: End of file
frame=   20 fps=0.2 q=-0.0 Lsize=N/A time=00:00:02.00 bitrate=N/A speed=0.05x
"""

        metrics = parse_ffmpeg_log(log, target_duration_seconds=120, exit_code=1)

        self.assertFalse(metrics.stable)
        self.assertEqual(metrics.frames, 20)
        self.assertEqual(metrics.eof_count, 1)
        self.assertEqual(metrics.hevc_error_count, 2)
        self.assertEqual(metrics.actual_duration_seconds, 2.0)

    def test_classifies_direct_and_go2rtc_fail_as_camera_network_or_vpn(self) -> None:
        conclusions = classify_root_cause(direct_stable=False, go2rtc_stable=False)

        self.assertIn("kamera, sieć, Wi-Fi, VPN albo rejestrator", " ".join(conclusions))

    def test_classifies_direct_ok_go2rtc_fail_as_go2rtc_issue(self) -> None:
        conclusions = classify_root_cause(direct_stable=True, go2rtc_stable=False)

        self.assertIn("go2rtc", " ".join(conclusions))

    def test_classifies_panel_fail_after_stable_direct_and_go2rtc_as_browser_or_frontend(self) -> None:
        conclusions = classify_root_cause(direct_stable=True, go2rtc_stable=True, panel_stable=False)

        self.assertIn("frontendzie, przeglądarce, HEVC", " ".join(conclusions))

    def test_classifies_frigate_recorder_and_vpn_impact(self) -> None:
        conclusions = classify_root_cause(
            direct_stable=True,
            go2rtc_stable=True,
            frigate_off_improves=True,
            recorder_off_improves=True,
            lan_stable=True,
            vpn_stable=False,
            cpu_or_gpu_saturated=True,
        )
        joined = " ".join(conclusions)

        self.assertIn("Frigate zwiększa", joined)
        self.assertIn("Rejestrator", joined)
        self.assertIn("VPN", joined)
        self.assertIn("HEVC", joined)

    def test_c8c60_path_comparison_prefers_stable_ch1_sub(self) -> None:
        recommendation = compare_c8c60_paths(
            [
                {
                    "name": "lukow_c8c_60_sub",
                    "path": "/Streaming/Channels/102",
                    "stable": False,
                    "fps": 0.2,
                    "speed": 0.05,
                    "eof_count": 1,
                    "hevc_error_count": 12,
                },
                {
                    "name": "lukow_c8c_60_sub_ch1",
                    "path": "/ch1/sub",
                    "stable": True,
                    "fps": 10.0,
                    "speed": 1.0,
                    "eof_count": 0,
                    "hevc_error_count": 2,
                },
            ]
        )

        self.assertEqual(recommendation["preferred_sub_path"], "/ch1/sub")
        self.assertEqual(recommendation["preferred_stream"], "lukow_c8c_60_sub_ch1")

    def test_c8c60_path_comparison_does_not_prefer_unstable_paths(self) -> None:
        recommendation = compare_c8c60_paths(
            [
                {
                    "name": "lukow_c8c_60_sub",
                    "path": "/Streaming/Channels/102",
                    "stable": False,
                    "fps": 4.8,
                    "speed": 0.477,
                    "eof_count": 1,
                    "hevc_error_count": 0,
                },
                {
                    "name": "lukow_c8c_60_sub_ch1",
                    "path": "/ch1/sub",
                    "stable": False,
                    "fps": 2.7,
                    "speed": 0.342,
                    "eof_count": 1,
                    "hevc_error_count": 13,
                },
            ]
        )

        self.assertIsNone(recommendation["preferred_sub_path"])
        self.assertIsNone(recommendation["preferred_stream"])
        self.assertEqual(recommendation["least_bad_sub_path"], "/Streaming/Channels/102")
        self.assertTrue(recommendation["all_candidates_unstable"])

    def test_report_rendering_does_not_leak_secrets(self) -> None:
        payload = {
            "summary": "bad rtsp://admin:plain-code@192.168.80.60:554/ch1/sub",
            "direct_camera": [{"stream": "c8c", "error": "plain-code EOF"}],
            "go2rtc": [],
            "conclusions": ["verification code: ABCD12EF"],
        }

        markdown = render_report_markdown(payload, secret_values=["plain-code"])
        json_text = render_report_json(payload, secret_values=["plain-code"])

        self.assertNotIn("plain-code", markdown + json_text)
        self.assertNotIn("ABCD12EF", markdown + json_text)
        self.assertIn("rtsp://admin:***@", markdown + json_text)


if __name__ == "__main__":
    unittest.main()
