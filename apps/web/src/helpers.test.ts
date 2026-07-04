import { describe, expect, it } from "vitest";
import { t, viewLabel } from "./i18n/pl";
import { frigateHealthLabel, nvrEventCountLabel, recordingPolicyError, sanitizeNvrUrl } from "./nvr";
import {
  buildOperatorTiles,
  defaultSavedLayouts,
  orderedTileIdsForLayout,
  selectTileStream,
  tileFallbackNotice,
  visibleTileIdsForLayout
} from "./liveTiles";
import {
  createSavedLayoutFromTiles,
  displayNameForTile,
  playerAudioPolicy,
  ptzTargetLensLabel,
  sanitizeDisplayName,
  sanitizeSavedLayouts
} from "./operatorPreferences";
import {
  defaultPtzDurationMs,
  ptzCommandAllowed,
  ptzControlsForCamera,
  ptzStatusMessage,
  sanitizePtzUiText
} from "./ptz";
import {
  buildGo2RtcPlayerUrl,
  isDefaultSmokeStream,
  preferredSmokeStreamNames,
  qualityLabel,
  qualityRoleForStream,
  selectStreamForSurface,
  streamLensRole
} from "./streamLinks";
import {
  activePreviewLimitCount,
  buildLiveTilePlayerIdentity,
  effectivePreviewProfile,
  operatorWallDefaults,
  streamStabilityStatus,
  tilePreviewLoadState
} from "./streamStability";
import { cameraStatusBadge } from "./status";
import type { Stream } from "./types";
import type { Camera, RecordingPolicy } from "./types";

describe("stream links", () => {
  it("builds go2rtc player URLs from stream names only", () => {
    const url = buildGo2RtcPlayerUrl("http://127.0.0.1:1984", "lukow_h9c_98_sub");

    expect(url).toBe("http://127.0.0.1:1984/stream.html?src=lukow_h9c_98_sub");
    expect(url).not.toContain("rtsp://");
    expect(url).not.toContain("@");
  });

  it("builds video-only go2rtc URLs for muted wall players", () => {
    const url = buildGo2RtcPlayerUrl("http://127.0.0.1:1984", "lukow_h9c_98_sub", { audio: "off" });

    expect(url).toBe("http://127.0.0.1:1984/stream.html?src=lukow_h9c_98_sub&media=video&muted=1");
    expect(url).not.toContain("mode=mjpeg");
    expect(url).not.toContain("rtsp://");
    expect(url).not.toContain("@");
  });

  it("can force the go2rtc MSE player with MJPEG fallback for stable HEVC wall playback", () => {
    const url = buildGo2RtcPlayerUrl("http://127.0.0.1:1984", "lukow_h9c_98_sub", {
      audio: "off",
      mode: "mse,mjpeg"
    });
    const parsed = new URL(url);

    expect(parsed.searchParams.get("mode")).toBe("mse,mjpeg");
    expect(parsed.searchParams.get("media")).toBe("video");
    expect(url).not.toContain("rtsp://");
    expect(url).not.toContain("@");
  });

  it("defaults live smoke to substreams", () => {
    expect(preferredSmokeStreamNames).toEqual([
      "lukow_h9c_98_sub",
      "lukow_h9c_98_lens2_sub",
      "lukow_c8w_97_sub"
    ]);
    expect(isDefaultSmokeStream("lukow_h9c_98_main")).toBe(false);
    expect(isDefaultSmokeStream("lukow_c8c_60_sub")).toBe(false);
  });

  it("maps stream quality roles to Polish labels", () => {
    expect(qualityRoleForStream(stream("lukow_h9c_98_main", "main"))).toBe("main");
    expect(qualityRoleForStream(stream("lukow_h9c_98_sub", "sub"))).toBe("sub");
    expect(qualityLabel("main")).toBe("Wysoka");
    expect(qualityLabel("sub")).toBe("Szybka");
  });

  it("auto profile chooses substream for grid and main stream for focus", () => {
    const streams = [stream("lukow_h9c_98_main", "main"), stream("lukow_h9c_98_sub", "sub")];

    expect(selectStreamForSurface(streams, { profile: "auto", surface: "grid" })?.stream_name).toBe("lukow_h9c_98_sub");
    expect(selectStreamForSurface(streams, { profile: "auto", surface: "focus" })?.stream_name).toBe("lukow_h9c_98_main");
  });

  it("selects H9C lens2 main for focus and substreams for split view", () => {
    const streams = [
      stream("lukow_h9c_98_main", "main"),
      stream("lukow_h9c_98_sub", "sub"),
      stream("lukow_h9c_98_lens2_main", "lens2_main"),
      stream("lukow_h9c_98_lens2_sub", "lens2_sub")
    ];

    expect(selectStreamForSurface(streams, { profile: "auto", surface: "focus", lens: "lens2" })?.stream_name).toBe(
      "lukow_h9c_98_lens2_main"
    );
    expect(
      streams
        .filter((item) => streamLensRole(item) === "lens1" || streamLensRole(item) === "lens2")
        .filter((item) => qualityRoleForStream(item) === "sub")
        .map((item) => item.stream_name)
    ).toEqual(["lukow_h9c_98_sub", "lukow_h9c_98_lens2_sub"]);
  });
});

