import type { Camera } from "./types";

export type BadgeTone = "good" | "warn" | "bad" | "muted" | "info";

export type StatusBadge = {
  label: string;
  tone: BadgeTone;
};

export function cameraStatusBadge(camera: Pick<Camera, "video_status" | "probe_status" | "reliability_status">): StatusBadge {
  if (camera.reliability_status === "unstable") {
    return { label: "Niestabilna", tone: "warn" };
  }
  if (camera.video_status === "ok") {
    return { label: "Obraz OK", tone: "good" };
  }
  if (camera.video_status === "partial") {
    return { label: "Częściowo", tone: "info" };
  }
  if (camera.video_status === "failed" || camera.probe_status === "failed") {
    return { label: "Błąd", tone: "bad" };
  }
  if (camera.video_status === "unavailable") {
    return { label: "Brak obrazu", tone: "muted" };
  }
  return { label: "Nieznany", tone: "muted" };
}

export function apiErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return translateApiError(error.message);
  }
  return "Żądanie nie powiodło się";
}

function translateApiError(message: string): string {
  if (message.includes("Invalid username or password")) {
    return "Nieprawidłowy użytkownik albo hasło";
  }
  if (message.includes("Missing bearer token") || message.includes("Invalid token")) {
    return "Sesja wygasła albo brakuje tokenu";
  }
  if (message.includes("PTZ not supported or not detected")) {
    return "PTZ niedostępne albo niewykryte";
  }
  if (message.includes("PTZ secret is not configured")) {
    return "Brak skonfigurowanego sekretu PTZ";
  }
  if (message.includes("Camera has no video stream for snapshot")) {
    return "Kamera nie ma strumienia do zrzutu";
  }
  if (message.includes("Frigate API not reachable")) {
    return "API Frigate jest niedostępne";
  }
  if (message.includes("go2rtc API not reachable")) {
    return "API go2rtc jest niedostępne";
  }
  if (message.includes("Request failed")) {
    return "Żądanie nie powiodło się";
  }
  return message;
}
