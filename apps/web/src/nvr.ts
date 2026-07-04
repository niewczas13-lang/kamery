import type { BadgeTone } from "./status";

export type NvrHealthInput = {
  reachable: boolean;
  error?: string | null;
};

export type RecordingPolicyForm = {
  mode: string;
  retention_days: number;
};

const modes = ["disabled", "events_only", "continuous", "continuous_selected_hours"];

export function frigateHealthLabel(health: NvrHealthInput | null): { label: string; tone: BadgeTone } {
  if (!health) {
    return { label: "Frigate nieznany", tone: "muted" };
  }
  if (health.reachable) {
    return { label: "Frigate działa", tone: "good" };
  }
  return { label: "Frigate offline", tone: "warn" };
}

export function nvrEventCountLabel(payload: { reachable: boolean; events?: unknown[] | null } | null): string {
  if (!payload || !payload.reachable || !payload.events) {
    return "niedostępne";
  }
  if (payload.events.length === 1) {
    return "1 zdarzenie";
  }
  return `${payload.events.length} zdarzeń`;
}

export function recordingPolicyError(policy: RecordingPolicyForm): string {
  if (!modes.includes(policy.mode)) {
    return "Wybierz obsługiwany tryb nagrywania.";
  }
  if (!Number.isFinite(policy.retention_days) || policy.retention_days < 1 || policy.retention_days > 30) {
    return "Retencja musi mieć od 1 do 30 dni.";
  }
  return "";
}

export function sanitizeNvrUrl(value: string): string {
  return value.replace(/\b(rtsp|http|https):\/\/([^:\s/@]+):([^@\s]+)@/gi, "$1://$2:***@");
}