describe("camera badges", () => {
  it("prioritizes unstable cameras", () => {
    expect(
      cameraStatusBadge({
        video_status: "ok",
        probe_status: "partial",
        reliability_status: "unstable"
      })
    ).toEqual({ label: "Niestabilna", tone: "warn" });
  });

  it("maps healthy video to a clear badge", () => {
    expect(
      cameraStatusBadge({
        video_status: "ok",
        probe_status: "ok",
        reliability_status: "stable"
      })
    ).toEqual({ label: "Obraz OK", tone: "good" });
  });
});

describe("ptz helpers", () => {
  it("renders PTZ buttons only for cameras with has_ptz=true", () => {
    expect(ptzControlsForCamera({ has_ptz: false })).toEqual([]);
    expect(ptzControlsForCamera({ has_ptz: true }).map((control) => control.command)).toContain("stop");
  });

  it("maps PTZ success and error states to user-facing statuses", () => {
    expect(defaultPtzDurationMs()).toBe(300);
    expect(ptzControlsForCamera({ has_ptz: true }).find((control) => control.command === "stop")?.label).toBe("Stop");
    expect(ptzStatusMessage({ state: "stopped", command: "left" })).toBe("Zatrzymano po ruchu: lewo");
    expect(ptzStatusMessage({ state: "failed", message: "PTZ not supported or not detected" })).toBe(
      "PTZ niedostępne albo niewykryte"
    );
  });

  it("blocks PTZ movement by default but keeps emergency stop allowed", () => {
    expect(ptzCommandAllowed("left", false)).toBe(false);
    expect(ptzCommandAllowed("zoom_in", false)).toBe(false);
    expect(ptzCommandAllowed("stop", false)).toBe(true);
    expect(ptzCommandAllowed("left", true)).toBe(true);
  });

  it("sanitizes sensitive PTZ UI text defensively", () => {
    const text = sanitizePtzUiText("failed rtsp://admin:secret-h9c@10.20.1.98:554/path");

    expect(text).toContain("rtsp://admin:***@");
    expect(text).not.toContain("secret-h9c");
  });
});

describe("nvr helpers", () => {
  it("maps Frigate health states", () => {
    expect(frigateHealthLabel({ reachable: true })).toEqual({ label: "Frigate działa", tone: "good" });
    expect(frigateHealthLabel({ reachable: false, error: "offline" })).toEqual({ label: "Frigate offline", tone: "warn" });
  });

  it("renders empty event counts without crashing", () => {
    expect(nvrEventCountLabel({ reachable: false, events: null })).toBe("niedostępne");
    expect(nvrEventCountLabel({ reachable: true, events: [] })).toBe("0 zdarzeń");
  });

  it("validates recording policy form values", () => {
    expect(recordingPolicyError({ mode: "events_only", retention_days: 2 })).toBe("");
    expect(recordingPolicyError({ mode: "events_only", retention_days: 0 })).toContain("Retencja");
    expect(recordingPolicyError({ mode: "forever", retention_days: 2 })).toContain("tryb");
  });

  it("sanitizes NVR URLs defensively", () => {
    const url = sanitizeNvrUrl("rtsp://admin:secret-h9c@10.20.1.98:554/path");

    expect(url).toContain("rtsp://admin:***@");
    expect(url).not.toContain("secret-h9c");
  });
});

