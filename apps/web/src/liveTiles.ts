import { qualityLabel, qualityRoleForStream, selectStreamForSurface, streamLensRole, type PreviewProfile, type StreamLens } from "./streamLinks";
import type { Camera, RecordingPolicy, Stream } from "./types";

export type TileLens = "single" | "lens1" | "lens2" | "combined";
export type TileStatusFilter = "all" | "online" | "ptz" | "recording" | "unstable" | "no_video";
export type TileSurface = "grid" | "focus" | "split";

export type OperatorTile = {
  tile_id: string;
  camera_id: number;
  camera_slug: string;
  title: string;
  physical_device_title: string;
  lens: TileLens;
  is_dual_lens: boolean;
  has_ptz: boolean;
  ptz_camera_id: number | null;
  fast_stream_name: string | null;
  high_stream_name: string | null;
  default_stream_name: string | null;
  focus_stream_name: string | null;
  fastStream?: Stream;
  highStream?: Stream;
  fallbackStream?: Stream;
  camera: Camera;
  policy: RecordingPolicy | null;
  badges: string[];
  quality: {
    fast_resolution: string | null;
    high_resolution: string | null;
    codec: string | null;
  };
};

export type NoVideoCamera = {
  id: number;
  slug: string;
  name: string;
  reason: string;
  camera: Camera;
};

export type OperatorTileResult = {
  tiles: OperatorTile[];
  noVideoCameras: NoVideoCamera[];
};

export type OperatorTileOptions = {
  separateLenses: boolean;
  showNoVideoInGrid: boolean;
  statusFilter?: TileStatusFilter;
};

export type SavedLiveLayout = {
  id: string;
  name: string;
  tileIds: string[];
  hiddenTileIds: string[];
  layoutSize?: string;
  qualityMode?: PreviewProfile;
  separateLenses?: boolean;
};

export function buildOperatorTiles(
  cameras: Camera[],
  streams: Stream[],
  policiesBySlug: Map<string, RecordingPolicy>,
  options: OperatorTileOptions
): OperatorTileResult {
  const tiles: OperatorTile[] = [];
  const noVideoCameras: NoVideoCamera[] = [];
  for (const camera of cameras) {
    const cameraStreams = streams.filter((stream) => stream.camera_id === camera.id);
    const policy = policiesBySlug.get(camera.slug) || null;
    const noVideo = cameraHasNoVideo(camera, cameraStreams);
    if (noVideo) {
      const item = noVideoCamera(camera, cameraStreams);
      noVideoCameras.push(item);
      if (!options.showNoVideoInGrid) {
        continue;
      }
      tiles.push(placeholderTile(camera, policy, item.reason));
      continue;
    }

    const hasLens2 = cameraStreams.some((stream) => streamLensRole(stream) === "lens2");
    if (hasLens2 && options.separateLenses) {
      tiles.push(makeTile(camera, cameraStreams, policy, "lens1"));
      tiles.push(makeTile(camera, cameraStreams, policy, "lens2"));
    } else {
      tiles.push(makeTile(camera, cameraStreams, policy, hasLens2 ? "combined" : "single"));
    }
  }
  return {
    tiles: tiles.filter((tile) => matchesStatusFilter(tile, options.statusFilter || "all")),
    noVideoCameras
  };
}

export function selectTileStream(tile: OperatorTile, profile: PreviewProfile, surface: TileSurface): Stream | undefined {
  if (profile === "fast") {
    return tile.fastStream || tile.fallbackStream || tile.highStream;
  }
  if (profile === "high") {
    return tile.highStream || tile.fastStream || tile.fallbackStream;
  }
  if (surface === "grid" || surface === "split") {
    return tile.fastStream || tile.highStream || tile.fallbackStream;
  }
  return tile.highStream || tile.fastStream || tile.fallbackStream;
}

export function tileFallbackNotice(tile: OperatorTile, profile: PreviewProfile): string {
  if (profile === "high" && !tile.highStream && tile.fastStream) {
    return "Brak strumienia wysokiej jakości. Używam szybkiego podglądu.";
  }
  return "";
}

export function defaultSavedLayouts(tiles: OperatorTile[]): SavedLiveLayout[] {
  const allIds = tiles.map((tile) => tile.tile_id);
  const h9cIds = allIds.filter((id) => id.startsWith("lukow_h9c_98:"));
  const ptzIds = tiles.filter((tile) => tile.has_ptz).map((tile) => tile.tile_id);
  const recordingIds = tiles.filter((tile) => tile.policy?.enabled).map((tile) => tile.tile_id);
  return [
    { id: "all", name: "Wszystkie kamery", tileIds: allIds, hiddenTileIds: [] },
    { id: "h9c-dual", name: "H9C podwójny", tileIds: h9cIds.length ? h9cIds : allIds, hiddenTileIds: [] },
    { id: "ptz", name: "PTZ", tileIds: ptzIds.length ? ptzIds : allIds, hiddenTileIds: [] },
    { id: "nvr-events", name: "NVR / zdarzenia", tileIds: recordingIds.length ? recordingIds : allIds, hiddenTileIds: [] }
  ];
}

export function visibleTileIdsForLayout(layout: SavedLiveLayout, tiles: OperatorTile[]): string[] {
  const hidden = new Set(layout.hiddenTileIds);
  return orderedTileIdsForLayout(layout, tiles).filter((id) => !hidden.has(id));
}

