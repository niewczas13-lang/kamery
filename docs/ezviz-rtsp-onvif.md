# EZVIZ RTSP and ONVIF Notes

Do not assume every EZVIZ model exposes the same local features. The project
should detect features per camera and store the result.

## Known models to test

- `CS-H9c-R100-8G55WKFL`: dual-lens camera. Treat as one physical camera with
  possible lens 1 and lens 2 streams.
- `CS-C8c-R100-1J5WKFL`: common PT-style camera, but PTZ must still be detected.
- `CS-C8W`: PT camera candidate; verify RTSP, ONVIF, PTZ, and audio by probe.

## Candidate RTSP paths

- `/ch1/main`
- `/ch1/sub`
- `/Streaming/Channels/101`
- `/Streaming/Channels/102`
- `/Streaming/Channels/201`
- `/Streaming/Channels/202`

Suggested stream names for later go2rtc generation:

- `lukow_h9c_01_main`
- `lukow_h9c_01_sub`
- `lukow_h9c_01_lens2_main`
- `lukow_h9c_01_lens2_sub`
- `radom_c8c_01_main`
- `radom_c8c_01_sub`

## Network rule

RTSP and ONVIF stay private. Remote sites should connect through WireGuard,
Tailscale subnet routing, or another private tunnel. Only the future HTTPS panel
should be exposed remotely.
