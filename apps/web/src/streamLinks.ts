import type { Stream } from "./types";

export const preferredSmokeStreamNames = [
  "lukow_h9c_98_sub",
  "lukow_h9c_98_lens2_sub",
  "lukow_c8w_97_sub"
];

export type Go2RtcPlaybackMode = "auto" | "mse,mjpeg" | "mse" | "webrtc" | "webrtc/tcp" | "mjpeg";
export type PreviewProfile = "auto" | "fast" | "high";
export type StreamSurface = "grid" | "focus" | "fullscreen" | "split";
export type StreamLens = "lens1" | "lens2" | "unknown";
export type QualityRole = "main" | "sub" | "unknown";

export function buildGo2RtcPlayerUrl(
  baseUrl: string,
  streamName: string,
  options: { audio?: "off" | "on"; mode?: Go2RtcPlaybackMode } = {}
): string {
  const url = new URL("stream.html", ensureTrailingSlash(baseUrl));
  url.searchParams.set("src", streamName);
  const audio = options.audio || "off";
  if (audio === "off") {
    url.searchParams.set("media", "video");
    url.searchParams.set("muted", "1");
  } else if (audio === "on") {
    url.searchParams.set("media", "video,audio");
    url.searchParams.set("muted", "0");
  }
  if (options.mode && options.mode !== "auto") {
    url.searchParams.set("mode", options.mode);
  }
  return url.toString();
}

export function isDefaultSmokeStream(streamName: string): boolean {
  return preferredSmokeStreamNames.includes(streamName);
}

export function qualityRoleForStream(stream: Pick<Stream, "quality_role" | "stream_role" | "stream_name">): QualityRole {
  if (stream.quality_role) {
    return stream.quality_role;
  }
  const value = `${stream.stream_role} ${stream.stream_name}`.toLowerCase();
  if (value.includes("main")) {
    return "main";
  }
  if (value.includes("sub")) {
    return "sub";
  }
  return "unknown";
}

export function qualityLabel(role: QualityRole): string {
  if (role === "main") {
    return "Wysoka";
  }
  if (role === "sub") {
    return "Szybka";
  }
  return "Nieznana";
}

export function streamLensRole(stream: Pick<Stream, "stream_role" | "stream_name">): StreamLens {
  const value = `${stream.stream_role} ${stream.stream_name}`.toLowerCase();
  if (value.includes("lens2")) {
    return "lens2";
  }
  if (value.includes("lens1") || value.includes("main") || value.includes("sub")) {
    return "lens1";
  }
  return "unknown";
}

export function selectStreamForSurface(
  streams: Stream[],
  options: { profile: PreviewProfile; surface: StreamSurface; lens?: StreamLens }
): Stream | undefined {
  const lens = options.lens || "lens1";
  const candidates = streams.filter((stream) => streamLensRole(stream) === lens || lens === "unknown");
  const scoped = candidates.length ? candidates : streams;
  const wantedQuality = qualityForProfile(options.profile, options.surface);
  return (
    scoped.find((stream) => qualityRoleForStream(stream) === wantedQuality) ||
    scoped.find((stream) => qualityRoleForStream(stream) === "sub") ||
    scoped.find((stream) => qualityRoleForStream(stream) === "main") ||
    scoped[0]
  );
}

export function qualityForProfile(profile: PreviewProfile, surface: StreamSurface): QualityRole {
  if (profile === "fast") {
    return "sub";
  }
  if (profile === "high") {
    return "main";
  }
  return surface === "grid" || surface === "split" ? "sub" : "main";
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith("/") ? value : `${value}/`;
}
