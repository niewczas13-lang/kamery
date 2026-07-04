import type { Camera } from "./types";

export type PtzCommand = "up" | "down" | "left" | "right" | "zoom_in" | "zoom_out" | "stop";

export type PtzControl = {
  command: PtzCommand;
  label: string;
};

export type PtzUiState =
  | { state: "idle" }
  | { state: "moving"; command: PtzCommand }
  | { state: "stopped"; command: PtzCommand }
  | { state: "failed"; message: string }
  | { state: "not_supported" };

const controls: PtzControl[] = [
  { command: "up", label: "Góra" },
  { command: "left", label: "Lewo" },
  { command: "right", label: "Prawo" },
  { command: "down", label: "Dół" },
  { command: "zoom_in", label: "Zoom +" },
  { command: "zoom_out", label: "Zoom -" },
  { command: "stop", label: "Stop" }
];

export function ptzControlsForCamera(camera: Pick<Camera, "has_ptz">): PtzControl[] {
  return camera.has_ptz ? controls : [];
}

export function defaultPtzDurationMs(): number {
  return 300;
}

export function ptzCommandAllowed(command: PtzCommand, controlsUnlocked: boolean): boolean {
  return controlsUnlocked || command === "stop";
}

export function ptzStatusMessage(status: PtzUiState): string {
  if (status.state === "idle") {
    return "";
  }
  if (status.state === "moving") {
    return `Ruch: ${commandLabel(status.command)}`;
  }
  if (status.state === "stopped") {
    return `Zatrzymano po ruchu: ${commandLabel(status.command)}`;
  }
  if (status.state === "not_supported") {
    return "PTZ niedostępne albo niewykryte";
  }
  return translateKnownPtzError(sanitizePtzUiText(status.message));
}

export function sanitizePtzUiText(value: string): string {
  return value.replace(/\b(rtsp|http|https):\/\/([^:\s/@]+):([^@\s]+)@/gi, "$1://$2:***@");
}

export function commandLabel(command: PtzCommand): string {
  return controls.find((control) => control.command === command)?.label.toLowerCase() || command;
}

function translateKnownPtzError(value: string): string {
  if (value.includes("PTZ not supported or not detected")) {
    return "PTZ niedostępne albo niewykryte";
  }
  if (value.includes("PTZ secret is not configured")) {
    return "Brak skonfigurowanego sekretu PTZ";
  }
  return value;
}
