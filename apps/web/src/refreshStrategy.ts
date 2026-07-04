export type RefreshMode = "full" | "live_light";
export type RefreshResource =
  | "backendHealth"
  | "locations"
  | "cameras"
  | "streams"
  | "go2rtcHealth"
  | "frigateHealth"
  | "frigateEvents"
  | "frigateRecordings"
  | "recordingPolicies";

const fullRefreshResources: RefreshResource[] = [
  "backendHealth",
  "locations",
  "cameras",
  "streams",
  "go2rtcHealth",
  "frigateHealth",
  "frigateEvents",
  "frigateRecordings",
  "recordingPolicies"
];

const liveLightRefreshResources: RefreshResource[] = [
  "backendHealth",
  "locations",
  "cameras",
  "streams",
  "go2rtcHealth",
  "recordingPolicies"
];

export function refreshModeForView(options: { view: string; silent?: boolean }): RefreshMode {
  return options.view === "live" && Boolean(options.silent) ? "live_light" : "full";
}

export function refreshResourcesForMode(mode: RefreshMode): RefreshResource[] {
  return mode === "live_light" ? [...liveLightRefreshResources] : [...fullRefreshResources];
}
