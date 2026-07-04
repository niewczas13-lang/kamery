import { buildGo2RtcPlayerUrl } from "./streamLinks";
import type { Go2RtcPlaybackMode, PreviewProfile } from "./streamLinks";

export type ActivePreviewLimit = "2" | "4" | "6" | "9" | "unlimited";
export type StreamStabilityLabel = "stabilny" | "obniżona stabilność" | "niestabilny" | "eksperymentalny";
export type StreamStabilityTone = "good" | "warn" | "bad";

export const stableWallPlaybackMode: Go2RtcPlaybackMode = "mse,mjpeg";
export const operatorWallDefaults = {
  previewProfile: "fast",
  activePreviewLimit: "6",
  separateLenses: true,
  showNoVideoInGrid: false,
  statusFilter: "all",
  showEventDrawer: false,
  audio: "off"
} as const;

export const activePreviewLimitOptions: { value: ActivePreviewLimit; label: string }[] = [
  { value: "2", label: "2" },
  { value: "4", label: "4" },
  { value: "6", label: "6" },
  { value: "9", label: "9" },
  { value: "unlimited", label: "bez limitu" }
];

export function buildLiveTilePlayerIdentity(options: {
  baseUrl: string;
  tileId: string;
  streamName?: string | null;
  audio: "off" | "on";
  reloadToken: number;
  mode?: Go2RtcPlaybackMode;
}): { key: string; src: string } {
  if (!options.streamName) {
    return { key: options.tileId, src: "" };
  }
  const url = new URL(
    buildGo2RtcPlayerUrl(options.baseUrl, options.streamName, {
      audio: options.audio,
      mode: options.mode || stableWallPlaybackMode
    })
  );
  if (options.reloadToken > 0) {
    url.searchParams.set("reload", String(options.reloadToken));
  }
  return { key: options.tileId, src: url.toString() };
}

export function activePreviewLimitCount(limit: ActivePreviewLimit): number {
  if (limit === "unlimited") {
    return Number.POSITIVE_INFINITY;
  }
  return Number(limit);
}

export function effectiveActivePreviewLimit(limit: ActivePreviewLimit, ecoMode: boolean): ActivePreviewLimit {
  return ecoMode ? "2" : limit;
}

export function effectivePreviewProfile(profile: PreviewProfile, ecoMode: boolean): PreviewProfile {
  return ecoMode ? "fast" : profile;
}

export function tilePreviewLoadState(options: {
  index: number;
  limit: ActivePreviewLimit;
  manuallyLoaded: boolean;
  ecoMode?: boolean;
}): { active: boolean; paused: boolean; overActiveLimit: boolean; effectiveLimit: ActivePreviewLimit } {
  const effectiveLimit = effectiveActivePreviewLimit(options.limit, Boolean(options.ecoMode));
  const limitCount = activePreviewLimitCount(effectiveLimit);
  const overActiveLimit = options.index >= limitCount;
  const active = !overActiveLimit || options.manuallyLoaded;
  return {
    active,
    paused: !active,
    overActiveLimit,
    effectiveLimit
  };
}

export function streamStabilityStatus(options: {
  slug: string;
  reliabilityStatus?: string | null;
}): { label: StreamStabilityLabel; tone: StreamStabilityTone; description: string } {
  const slug = options.slug.toLowerCase();
  const reliability = (options.reliabilityStatus || "").toLowerCase();
  if (slug.includes("c8c_102")) {
    return {
      label: "eksperymentalny",
      tone: "bad",
      description: "C8C 102 pozostaje poza domyślnym video wallem do czasu stabilnego SUB streamu."
    };
  }
  if (slug.includes("c8c_60")) {
    if (reliability === "unstable") {
      return {
        label: "niestabilny",
        tone: "bad",
        description: "C8C 60 jest poza domyslnym wall/NVR; direct RTSP wymaga stabilizacji linku albo kamery."
      };
    }
    return {
      label: "obniżona stabilność",
      tone: "warn",
      description: "C8C 60 nie startuje automatycznie w smoke wallu ani NVR; otwieraj ja recznie do testow."
    };
  }
  if (reliability === "unstable") {
    return {
      label: "niestabilny",
      tone: "bad",
      description: "Probe oznaczył kamerę jako niestabilną."
    };
  }
  if (reliability === "degraded") {
    return {
      label: "obniżona stabilność",
      tone: "warn",
      description: "Kamera działa, ale wcześniejsze probe albo usługi pomocnicze zgłaszały problemy."
    };
  }
  return {
    label: "stabilny",
    tone: "good",
    description: "Stream przeszedł bazowe testy i nadaje się do domyślnego podglądu."
  };
}
