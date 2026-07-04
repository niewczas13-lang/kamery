from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


INSTALL_HINT = (
    "Install FFmpeg and make sure ffmpeg/ffprobe are available in PATH. "
    "Windows: winget install Gyan.FFmpeg or install from https://ffmpeg.org. "
    "Linux: use your package manager, for example apt install ffmpeg. "
    "Docker: include ffmpeg in the image."
)


def verify_tools(*, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe") -> dict[str, Any]:
    tools = [
        _check_tool("ffmpeg", ffmpeg_bin),
        _check_tool("ffprobe", ffprobe_bin),
    ]
    return {
        "ok": all(tool["available"] and tool["runs"] for tool in tools),
        "tools": tools,
    }


def format_tool_report(payload: dict[str, Any]) -> str:
    lines = ["Camera probe tool check:"]
    for tool in payload.get("tools", []):
        name = tool.get("name", "tool")
        requested = tool.get("requested", "")
        if tool.get("available") and tool.get("runs"):
            lines.append(f"- {name}: ok ({tool.get('path')})")
            lines.append(f"  {tool.get('version')}")
        elif tool.get("available"):
            lines.append(f"- {name}: found but could not run ({requested})")
            lines.append(f"  {tool.get('error')}")
        else:
            lines.append(f"- {name}: missing ({requested})")
            lines.append(f"  {INSTALL_HINT}")
    return "\n".join(lines)


def _check_tool(name: str, requested: str) -> dict[str, Any]:
    resolved = shutil.which(requested)
    if resolved is None and _path_exists(requested):
        resolved = requested

    if resolved is None:
        return {
            "name": name,
            "requested": requested,
            "available": False,
            "runs": False,
            "path": None,
            "version": None,
            "error": INSTALL_HINT,
        }

    try:
        completed = subprocess.run(
            [resolved, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": name,
            "requested": requested,
            "available": True,
            "runs": False,
            "path": resolved,
            "version": None,
            "error": str(exc),
        }

    output = (completed.stdout or completed.stderr).strip()
    return {
        "name": name,
        "requested": requested,
        "available": True,
        "runs": completed.returncode == 0,
        "path": resolved,
        "version": output.splitlines()[0] if output else "<no version output>",
        "error": None if completed.returncode == 0 else output,
    }


def _path_exists(value: str) -> bool:
    try:
        return Path(value).exists()
    except OSError:
        return False
