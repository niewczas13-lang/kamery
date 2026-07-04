from __future__ import annotations

import base64
import hashlib
import http.client
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

from .masking import sanitize_text
from .models import CameraConfig, OnvifProbeResult
from .network import tcp_port_open

DEFAULT_ONVIF_PORTS = (80, 8000, 8080, 8899)
DEFAULT_ONVIF_PATHS = ("/onvif/device_service", "/onvif/Device")


def probe_onvif(
    camera: CameraConfig,
    *,
    ports: tuple[int, ...] = DEFAULT_ONVIF_PORTS,
    timeout_seconds: float = 3.0,
) -> OnvifProbeResult:
    result = OnvifProbeResult()

    try:
        for port in ports:
            if not tcp_port_open(camera.host, port, timeout_seconds=timeout_seconds):
                result.port_results.append({"port": port, "status": "port_closed"})
                continue

            result.open_ports.append(port)
            port_errors: list[str] = []
            port_status = "http_reachable_but_onvif_failed"

            for path in DEFAULT_ONVIF_PATHS:
                url = f"http://{camera.host}:{port}{path}"
                ok, status, body_or_error = _soap_request(
                    camera,
                    port,
                    path,
                    _device_capabilities_body(camera),
                    timeout_seconds,
                )
                if not ok:
                    port_status = "onvif_auth_failed" if status == "onvif_auth_failed" else port_status
                    port_errors.append(body_or_error)
                    continue

                result.reachable = True
                result.service_url = url
                lower = body_or_error.lower()
                result.ptz_supported = "ptz" in lower and "xaddr" in lower
                result.audio_output_supported = "audiooutput" in lower or "audio output" in lower

                media_url = _find_first_xaddr(body_or_error, "media") or url
                profiles_ok, profiles_status, profiles_body = _request_profiles(camera, media_url, timeout_seconds)
                if profiles_ok:
                    profiles_lower = profiles_body.lower()
                    result.profiles_detected = "profiles" in profiles_lower
                    result.ptz_supported = result.ptz_supported or "ptzconfiguration" in profiles_lower
                    result.audio_output_supported = (
                        result.audio_output_supported or "audiooutputconfiguration" in profiles_lower
                    )
                    result.profiles_status = (
                        "onvif_profiles_available" if result.profiles_detected else "unknown"
                    )
                else:
                    result.errors.append(profiles_body)
                    result.profiles_status = profiles_status

                result.ptz_status = (
                    "ptz_supported"
                    if result.ptz_supported
                    else "ptz_not_supported"
                    if result.profiles_detected
                    else "unknown"
                )
                result.status = result.ptz_status if result.ptz_status != "unknown" else result.profiles_status
                result.port_results.append(
                    {
                        "port": port,
                        "status": result.profiles_status,
                        "ptz_status": result.ptz_status,
                        "path": path,
                    }
                )
                return result

            result.port_results.append({"port": port, "status": port_status})
            result.errors.extend(port_errors)

        if not result.open_ports:
            result.status = "port_closed"
            result.errors.append("No common ONVIF ports are reachable")
        elif result.status == "unknown":
            statuses = {item.get("status") for item in result.port_results}
            if "onvif_auth_failed" in statuses:
                result.status = "onvif_auth_failed"
            elif "http_reachable_but_onvif_failed" in statuses:
                result.status = "http_reachable_but_onvif_failed"
    except Exception as exc:
        result.status = "unknown"
        result.errors.append(sanitize_text(f"ONVIF probe failed: {exc}", camera.secrets()))

    return result


def _soap_request(
    camera: CameraConfig,
    port: int,
    path: str,
    body: str,
    timeout_seconds: float,
) -> tuple[bool, str, str]:
    headers = {"Content-Type": "application/soap+xml; charset=utf-8"}
    connection = http.client.HTTPConnection(camera.host, port, timeout=timeout_seconds)
    try:
        connection.request("POST", path, body=body.encode("utf-8"), headers=headers)
        response = connection.getresponse()
        payload = response.read(256_000).decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException) as exc:
        return False, "http_reachable_but_onvif_failed", sanitize_text(str(exc), camera.secrets())
    finally:
        connection.close()

    if response.status in {401, 403}:
        return False, "onvif_auth_failed", f"ONVIF authentication rejected on port {port}"
    if response.status < 200 or response.status >= 300:
        return False, "http_reachable_but_onvif_failed", f"ONVIF HTTP {response.status} on port {port}"
    if "<" not in payload:
        return False, "http_reachable_but_onvif_failed", f"ONVIF endpoint on port {port} did not return SOAP/XML"
    if "fault" in payload.lower() and "not authorized" in payload.lower():
        return False, "onvif_auth_failed", f"ONVIF authentication rejected on port {port}"
    return True, "ok", sanitize_text(payload, camera.secrets())


def _request_profiles(camera: CameraConfig, media_url: str, timeout_seconds: float) -> tuple[bool, str, str]:
    parsed = urlparse(media_url)
    if parsed.scheme != "http" or not parsed.hostname:
        return False, "unknown", "ONVIF media URL is not an HTTP URL"
    port = parsed.port or 80
    path = parsed.path or "/onvif/Media"
    return _soap_request(camera, port, path, _media_profiles_body(camera), timeout_seconds)


def _device_capabilities_body(camera: CameraConfig) -> str:
    return _soap_envelope(
        camera,
        """
        <tds:GetCapabilities xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
          <tds:Category>All</tds:Category>
        </tds:GetCapabilities>
        """,
    )


def _media_profiles_body(camera: CameraConfig) -> str:
    return _soap_envelope(
        camera,
        """
        <trt:GetProfiles xmlns:trt="http://www.onvif.org/ver10/media/wsdl" />
        """,
    )


def _soap_envelope(camera: CameraConfig, body: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
  <s:Header>
    {_wsse_header(camera)}
  </s:Header>
  <s:Body>
    {body}
  </s:Body>
</s:Envelope>"""


def _wsse_header(camera: CameraConfig) -> str:
    if not camera.onvif_username:
        return ""

    nonce = os.urandom(16)
    created = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    digest = base64.b64encode(
        hashlib.sha1(nonce + created.encode("utf-8") + camera.onvif_password.encode("utf-8")).digest()
    ).decode("ascii")
    nonce64 = base64.b64encode(nonce).decode("ascii")

    return f"""
    <wsse:Security
      xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
      xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
      <wsse:UsernameToken>
        <wsse:Username>{_xml_escape(camera.onvif_username)}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</wsse:Password>
        <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce64}</wsse:Nonce>
        <wsu:Created>{created}</wsu:Created>
      </wsse:UsernameToken>
    </wsse:Security>
    """


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _find_first_xaddr(xml_text: str, needle: str) -> str | None:
    lower = xml_text.lower()
    needle_index = lower.find(needle.lower())
    search_from = max(0, needle_index - 500) if needle_index != -1 else 0
    xaddr_index = lower.find("xaddr", search_from)
    if xaddr_index == -1:
        return None
    start = lower.find("http://", xaddr_index)
    if start == -1:
        return None
    end_candidates = [
        index
        for index in (
            xml_text.find("<", start),
            xml_text.find("&lt;", start),
            xml_text.find('"', start),
            xml_text.find("'", start),
        )
        if index != -1
    ]
    end = min(end_candidates) if end_candidates else len(xml_text)
    return xml_text[start:end].strip()
