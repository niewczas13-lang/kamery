# Storage Sizing

Stage 5A is intentionally conservative:

- short default retention,
- selected cameras only,
- no full 25-camera NVR,
- no mass HEVC transcoding,
- CPU detection only as a smoke-test path.

Current defaults:

- H9C lens1/lens2: 2-day event retention.
- C8W 97: 1-day event retention.
- C8C 60: disabled by default until direct RTSP is stable in the Lukow LAN.
- C8C 102 and H8 101: skipped.

Before enabling longer retention or all cameras, move Frigate media to a larger
disk and consider hardware acceleration or a Coral/GPU-class detector. HEVC/H.265
streams can reduce bandwidth/storage, but browser playback and detection CPU
costs may need an H.264 fallback/transcode design in a later stage.