describe("Polish UI labels", () => {
  it("keeps the main menu in Polish", () => {
    expect(["dashboard", "live", "cameras", "streams", "events", "recordings", "diagnostics", "settings"].map(viewLabel)).toEqual([
      "Pulpit",
      "Konsola podglądu",
      "Kamery",
      "Strumienie",
      "Zdarzenia",
      "Nagrania",
      "Diagnostyka",
      "Ustawienia"
    ]);
  });

  it("translates important empty and error states", () => {
    expect(t("events.emptyTitle")).toBe("Brak zdarzeń");
    expect(t("common.loading")).toBe("Ładowanie");
    expect(t("common.error")).toBe("Błąd");
    expect(t("ptz.disabled")).toBe("PTZ niedostępne");
  });
});

describe("operator live wall tiles", () => {
  const cameras = [
    camera(1, "lukow_h9c_98", "H9C 98", { has_ptz: true }),
    camera(2, "lukow_c8w_97", "C8W 97"),
    camera(3, "lukow_h8_101", "H8 101", { video_status: "unavailable" })
  ];
  const policies = new Map<string, RecordingPolicy>([
    ["lukow_h9c_98", policy("lukow_h9c_98", true)],
    ["lukow_c8w_97", policy("lukow_c8w_97", false)]
  ]);
  const streams = [
    streamFor(1, "lukow_h9c_98_main", "main", "2880x1620"),
    streamFor(1, "lukow_h9c_98_sub", "sub", "768x432"),
    streamFor(1, "lukow_h9c_98_lens2_main", "lens2_main", "2560x1440"),
    streamFor(1, "lukow_h9c_98_lens2_sub", "lens2_sub", "640x360"),
    streamFor(2, "lukow_c8w_97_sub", "sub", "768x432")
  ];

  it("renders H9C as two logical preview windows when dual-lens split is enabled", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });

    expect(result.tiles.map((tile) => tile.tile_id)).toEqual(["lukow_h9c_98:lens1", "lukow_h9c_98:lens2", "lukow_c8w_97:single"]);
    expect(result.tiles[0]).toMatchObject({
      title: "H9C 98 - Obiektyw 1",
      physical_device_title: "H9C 98",
      fast_stream_name: "lukow_h9c_98_sub",
      high_stream_name: "lukow_h9c_98_main",
      default_stream_name: "lukow_h9c_98_sub",
      focus_stream_name: "lukow_h9c_98_main"
    });
    expect(result.tiles[1]).toMatchObject({
      title: "H9C 98 - Obiektyw 2",
      fast_stream_name: "lukow_h9c_98_lens2_sub",
      high_stream_name: "lukow_h9c_98_lens2_main"
    });
  });

  it("keeps both H9C lenses first even when backend camera order differs", () => {
    const result = buildOperatorTiles([...cameras].reverse(), streams, policies, { separateLenses: true, showNoVideoInGrid: false });

    expect(result.tiles.map((tile) => tile.tile_id)).toEqual(["lukow_h9c_98:lens1", "lukow_h9c_98:lens2", "lukow_c8w_97:single"]);
  });

  it("keeps no-video cameras outside the main grid by default", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });

    expect(result.tiles.some((tile) => tile.camera_slug === "lukow_h8_101")).toBe(false);
    expect(result.noVideoCameras.map((item) => item.slug)).toEqual(["lukow_h8_101"]);
  });

  it("uses global quality rules without per-tile quality overrides", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });
    const lens1 = result.tiles.find((tile) => tile.tile_id === "lukow_h9c_98:lens1")!;
    const c8w = result.tiles.find((tile) => tile.tile_id === "lukow_c8w_97:single")!;

    expect(selectTileStream(lens1, "auto", "grid")?.stream_name).toBe("lukow_h9c_98_sub");
    expect(selectTileStream(lens1, "auto", "focus")?.stream_name).toBe("lukow_h9c_98_main");
    expect(selectTileStream(lens1, "high", "grid")?.stream_name).toBe("lukow_h9c_98_main");
    expect(selectTileStream(c8w, "high", "grid")?.stream_name).toBe("lukow_c8w_97_sub");
    expect(tileFallbackNotice(c8w, "high")).toBe("Brak strumienia wysokiej jakości. Używam szybkiego podglądu.");
  });

  it("stores simple local layouts as tile ids without stream URLs", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });
    const layouts = defaultSavedLayouts(result.tiles);

    expect(layouts.map((layout) => layout.name)).toContain("H9C podwójny");
    expect(visibleTileIdsForLayout(layouts[0], result.tiles)).toContain("lukow_h9c_98:lens1");
    expect(JSON.stringify(layouts)).not.toContain("rtsp://");
    expect(JSON.stringify(layouts)).not.toContain("@");
  });

  it("keeps hidden tiles editable in layout order", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });
    const layout = {
      ...defaultSavedLayouts(result.tiles)[0],
      hiddenTileIds: ["lukow_h9c_98:lens2"]
    };

    expect(visibleTileIdsForLayout(layout, result.tiles)).toEqual(["lukow_h9c_98:lens1", "lukow_c8w_97:single"]);
    expect(orderedTileIdsForLayout(layout, result.tiles)).toEqual([
      "lukow_h9c_98:lens1",
      "lukow_h9c_98:lens2",
      "lukow_c8w_97:single"
    ]);
  });

  it("keeps C8C 102 experimental tiles out of the default wall but available in unstable diagnostics", () => {
    const experimentalCamera = camera(102, "lukow_c8c_102", "C8C 102", { reliability_status: "unstable" });
    const experimentalStream = streamFor(102, "lukow_c8c_102_main_experimental", "main_experimental", "2880x1620");

    const defaultResult = buildOperatorTiles([...cameras, experimentalCamera], [...streams, experimentalStream], policies, {
      separateLenses: true,
      showNoVideoInGrid: false,
      statusFilter: "all"
    });
    const unstableResult = buildOperatorTiles([...cameras, experimentalCamera], [...streams, experimentalStream], policies, {
      separateLenses: true,
      showNoVideoInGrid: false,
      statusFilter: "unstable"
    });

    expect(defaultResult.tiles.map((tile) => tile.camera_slug)).not.toContain("lukow_c8c_102");
    expect(unstableResult.tiles.map((tile) => tile.camera_slug)).toContain("lukow_c8c_102");
  });
});

