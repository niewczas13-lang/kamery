from __future__ import annotations

from copy import deepcopy


def stream(path: str, role: str, resolution: str, *, audio: bool = False, fps: float = 10.0) -> dict[str, object]:
    return {
        "path": path,
        "stream_role": role,
        "video_codec": "hevc",
        "audio_codec": "aac" if audio else None,
        "resolution": resolution,
        "fps": fps,
        "bitrate": 1_000_000,
        "has_audio": audio,
        "probe_duration_ms": 100,
        "error": None,
    }


H8_RESULT = {
    "camera_id": "demo_h8_101",
    "location_id": "demo",
    "name": "Demo H8",
    "model": "CS-H8",
    "serial_number": "DEMO-H8-SERIAL",
    "host": "10.20.1.101",
    "status": "ok",
    "working_rtsp_paths": [
        stream("/ch1/main", "main", "2880x1620"),
        stream("/ch1/sub", "sub", "768x432"),
        stream("/Streaming/Channels/101", "lens1_main", "2880x1620"),
        stream("/Streaming/Channels/102", "lens1_sub", "768x432"),
    ],
    "onvif_reachable": True,
    "ptz_supported": True,
    "snapshot_possible": True,
    "two_way_audio_candidate": False,
}


H9C_RESULT = {
    "camera_id": "demo_h9c_98",
    "location_id": "demo",
    "name": "Demo H9C",
    "model": "CS-H9c-R100-8G55WKFL",
    "serial_number": "DEMO-H9C-SERIAL",
    "host": "10.20.1.98",
    "status": "ok",
    "working_rtsp_paths": [
        stream("/ch1/main", "main", "2880x1620", audio=True),
        stream("/ch1/sub", "sub", "768x432", audio=True),
        stream("/Streaming/Channels/101", "lens1_main", "2880x1620", audio=True),
        stream("/Streaming/Channels/102", "lens1_sub", "768x432", audio=True),
        stream("/Streaming/Channels/201", "lens2_main", "2880x1620", audio=True),
        stream("/Streaming/Channels/202", "lens2_sub", "768x432", audio=True),
    ],
    "onvif_reachable": True,
    "ptz_supported": True,
    "snapshot_possible": True,
    "two_way_audio_candidate": False,
}


C8W_RESULT = {
    "camera_id": "demo_c8w_97",
    "location_id": "demo",
    "name": "Demo C8W",
    "model": "CS-C8W",
    "serial_number": "DEMO-C8W-SERIAL",
    "host": "10.20.1.97",
    "status": "partial",
    "working_rtsp_paths": [
        stream("/Streaming/Channels/102", "lens1_sub", "768x432"),
    ],
    "onvif_reachable": False,
    "onvif_status": "http_reachable_but_onvif_failed",
    "ptz_supported": False,
    "snapshot_possible": True,
    "two_way_audio_candidate": False,
}

C8W_FULL_RESULT = {
    **C8W_RESULT,
    "working_rtsp_paths": [
        stream("/ch1/main", "main", "2560x1440", fps=15.0),
        stream("/ch1/sub", "sub", "768x432"),
        stream("/Streaming/Channels/101", "lens1_main", "2560x1440", fps=15.0),
        stream("/Streaming/Channels/102", "lens1_sub", "768x432"),
    ],
}


C8C_CONTROL_ONLY_RESULT = {
    "camera_id": "demo_c8c_60",
    "location_id": "demo",
    "name": "Demo C8C",
    "model": "CS-C8c-R100-1J5WKFL",
    "serial_number": "DEMO-C8C-SERIAL",
    "host": "10.20.1.60",
    "status": "partial",
    "working_rtsp_paths": [],
    "onvif_reachable": True,
    "onvif_status": "ptz_supported",
    "ptz_supported": True,
    "snapshot_possible": False,
    "two_way_audio_candidate": False,
}

C8C_60_FULL_TIMEOUT_RESULT = {
    **C8C_CONTROL_ONLY_RESULT,
    "working_rtsp_paths": [
        stream("/ch1/main", "main", "2880x1620", audio=True, fps=6.0),
        stream("/ch1/sub", "sub", "768x432", audio=True),
        stream("/Streaming/Channels/101", "lens1_main", "2880x1620", audio=True, fps=6.0),
        stream("/Streaming/Channels/102", "lens1_sub", "768x432", audio=True),
    ],
    "snapshot_possible": False,
    "errors": ["ffmpeg timed out while capturing snapshot"],
}


C8C_60_RECHECK_RESULT = {
    **C8C_60_FULL_TIMEOUT_RESULT,
    "status": "ok",
    "working_rtsp_paths": [
        stream("/ch1/sub", "sub", "768x432", audio=True),
        stream("/Streaming/Channels/101", "lens1_main", "2880x1620", audio=True, fps=6.0),
        stream("/Streaming/Channels/102", "lens1_sub", "768x432", audio=True),
    ],
    "snapshot_possible": True,
    "errors": [],
}


C8C_102_FAILED_RESULT = {
    "camera_id": "demo_c8c_102",
    "location_id": "demo",
    "name": "Demo C8C 102",
    "model": "CS-C8c-R100-1J5WKFL",
    "serial_number": "DEMO-C8C102-SERIAL",
    "host": "10.20.1.102",
    "status": "failed",
    "working_rtsp_paths": [],
    "onvif_reachable": False,
    "onvif_status": "unreachable",
    "ptz_supported": False,
    "snapshot_possible": False,
    "two_way_audio_candidate": False,
    "errors": ["RTSP port 554 is not reachable", "No common ONVIF ports are reachable"],
}


C8C_102_RECHECK_RESULT = {
    **C8C_102_FAILED_RESULT,
    "status": "partial",
    "working_rtsp_paths": [
        stream("/ch1/main", "main", "2880x1620", audio=True, fps=6.0),
    ],
    "onvif_reachable": True,
    "onvif_status": "ptz_supported",
    "ptz_supported": True,
    "snapshot_possible": False,
    "errors": ["ffmpeg timed out while capturing snapshot"],
}


ALL_PROBE_RESULT = {
    "generated_at": "2026-07-02T10:00:00+00:00",
    "rtsp_transport": "tcp",
    "results": [
        H8_RESULT,
        H9C_RESULT,
        C8W_RESULT,
        C8C_CONTROL_ONLY_RESULT,
    ],
}


VPN_FULL_RESULT = {
    "generated_at": "2026-07-04T00:09:14+00:00",
    "rtsp_transport": "tcp",
    "results": [
        {**H8_RESULT, "camera_id": "demo_h8_101"},
        {**H9C_RESULT, "camera_id": "demo_h9c_98"},
        {**C8W_FULL_RESULT, "camera_id": "demo_c8w_97"},
        C8C_60_FULL_TIMEOUT_RESULT,
        C8C_102_FAILED_RESULT,
    ],
}


VPN_RECHECK_RESULT = {
    "generated_at": "2026-07-04T00:14:20+00:00",
    "rtsp_transport": "tcp",
    "results": [
        C8C_60_RECHECK_RESULT,
        C8C_102_RECHECK_RESULT,
    ],
}


SANITIZED_RESULT = deepcopy(ALL_PROBE_RESULT)
SANITIZED_RESULT["results"][0]["camera_id"] = "dem****01"
SANITIZED_RESULT["results"][0]["host"] = "10.20.1.xxx"
