export type LoginResponse = {
  access_token: string;
  token_type: string;
};

export type Location = {
  id: number;
  name: string;
  slug: string;
  network_cidr?: string | null;
};

export type Camera = {
  id: number;
  location_id: number;
  name: string;
  slug: string;
  model: string;
  host: string;
  video_status: string;
  control_status: string;
  probe_status: string;
  reliability_status?: string;
  has_audio: boolean;
  has_ptz: boolean;
  has_onvif: boolean;
  has_snapshot: boolean;
  has_two_way_audio_candidate: boolean;
  enabled: boolean;
  notes?: string | null;
};

export type Stream = {
  stream_name: string;
  camera_id: number;
  camera_name: string;
  location_id: number;
  stream_role: string;
  path: string;
  video_codec?: string | null;
  audio_codec?: string | null;
  resolution?: string | null;
  fps?: number | null;
  has_audio: boolean;
  quality_role?: "main" | "sub" | "unknown";
  quality_label?: string;
  is_recommended_for_grid?: boolean;
  is_recommended_for_focus?: boolean;
  is_recommended_for_recording?: boolean;
  is_recommended_for_detection?: boolean;
  playback_status: string;
  warnings: string[];
};

export type Go2RtcHealth = {
  reachable: boolean;
  version?: string | null;
  stream_count?: number | null;
  error?: string | null;
};

export type BackendHealth = {
  ok: boolean;
  database: string;
};

export type FrigateHealth = {
  reachable: boolean;
  version?: string | null;
  error?: string | null;
};

export type FrigateEventsResponse = {
  reachable: boolean;
  events?: FrigateEvent[] | null;
  error?: string | null;
};

export type FrigateEvent = {
  id?: string;
  camera?: string;
  label?: string;
  type?: string;
  score?: number;
  top_score?: number;
  start_time?: number;
  end_time?: number;
  has_clip?: boolean;
  has_snapshot?: boolean;
  thumbnail_url?: string;
  clip_url?: string;
};

export type FrigateRecordingsResponse = {
  reachable: boolean;
  recordings?: FrigateRecording[] | null;
  error?: string | null;
};

export type FrigateRecording = {
  id?: string;
  camera?: string;
  start_time?: number;
  end_time?: number;
  severity?: string;
  thumb_path?: string;
  data?: unknown;
};

export type RecordingPolicy = {
  camera_id: number;
  camera_name: string;
  camera_slug: string;
  mode: "disabled" | "events_only" | "continuous" | "continuous_selected_hours";
  retention_days: number;
  record_main_stream: boolean;
  detect_sub_stream: boolean;
  enabled: boolean;
};

export type SnapshotResponse = {
  camera_id: number;
  camera_name: string;
  path: string;
  source_path: string;
  created_at: string;
};

export type PtzCommand = "up" | "down" | "left" | "right" | "zoom_in" | "zoom_out" | "stop";

export type PtzResponse = {
  camera_id: number;
  command: PtzCommand;
  status: "moved" | "stopped";
  duration_ms: number;
  stopped: boolean;
  warning?: string | null;
};