describe("operator preferences", () => {
  const cameras = [
    camera(1, "lukow_h9c_98", "H9C 98", { has_ptz: true }),
    camera(2, "lukow_c8w_97", "C8W 97")
  ];
  const streams = [
    streamFor(1, "lukow_h9c_98_main", "main", "2880x1620"),
    streamFor(1, "lukow_h9c_98_sub", "sub", "768x432"),
    streamFor(1, "lukow_h9c_98_lens2_main", "lens2_main", "2560x1440"),
    streamFor(1, "lukow_h9c_98_lens2_sub", "lens2_sub", "640x360"),
    streamFor(2, "lukow_c8w_97_sub", "sub", "768x432")
  ];
  const policies = new Map<string, RecordingPolicy>([
    ["lukow_h9c_98", policy("lukow_h9c_98", true)],
    ["lukow_c8w_97", policy("lukow_c8w_97", false)]
  ]);

  it("maps friendly tile display names without mutating technical ids", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });
    const lens2 = result.tiles.find((tile) => tile.tile_id === "lukow_h9c_98:lens2")!;

    expect(
      displayNameForTile(lens2, {
        cameraDisplayNames: { lukow_h9c_98: "Magazyn" },
        tileDisplayNames: { "lukow_h9c_98:lens2": "H9C - obrotowy" }
      })
    ).toBe("H9C - obrotowy");
    expect(displayNameForTile(lens2, { cameraDisplayNames: { lukow_h9c_98: "Magazyn" }, tileDisplayNames: {} })).toBe(
      "Magazyn - Obiektyw 2"
    );
    expect(lens2.tile_id).toBe("lukow_h9c_98:lens2");
  });

  it("rejects unsafe display names before localStorage persistence", () => {
    expect(sanitizeDisplayName(" Plac ")).toBe("Plac");
    expect(sanitizeDisplayName("rtsp://admin:secret@192.168.80.98")).toBe("");
    expect(sanitizeDisplayName("admin:secret@host")).toBe("");
  });

  it("serializes custom layouts with UI preferences and without stream URLs", () => {
    const result = buildOperatorTiles(cameras, streams, policies, { separateLenses: true, showNoVideoInGrid: false });
    const saved = createSavedLayoutFromTiles({
      id: "custom-test",
      name: "Własny",
      tiles: result.tiles,
      hiddenTileIds: ["lukow_h9c_98:lens2"],
      layoutSize: "4",
      qualityMode: "fast",
      separateLenses: true
    });

    expect(saved.tileIds).toEqual(["lukow_h9c_98:lens1", "lukow_h9c_98:lens2", "lukow_c8w_97:single"]);
    expect(saved.hiddenTileIds).toEqual(["lukow_h9c_98:lens2"]);
    expect(saved.layoutSize).toBe("4");
    expect(saved.qualityMode).toBe("fast");
    expect(saved.separateLenses).toBe(true);
    expect(JSON.stringify(saved)).not.toContain("rtsp://");
    expect(JSON.stringify(saved)).not.toContain("@");
  });

  it("drops unsafe saved layouts loaded from localStorage", () => {
    const layouts = sanitizeSavedLayouts([
      {
        id: "custom-ok",
        name: "Własny",
        tileIds: ["lukow_h9c_98:lens1"],
        hiddenTileIds: []
      },
      {
        id: "bad",
        name: "rtsp://admin:secret@host",
        tileIds: ["rtsp://admin:secret@host"],
        hiddenTileIds: []
      }
    ]);

    expect(layouts.map((layout) => layout.id)).toEqual(["custom-ok"]);
    expect(JSON.stringify(layouts)).not.toContain("secret");
  });

  it("keeps wall, monitor and inactive split streams muted", () => {
    expect(playerAudioPolicy({ surface: "grid", hasAudio: true, requestedAudio: true })).toMatchObject({
      enabled: false,
      playerAudio: "off"
    });
    expect(playerAudioPolicy({ surface: "monitor", hasAudio: true, requestedAudio: true })).toMatchObject({
      enabled: false,
      playerAudio: "off"
    });
    expect(playerAudioPolicy({ surface: "split", hasAudio: true, requestedAudio: true, active: false })).toMatchObject({
      enabled: false,
      playerAudio: "off"
    });
  });

  it("allows audio only for the active focus player after a manual request", () => {
    expect(playerAudioPolicy({ surface: "focus", hasAudio: true, requestedAudio: false })).toMatchObject({
      enabled: false,
      canEnable: true,
      label: "Dźwięk wyłączony"
    });
    expect(playerAudioPolicy({ surface: "focus", hasAudio: true, requestedAudio: true })).toMatchObject({
      enabled: true,
      canEnable: true,
      playerAudio: "on",
      label: "Dźwięk włączony"
    });
  });

  it("marks cameras without audio as unavailable", () => {
    expect(playerAudioPolicy({ surface: "focus", hasAudio: false, requestedAudio: true })).toMatchObject({
      enabled: false,
      canEnable: false,
      label: "Dźwięk niedostępny"
    });
  });

  it("labels H9C PTZ target lens without assuming the physical lens", () => {
    expect(ptzTargetLensLabel("lens1")).toBe("Obiektyw 1");
    expect(ptzTargetLensLabel("lens2")).toBe("Obiektyw 2");
    expect(ptzTargetLensLabel("unknown")).toBe("Nie wiem / do sprawdzenia");
  });
});