export function orderedTileIdsForLayout(layout: SavedLiveLayout, tiles: OperatorTile[]): string[] {
  const known = new Set(tiles.map((tile) => tile.tile_id));
  const ordered = layout.tileIds.filter((id) => known.has(id));
  const missing = tiles.map((tile) => tile.tile_id).filter((id) => !layout.tileIds.includes(id));
  return [...ordered, ...missing];
}

function makeTile(camera: Camera, streams: Stream[], policy: RecordingPolicy | null, lens: TileLens): OperatorTile {
  const lensForStream: StreamLens = lens === "lens2" ? "lens2" : "lens1";
  const scoped = streams.filter((stream) => lens === "combined" || streamLensRole(stream) === lensForStream);
  const fastStream = scoped.find((stream) => qualityRoleForStream(stream) === "sub");
  const highStream = scoped.find((stream) => qualityRoleForStream(stream) === "main");
  const fallbackStream = fastStream || highStream || selectStreamForSurface(streams, { profile: "auto", surface: "grid", lens: lensForStream });
  const defaultStream = fastStream || fallbackStream || highStream;
  const focusStream = highStream || fastStream || fallbackStream;
  const dual = streams.some((stream) => streamLensRole(stream) === "lens2");
  return {
    tile_id: `${camera.slug}:${lens === "combined" || lens === "single" ? "single" : lens}`,
    camera_id: camera.id,
    camera_slug: camera.slug,
    title: tileTitle(camera, lens),
    physical_device_title: camera.name,
    lens,
    is_dual_lens: dual,
    has_ptz: camera.has_ptz,
    ptz_camera_id: camera.has_ptz ? camera.id : null,
    fast_stream_name: fastStream?.stream_name || null,
    high_stream_name: highStream?.stream_name || null,
    default_stream_name: defaultStream?.stream_name || null,
    focus_stream_name: focusStream?.stream_name || null,
    fastStream,
    highStream,
    fallbackStream,
    camera,
    policy,
    badges: tileBadges(camera, fallbackStream, policy),
    quality: {
      fast_resolution: fastStream?.resolution || null,
      high_resolution: highStream?.resolution || null,
      codec: (highStream?.video_codec || fastStream?.video_codec || fallbackStream?.video_codec || null)?.toUpperCase() || null
    }
  };
}

function placeholderTile(camera: Camera, policy: RecordingPolicy | null, reason: string): OperatorTile {
  return {
    tile_id: `${camera.slug}:no-video`,
    camera_id: camera.id,
    camera_slug: camera.slug,
    title: camera.name,
    physical_device_title: camera.name,
    lens: "single",
    is_dual_lens: false,
    has_ptz: camera.has_ptz,
    ptz_camera_id: camera.has_ptz ? camera.id : null,
    fast_stream_name: null,
    high_stream_name: null,
    default_stream_name: null,
    focus_stream_name: null,
    camera,
    policy,
    badges: ["BRAK OBRAZU", camera.reliability_status === "unstable" ? "NIESTABILNA" : ""].filter(Boolean),
    quality: { fast_resolution: null, high_resolution: null, codec: null },
    fallbackStream: undefined
  };
}

function tileTitle(camera: Camera, lens: TileLens): string {
  if (lens === "lens1") {
    return `${camera.name} - Obiektyw 1`;
  }
  if (lens === "lens2") {
    return `${camera.name} - Obiektyw 2`;
  }
  return camera.name;
}

function tileBadges(camera: Camera, stream: Stream | undefined, policy: RecordingPolicy | null): string[] {
  return [
    stream ? "LIVE" : "BRAK OBRAZU",
    policy?.enabled ? "REC" : "",
    camera.has_ptz ? "PTZ" : "",
    camera.has_audio || stream?.has_audio ? "AUDIO" : "",
    (stream?.video_codec || "").toLowerCase().includes("hevc") ? "HEVC" : "",
    camera.reliability_status === "unstable" ? "NIESTABILNA" : ""
  ].filter(Boolean);
}

function cameraHasNoVideo(camera: Camera, streams: Stream[]): boolean {
  return streams.length === 0 || ["failed", "unavailable"].includes(camera.video_status);
}

function noVideoCamera(camera: Camera, streams: Stream[]): NoVideoCamera {
  const reason = streams.length === 0 ? "brak strumienia" : camera.reliability_status === "unstable" ? "niestabilna" : "brak obrazu";
  return { id: camera.id, slug: camera.slug, name: camera.name, reason, camera };
}

function matchesStatusFilter(tile: OperatorTile, filter: TileStatusFilter): boolean {
  if (isExperimentalCamera(tile.camera) && filter !== "unstable") {
    return false;
  }
  if (filter === "all") {
    return true;
  }
  if (filter === "online") {
    return tile.camera.enabled && Boolean(tile.default_stream_name);
  }
  if (filter === "ptz") {
    return tile.has_ptz;
  }
  if (filter === "recording") {
    return Boolean(tile.policy?.enabled);
  }
  if (filter === "unstable") {
    return tile.camera.reliability_status === "unstable";
  }
  if (filter === "no_video") {
    return !tile.default_stream_name;
  }
  return true;
}

export function tileQualityText(tile: OperatorTile, stream: Stream | undefined): string {
  if (!stream) {
    return "Brak obrazu";
  }
  return `${qualityLabel(qualityRoleForStream(stream))} / ${stream.resolution || "-"} / ${stream.video_codec?.toUpperCase() || "-"}`;
}

function isExperimentalCamera(camera: Camera): boolean {
  return camera.slug.toLowerCase().includes("c8c_102") || camera.reliability_status === "experimental";
}
