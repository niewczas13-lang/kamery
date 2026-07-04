from __future__ import annotations

import platform
import socket
import subprocess


def host_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return True


def tcp_port_open(host: str, port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def ping_host(host: str, timeout_seconds: float = 2.0) -> bool | None:
    timeout_ms = max(1, int(timeout_seconds * 1000))
    if platform.system().lower().startswith("win"):
        command = ["ping", "-n", "1", "-w", str(timeout_ms), host]
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, int(timeout_seconds))), host]

    try:
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except FileNotFoundError:
        return None
    return completed.returncode == 0