describe("stream stability helpers", () => {
  it("keeps the operator wall locked to stable muted defaults", () => {
    expect(operatorWallDefaults.previewProfile).toBe("fast");
    expect(operatorWallDefaults.activePreviewLimit).toBe("6");
    expect(operatorWallDefaults.separateLenses).toBe(true);
    expect(operatorWallDefaults.showNoVideoInGrid).toBe(false);
    expect(operatorWallDefaults.statusFilter).toBe("all");
    expect(operatorWallDefaults.showEventDrawer).toBe(false);
    expect(operatorWallDefaults.audio).toBe("off");
  });

  it("keeps tile keys stable and changes player src only for stream, audio or retry token", () => {
    const first = buildLiveTilePlayerIdentity({
      baseUrl: "http://127.0.0.1:1984",
      tileId: "lukow_h9c_98:lens1",
      streamName: "lukow_h9c_98_sub",
      audio: "off",
      reloadToken: 0
    });
    const afterPolling = buildLiveTilePlayerIdentity({
      baseUrl: "http://127.0.0.1:1984",
      tileId: "lukow_h9c_98:lens1",
      streamName: "lukow_h9c_98_sub",
      audio: "off",
      reloadToken: 0
    });
    const afterRetry = buildLiveTilePlayerIdentity({
      baseUrl: "http://127.0.0.1:1984",
      tileId: "lukow_h9c_98:lens1",
      streamName: "lukow_h9c_98_sub",
      audio: "off",
      reloadToken: 1
    });

    expect(first.key).toBe("lukow_h9c_98:lens1");
    expect(afterPolling.src).toBe(first.src);
    expect(afterRetry.src).not.toBe(first.src);
    expect(first.src).not.toContain("rtsp://");
    expect(first.src).not.toContain("@");
  });

  it("uses MSE plus MJPEG fallback for live wall iframe players by default", () => {
    const identity = buildLiveTilePlayerIdentity({
      baseUrl: "http://127.0.0.1:1984",
      tileId: "lukow_c8w_97:single",
      streamName: "lukow_c8w_97_sub",
      audio: "off",
      reloadToken: 0
    });
    const parsed = new URL(identity.src);

    expect(parsed.searchParams.get("mode")).toBe("mse,mjpeg");
    expect(parsed.searchParams.get("media")).toBe("video");
    expect(parsed.searchParams.get("muted")).toBe("1");
  });

  it("limits active grid previews and lets an over-limit tile load manually", () => {
    expect(activePreviewLimitCount("4")).toBe(4);
    expect(tilePreviewLoadState({ index: 0, limit: "4", manuallyLoaded: false })).toMatchObject({
      active: true,
      paused: false,
      overActiveLimit: false
    });
    expect(tilePreviewLoadState({ index: 4, limit: "4", manuallyLoaded: false })).toMatchObject({
      active: false,
      paused: true,
      overActiveLimit: true
    });
    expect(tilePreviewLoadState({ index: 4, limit: "4", manuallyLoaded: true })).toMatchObject({
      active: true,
      paused: false,
      overActiveLimit: true
    });
  });

  it("uses fast quality and a small active limit in eco mode", () => {
    expect(effectivePreviewProfile("high", true)).toBe("fast");
    expect(tilePreviewLoadState({ index: 2, limit: "9", manuallyLoaded: false, ecoMode: true })).toMatchObject({
      active: false,
      paused: true,
      effectiveLimit: "2"
    });
  });

  it("maps known stream stability statuses without exposing secrets", () => {
    expect(streamStabilityStatus({ slug: "lukow_h9c_98", reliabilityStatus: "stable" })).toMatchObject({
      label: "stabilny",
      tone: "good"
    });
    expect(streamStabilityStatus({ slug: "lukow_c8c_60", reliabilityStatus: "degraded" })).toMatchObject({
      label: "obniżona stabilność",
      tone: "warn"
    });
    expect(streamStabilityStatus({ slug: "lukow_c8c_102", reliabilityStatus: "unstable" })).toMatchObject({
      label: "eksperymentalny",
      tone: "bad"
    });
  });
});

