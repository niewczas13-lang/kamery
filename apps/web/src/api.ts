import { API_BASE_URL } from "./config";
import type {
  Camera,
  BackendHealth,
  FrigateEventsResponse,
  FrigateHealth,
  FrigateRecordingsResponse,
  Go2RtcHealth,
  Location,
  LoginResponse,
  PtzCommand,
  PtzResponse,
  RecordingPolicy,
  SnapshotResponse,
  Stream
} from "./types";

type RequestOptions = RequestInit & {
  token?: string;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export function getBackendHealth(): Promise<BackendHealth> {
  return apiFetch<BackendHealth>("/api/v1/health");
}

export function listLocations(token: string): Promise<Location[]> {
  return apiFetch<Location[]>("/api/v1/locations", { token });
}

export function listCameras(token: string): Promise<Camera[]> {
  return apiFetch<Camera[]>("/api/v1/cameras", { token });
}

export function listStreams(token: string): Promise<Stream[]> {
  return apiFetch<Stream[]>("/api/v1/streams", { token });
}

export function getGo2RtcHealth(token: string): Promise<Go2RtcHealth> {
  return apiFetch<Go2RtcHealth>("/api/v1/go2rtc/health", { token });
}

export function getFrigateHealth(token: string): Promise<FrigateHealth> {
  return apiFetch<FrigateHealth>("/api/v1/frigate/health", { token });
}

export function listFrigateEvents(token: string): Promise<FrigateEventsResponse> {
  return apiFetch<FrigateEventsResponse>("/api/v1/frigate/events", { token });
}

export function listFrigateRecordings(token: string): Promise<FrigateRecordingsResponse> {
  return apiFetch<FrigateRecordingsResponse>("/api/v1/frigate/recordings", { token });
}

export function listRecordingPolicies(token: string): Promise<RecordingPolicy[]> {
  return apiFetch<RecordingPolicy[]>("/api/v1/recording-policies", { token });
}

export function updateRecordingPolicy(
  token: string,
  cameraId: number,
  payload: Pick<RecordingPolicy, "mode" | "retention_days">
): Promise<RecordingPolicy> {
  return apiFetch<RecordingPolicy>(`/api/v1/cameras/${cameraId}/recording-policy`, {
    method: "PATCH",
    token,
    body: JSON.stringify(payload)
  });
}

export function createSnapshot(token: string, cameraId: number): Promise<SnapshotResponse> {
  return apiFetch<SnapshotResponse>(`/api/v1/cameras/${cameraId}/snapshot`, { method: "POST", token });
}

export function sendPtzCommand(
  token: string,
  cameraId: number,
  command: PtzCommand,
  durationMs = 300,
  speed = 0.3
): Promise<PtzResponse> {
  return apiFetch<PtzResponse>(`/api/v1/cameras/${cameraId}/ptz/${command}`, {
    method: "POST",
    token,
    body: JSON.stringify({ duration_ms: durationMs, speed })
  });
}

async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // Text fallback below.
  }
  return response.statusText || `Żądanie nie powiodło się: ${response.status}`;
}
