from pathlib import Path
from unittest.mock import patch
import sys
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezviz_panel.backend.go2rtc import fetch_go2rtc_health, fetch_go2rtc_streams
from ezviz_panel.backend.settings import load_settings


class Go2RtcHealthTests(unittest.TestCase):
    def test_health_uses_streams_fallback_and_counts_empty_streams(self) -> None:
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request.url.path)
            if request.url.path == "/api":
                return httpx.Response(404)
            if request.url.path == "/api/streams":
                return httpx.Response(200, json={})
            return httpx.Response(200, text="go2rtc")

        payload = fetch_go2rtc_health(
            "http://127.0.0.1:1984",
            transport=httpx.MockTransport(handler),
        )

        self.assertTrue(payload["reachable"])
        self.assertEqual(payload["stream_count"], 0)
        self.assertIsNone(payload["error"])
        self.assertIn("/api", requests)
        self.assertIn("/api/streams", requests)

    def test_health_does_not_trust_proxy_environment(self) -> None:
        captured: dict[str, object] = {}

        class CapturingClient(httpx.Client):
            def __init__(self, *args: object, **kwargs: object) -> None:
                captured.update(kwargs)
                super().__init__(*args, transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})), **kwargs)

        with patch("ezviz_panel.backend.go2rtc.httpx.Client", CapturingClient):
            payload = fetch_go2rtc_health("http://127.0.0.1:1984")

        self.assertTrue(payload["reachable"])
        self.assertIs(captured["trust_env"], False)

    def test_settings_prefers_go2rtc_api_url_env(self) -> None:
        with patch.dict("os.environ", {"GO2RTC_API_URL": "http://127.0.0.1:2999"}, clear=False):
            self.assertEqual(load_settings().go2rtc_url, "http://127.0.0.1:2999")

    def test_streams_proxy_sanitizes_rtsp_credentials(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "demo_stream": {
                        "producers": [
                            {"url": "rtsp://admin:super-secret@10.20.1.98:554/Streaming/Channels/102"}
                        ],
                        "consumers": [],
                    }
                },
            )

        payload = fetch_go2rtc_streams(
            "http://127.0.0.1:1984",
            transport=httpx.MockTransport(handler),
        )

        self.assertTrue(payload["reachable"])
        self.assertIn("rtsp://admin:***@", str(payload))
        self.assertNotIn("super-secret", str(payload))


if __name__ == "__main__":
    unittest.main()