function stream(stream_name: string, stream_role: string): Stream {
  return {
    stream_name,
    camera_id: 1,
    camera_name: "H9C 98",
    location_id: 1,
    stream_role,
    path: "/Streaming/Channels/101",
    video_codec: "hevc",
    audio_codec: "aac",
    resolution: stream_role.includes("main") ? "2880x1620" : "768x432",
    fps: 15,
    has_audio: true,
    playback_status: "needs_transcode",
    warnings: [],
    quality_role: stream_role.includes("main") ? "main" : "sub",
    quality_label: stream_role.includes("main") ? "Wysoka" : "Szybka",
    is_recommended_for_grid: stream_role.includes("sub"),
    is_recommended_for_focus: stream_role.includes("main"),
    is_recommended_for_recording: stream_role.includes("main"),
    is_recommended_for_detection: stream_role.includes("sub")
  };
}

function camera(id: number, slug: string, name: string, overrides: Partial<Camera> = {}): Camera {
  return {
    id,
    location_id: 1,
    name,
    slug,
    model: "CS-test",
    host: `192.168.80.${id}`,
    video_status: "ok",
    control_status: "ptz_ok",
    probe_status: "ok",
    reliability_status: "stable",
    has_audio: true,
    has_ptz: false,
    has_onvif: true,
    has_snapshot: false,
    has_two_way_audio_candidate: false,
    enabled: true,
    ...overrides
  };
}

function streamFor(camera_id: number, stream_name: string, stream_role: string, resolution: string): Stream {
  return {
    ...stream(stream_name, stream_role),
    camera_id,
    camera_name: camera_id === 1 ? "H9C 98" : "C8W 97",
    resolution
  };
}

function policy(camera_slug: string, enabled: boolean): RecordingPolicy {
  return {
    camera_id: camera_slug === "lukow_h9c_98" ? 1 : 2,
    camera_name: camera_slug,
    camera_slug,
    mode: enabled ? "events_only" : "disabled",
    retention_days: 1,
    record_main_stream: enabled,
    detect_sub_stream: enabled,
    enabled
  };
}
