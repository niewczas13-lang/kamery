from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.camera_probe.ffprobe import FFProbeFailed, guess_stream_role, parse_ffprobe_json


class FFProbeParsingTests(unittest.TestCase):
    def test_parses_video_audio_and_bitrate(self) -> None:
        stream = parse_ffprobe_json(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 2560,
                        "height": 1440,
                        "avg_frame_rate": "30000/1001",
                        "bit_rate": "4200000",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"bit_rate": "4500000"},
            },
            "/Streaming/Channels/101",
        )

        self.assertEqual(stream.video_codec, "h264")
        self.assertEqual(stream.stream_role, "lens1_main")
        self.assertEqual(stream.audio_codec, "aac")
        self.assertEqual(stream.resolution, "2560x1440")
        self.assertEqual(stream.fps, 29.97)
        self.assertEqual(stream.bitrate, 4200000)
        self.assertTrue(stream.has_audio)

    def test_uses_format_bitrate_when_stream_bitrate_missing(self) -> None:
        stream = parse_ffprobe_json(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "hevc",
                        "width": 1920,
                        "height": 1080,
                        "avg_frame_rate": "15/1",
                    }
                ],
                "format": {"bit_rate": "2100000"},
            },
            "/ch1/main",
        )

        self.assertEqual(stream.video_codec, "hevc")
        self.assertEqual(stream.resolution, "1920x1080")
        self.assertEqual(stream.fps, 15.0)
        self.assertEqual(stream.bitrate, 2100000)
        self.assertFalse(stream.has_audio)

    def test_requires_video_stream(self) -> None:
        with self.assertRaises(FFProbeFailed):
            parse_ffprobe_json({"streams": [{"codec_type": "audio", "codec_name": "aac"}]}, "/ch1/sub")

    def test_guesses_ezviz_stream_roles(self) -> None:
        self.assertEqual(guess_stream_role("/ch1/main"), "main")
        self.assertEqual(guess_stream_role("/ch1/sub"), "sub")
        self.assertEqual(guess_stream_role("/Streaming/Channels/101"), "lens1_main")
        self.assertEqual(guess_stream_role("/Streaming/Channels/102"), "lens1_sub")
        self.assertEqual(guess_stream_role("/Streaming/Channels/201"), "lens2_main")
        self.assertEqual(guess_stream_role("/Streaming/Channels/202"), "lens2_sub")
        self.assertEqual(guess_stream_role("/custom"), "unknown")


if __name__ == "__main__":
    unittest.main()
