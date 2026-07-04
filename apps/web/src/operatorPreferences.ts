import type { OperatorTile, SavedLiveLayout } from "./liveTiles";
import type { PreviewProfile } from "./streamLinks";

export type DisplayNameMaps = {
  cameraDisplayNames: Record<string, string>;
  tileDisplayNames: Record<string, string>;
};

export type PtzTargetLens = "lens1" | "lens2" | "unknown";
export type PlayerSurface = "grid" | "focus" | "split" | "mini" | "monitor" | "fullscreen";
export type PlayerAudioMode = "off" | "on";

export type PlayerAudioPolicy = {
  enabled: boolean;
  canEnable: boolean;
  playerAudio: PlayerAudioMode;
  label: string;
};

const unsafeValuePattern = /rtsp:\/\/|@/i;

export function sanitizeDisplayName(value: string): string {
  const trimmed = value.trim().replace(/\s+/g, " ").slice(0, 80);
  if (!trimmed || unsafeValuePattern.test(trimmed)) {
    return "";
  }
  return trimmed;
}

export function displayNameForTile(tile: OperatorTile, names: DisplayNameMaps): string {
  const tileName = sanitizeDisplayName(names.tileDisplayNames[tile.tile_id] || "");
  if (tileName) {
    return tileName;
  }
  const cameraName = sanitizeDisplayName(names.cameraDisplayNames[tile.camera_slug] || "") || tile.physical_device_title;
  if (tile.lens === "lens1") {
    return `${cameraName} - Obiektyw 1`;
  }
  if (tile.lens === "lens2") {
    return `${cameraName} - Obiektyw 2`;
  }
  return cameraName;
}

export function createSavedLayoutFromTiles(options: {
  id: string;
  name: string;
  tiles: OperatorTile[];
  hiddenTileIds: string[];
  layoutSize: string;
  qualityMode: PreviewProfile;
  separateLenses: boolean;
}): SavedLiveLayout {
  return {
    id: safeStorageValue(options.id) || `custom-${Date.now()}`,
    name: safeStorageValue(options.name) || "Własny układ",
    tileIds: options.tiles.map((tile) => tile.tile_id).filter(safeStorageString),
    hiddenTileIds: options.hiddenTileIds.filter(safeStorageString),
    layoutSize: safeStorageValue(options.layoutSize) || "custom",
    qualityMode: options.qualityMode,
    separateLenses: options.separateLenses
  };
}

export function sanitizeSavedLayouts(value: unknown): SavedLiveLayout[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") {
      return [];
    }
    const candidate = item as Partial<SavedLiveLayout>;
    if (
      typeof candidate.id !== "string" ||
      typeof candidate.name !== "string" ||
      !Array.isArray(candidate.tileIds) ||
      !Array.isArray(candidate.hiddenTileIds)
    ) {
      return [];
    }
    if (![candidate.id, candidate.name, ...candidate.tileIds, ...candidate.hiddenTileIds].every(safeStorageString)) {
      return [];
    }
    return [
      {
        id: candidate.id,
        name: candidate.name,
        tileIds: candidate.tileIds,
        hiddenTileIds: candidate.hiddenTileIds,
        layoutSize: safeStorageValue(candidate.layoutSize || "") || undefined,
        qualityMode: candidate.qualityMode,
        separateLenses: typeof candidate.separateLenses === "boolean" ? candidate.separateLenses : undefined
      }
    ];
  });
}

export function playerAudioPolicy(options: {
  surface: PlayerSurface;
  hasAudio: boolean;
  requestedAudio: boolean;
  active?: boolean;
}): PlayerAudioPolicy {
  if (!options.hasAudio) {
    return { enabled: false, canEnable: false, playerAudio: "off", label: "Dźwięk niedostępny" };
  }
  const wallSurface = ["grid", "monitor", "fullscreen", "mini"].includes(options.surface);
  const inactiveSplit = options.surface === "split" && options.active === false;
  if (wallSurface || inactiveSplit) {
    return { enabled: false, canEnable: false, playerAudio: "off", label: "Dźwięk wyłączony" };
  }
  if (!options.requestedAudio) {
    return { enabled: false, canEnable: true, playerAudio: "off", label: "Dźwięk wyłączony" };
  }
  return { enabled: true, canEnable: true, playerAudio: "on", label: "Dźwięk włączony" };
}

export function ptzTargetLensLabel(value: PtzTargetLens): string {
  if (value === "lens1") {
    return "Obiektyw 1";
  }
  if (value === "lens2") {
    return "Obiektyw 2";
  }
  return "Nie wiem / do sprawdzenia";
}

function safeStorageString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && !unsafeValuePattern.test(value);
}

function safeStorageValue(value: unknown): string {
  return safeStorageString(value) ? value : "";
}
