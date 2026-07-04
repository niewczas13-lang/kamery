import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createSnapshot,
  getBackendHealth,
  getFrigateHealth,
  getGo2RtcHealth,
  listCameras,
  listFrigateEvents,
  listFrigateRecordings,
  listLocations,
  listRecordingPolicies,
  listStreams,
  login,
  sendPtzCommand,
  updateRecordingPolicy
} from "./api";
import { FRIGATE_PUBLIC_URL, GO2RTC_PUBLIC_URL } from "./config";
import { t, viewLabel, type ViewKey } from "./i18n/pl";
import {
  buildOperatorTiles,
  defaultSavedLayouts,
  selectTileStream,
  tileFallbackNotice,
  tileQualityText,
  visibleTileIdsForLayout,
  type NoVideoCamera,
  type OperatorTile,
  type SavedLiveLayout
} from "./liveTiles";
import { LiveWallConsole } from "./LiveWallConsole";
import { recordingPolicyError, sanitizeNvrUrl } from "./nvr";
import {
  playerAudioPolicy,
  ptzTargetLensLabel,
  sanitizeDisplayName,
  sanitizeSavedLayouts,
  type DisplayNameMaps,
  type PlayerAudioMode,
  type PtzTargetLens
} from "./operatorPreferences";
import { defaultPtzDurationMs, ptzCommandAllowed, sanitizePtzUiText, type PtzUiState } from "./ptz";
import { PtzJoystick } from "./PtzJoystick";
import {
  buildGo2RtcPlayerUrl,
  qualityLabel,
  qualityRoleForStream,
  selectStreamForSurface,
  streamLensRole,
  type PreviewProfile,
  type StreamLens
} from "./streamLinks";
import { apiErrorMessage, cameraStatusBadge } from "./status";
import type {
  BackendHealth,
  Camera,
  FrigateEvent,
  FrigateEventsResponse,
  FrigateHealth,
  FrigateRecording,
  FrigateRecordingsResponse,
  Go2RtcHealth,
  Location,
  PtzCommand,
  RecordingPolicy,
  SnapshotResponse,
  Stream
} from "./types";
import "./styles.css";

type View = Extract<ViewKey, "dashboard" | "live" | "cameras" | "streams" | "events" | "recordings" | "locations" | "diagnostics" | "settings">;
type LayoutChoice = "auto" | "1" | "2" | "4" | "6" | "9" | "custom";
type StatusFilter = "all" | "online" | "video_ok" | "unstable" | "no_video" | "ptz" | "recording";
type FocusState = {
  cameraId: number;
  lens: StreamLens;
  profile: PreviewProfile;
  mode: "single" | "split";
};

const tokenKey = "ezviz-panel-token";
const liveLayoutsKey = "ezviz-panel-live-layouts";
const activeLiveLayoutKey = "ezviz-panel-active-live-layout";
const cameraDisplayNamesKey = "cameraDisplayNames";
const tileDisplayNamesKey = "tileDisplayNames";
const ptzTargetLensKey = "h9cPtzTargetLens";
const navItems: View[] = ["dashboard", "live", "cameras", "streams", "events", "recordings", "locations", "diagnostics", "settings"];

export default function App() {
  const [token, setToken] = useState(() => window.localStorage.getItem(tokenKey) || "");
  const [view, setView] = useState<View>("live");
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(null);
  const [go2rtcHealth, setGo2rtcHealth] = useState<Go2RtcHealth | null>(null);
  const [frigateHealth, setFrigateHealth] = useState<FrigateHealth | null>(null);
  const [frigateEvents, setFrigateEvents] = useState<FrigateEventsResponse | null>(null);
  const [frigateRecordings, setFrigateRecordings] = useState<FrigateRecordingsResponse | null>(null);
  const [recordingPolicies, setRecordingPolicies] = useState<RecordingPolicy[]>([]);
  const [focus, setFocus] = useState<FocusState | null>(null);
  const [layout, setLayout] = useState<LayoutChoice>("auto");
  const [consoleProfile, setConsoleProfile] = useState<PreviewProfile>("auto");
  const [separateLenses, setSeparateLenses] = useState(true);
  const [showNoVideoInGrid, setShowNoVideoInGrid] = useState(false);
  const [customLayouts, setCustomLayouts] = useState<SavedLiveLayout[]>(() => loadSavedLayouts());
  const [activeLayoutId, setActiveLayoutId] = useState(() => window.localStorage.getItem(activeLiveLayoutKey) || "all");
  const [displayNames, setDisplayNames] = useState<DisplayNameMaps>(() => loadDisplayNames());
  const [ptzTargetLens, setPtzTargetLens] = useState<Record<string, PtzTargetLens>>(() => loadPtzTargetLens());
  const [operatorFullscreen, setOperatorFullscreen] = useState(false);
  const [monitorMode, setMonitorMode] = useState(false);
  const [ecoMode, setEcoMode] = useState(false);
  const [focusAudioEnabled, setFocusAudioEnabled] = useState(false);
  const [ptzControlUnlocked, setPtzControlUnlocked] = useState(false);
  const [search, setSearch] = useState("");
  const [locationFilter, setLocationFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [ptzSpeed, setPtzSpeed] = useState(0.3);
  const [ptzDuration, setPtzDuration] = useState(defaultPtzDurationMs());
  const [ptzStates, setPtzStates] = useState<Record<number, PtzUiState>>({});
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function refresh(options: { silent?: boolean } = {}) {
    if (!token) {
      return;
    }
    if (!options.silent) {
      setLoading(true);
      setError("");
    }
    try {
      const [
        nextBackendHealth,
        nextLocations,
        nextCameras,
        nextStreams,
        nextGo2rtcHealth,
        nextFrigateHealth,
        nextFrigateEvents,
        nextFrigateRecordings,
        nextRecordingPolicies
      ] = await Promise.all([
        getBackendHealth(),
        listLocations(token),
        listCameras(token),
        listStreams(token),
        getGo2RtcHealth(token),
        getFrigateHealth(token),
        listFrigateEvents(token),
        listFrigateRecordings(token),
        listRecordingPolicies(token)
      ]);
      setBackendHealth(nextBackendHealth);
      setLocations(nextLocations);
      setCameras(nextCameras);
      setStreams(nextStreams);
      setGo2rtcHealth(nextGo2rtcHealth);
      setFrigateHealth(nextFrigateHealth);
      setFrigateEvents(nextFrigateEvents);
      setFrigateRecordings(nextFrigateRecordings);
      setRecordingPolicies(nextRecordingPolicies);
    } catch (requestError) {
      setError(apiErrorMessage(requestError));
    } finally {
      if (!options.silent) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void refresh();
  }, [token]);

  useEffect(() => {
    if (!token || (view !== "live" && !monitorMode)) {
      return;
    }
    const timer = window.setInterval(() => {
      if (document.hidden) {
        return;
      }
      void refresh({ silent: true });
    }, ecoMode ? 15000 : 10000);
    return () => window.clearInterval(timer);
  }, [monitorMode, token, ecoMode, view]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && operatorFullscreen && !focus) {
        setOperatorFullscreen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [operatorFullscreen, focus]);

  function handleAuthenticated(nextToken: string) {
    window.localStorage.setItem(tokenKey, nextToken);
    setToken(nextToken);
  }

  function logout() {
    window.localStorage.removeItem(tokenKey);
    setToken("");
    setCameras([]);
    setStreams([]);
    setLocations([]);
    setBackendHealth(null);
    setGo2rtcHealth(null);
    setFrigateHealth(null);
    setFrigateEvents(null);
    setFrigateRecordings(null);
    setRecordingPolicies([]);
  }

  function openFocus(cameraId: number, lens: StreamLens = "lens1") {
    setFocusAudioEnabled(false);
    setPtzControlUnlocked(false);
    setFocus({ cameraId, lens, profile: "auto", mode: "single" });
  }

  function updateFocus(nextFocus: FocusState) {
    setFocusAudioEnabled(false);
    setPtzControlUnlocked(false);
    setFocus(nextFocus);
  }

  function closeFocus() {
    setFocusAudioEnabled(false);
    setPtzControlUnlocked(false);
    setFocus(null);
  }

  function persistDisplayNames(next: DisplayNameMaps) {
    setDisplayNames(next);
    window.localStorage.setItem(cameraDisplayNamesKey, JSON.stringify(next.cameraDisplayNames));
    window.localStorage.setItem(tileDisplayNamesKey, JSON.stringify(next.tileDisplayNames));
  }

  function renameTile(tile: OperatorTile) {
    const nextName = window.prompt("Nowa nazwa kafelka", displayNames.tileDisplayNames[tile.tile_id] || tile.title);
    if (nextName === null) {
      return;
    }
    const safeName = sanitizeDisplayName(nextName);
    if (!safeName) {
      setToast("Nazwa nie została zapisana, bo wygląda jak sekret albo URL.");
      return;
    }
    persistDisplayNames({
      ...displayNames,
      tileDisplayNames: { ...displayNames.tileDisplayNames, [tile.tile_id]: safeName }
    });
    setToast("Nazwa kafelka zapisana lokalnie.");
  }

  function resetTileName(tile: OperatorTile) {
    const nextTileNames = { ...displayNames.tileDisplayNames };
    delete nextTileNames[tile.tile_id];
    persistDisplayNames({ ...displayNames, tileDisplayNames: nextTileNames });
    setToast("Przywrócono techniczną nazwę kafelka.");
  }

  function renameCamera(camera: Camera) {
    const nextName = window.prompt("Nowa nazwa kamery", displayNames.cameraDisplayNames[camera.slug] || camera.name);
    if (nextName === null) {
      return;
    }
    const safeName = sanitizeDisplayName(nextName);
    if (!safeName) {
      setToast("Nazwa nie została zapisana, bo wygląda jak sekret albo URL.");
      return;
    }
    persistDisplayNames({
      ...displayNames,
      cameraDisplayNames: { ...displayNames.cameraDisplayNames, [camera.slug]: safeName }
    });
    setToast("Nazwa kamery zapisana lokalnie.");
  }

  function resetCameraName(camera: Camera) {
    const nextCameraNames = { ...displayNames.cameraDisplayNames };
    delete nextCameraNames[camera.slug];
    persistDisplayNames({ ...displayNames, cameraDisplayNames: nextCameraNames });
    setToast("Przywrócono techniczną nazwę kamery.");
  }

  function updatePtzTargetLens(cameraSlug: string, lens: PtzTargetLens) {
    const next = { ...ptzTargetLens, [cameraSlug]: lens };
    setPtzTargetLens(next);
    window.localStorage.setItem(ptzTargetLensKey, JSON.stringify(next));
  }

  const locationMap = useMemo(() => new Map(locations.map((location) => [location.id, location.name])), [locations]);
  const policiesBySlug = useMemo(
    () => new Map(recordingPolicies.map((policy) => [policy.camera_slug, policy])),
    [recordingPolicies]
  );
  const filteredCameras = useMemo(
    () => filterCameras(cameras, streams, policiesBySlug, { search, locationFilter, statusFilter }),
    [cameras, streams, policiesBySlug, search, locationFilter, statusFilter]
  );
  const focusCamera = focus ? cameras.find((camera) => camera.id === focus.cameraId) || null : null;

  if (!token) {
    return <LoginView onAuthenticated={handleAuthenticated} />;
  }

  return (
    <div className={["operator-shell", operatorFullscreen ? "operator-fullscreen" : "", monitorMode ? "monitor-mode" : ""].filter(Boolean).join(" ")}>
      <aside className="operator-sidebar">
        <div className="brand-lockup">
          <span className="brand-mark">EZ</span>
          <div>
            <p>{t("app.localOnly")}</p>
            <h1>{t("app.name")}</h1>
          </div>
        </div>
        <nav className="operator-nav" aria-label="Nawigacja główna">
          {navItems.map((item) => (
            <button key={item} className={view === item ? "nav-item active" : "nav-item"} onClick={() => setView(item)}>
              <span className="nav-dot" />
              {viewLabel(item)}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="ghost-button" onClick={() => void refresh()}>
            {t("common.refresh")}
          </button>
          <button className="ghost-button danger" onClick={logout}>
            {t("common.logout")}
          </button>
        </div>
      </aside>

      <main className="operator-main">
        <Topbar
          view={view}
          search={search}
          onSearch={setSearch}
          locations={locations}
          locationFilter={locationFilter}
          onLocationFilter={setLocationFilter}
          backendHealth={backendHealth}
          go2rtcHealth={go2rtcHealth}
          frigateHealth={frigateHealth}
        />

        {loading ? <Skeleton /> : null}
        {error ? <InlineAlert tone="bad" title={t("common.error")} body={error} /> : null}
        {toast ? <InlineAlert tone="info" title="Status" body={toast} /> : null}

        {!loading && view === "dashboard" ? (
          <Dashboard
            cameras={cameras}
            streams={streams}
            locations={locations}
            go2rtcHealth={go2rtcHealth}
            frigateHealth={frigateHealth}
            events={frigateEvents}
            policies={recordingPolicies}
            onView={setView}
            onFocus={(cameraId) => openFocus(cameraId)}
          />
        ) : null}
        {!loading && view === "live" ? (
          <LiveWallConsole
            cameras={filteredCameras}
            allCameraCount={cameras.length}
            streams={streams}
            locationMap={locationMap}
            policiesBySlug={policiesBySlug}
            events={frigateEvents?.events || []}
            layout={layout}
            onLayout={setLayout}
            statusFilter={statusFilter}
            onStatusFilter={setStatusFilter}
            consoleProfile={consoleProfile}
            onConsoleProfile={setConsoleProfile}
            separateLenses={separateLenses}
            onSeparateLenses={setSeparateLenses}
            showNoVideoInGrid={showNoVideoInGrid}
            onShowNoVideoInGrid={setShowNoVideoInGrid}
            customLayouts={customLayouts}
            activeLayoutId={activeLayoutId}
            onActiveLayoutId={(id) => {
              setActiveLayoutId(id);
              window.localStorage.setItem(activeLiveLayoutKey, id);
            }}
            onCustomLayouts={(layouts) => {
              setCustomLayouts(layouts);
              window.localStorage.setItem(liveLayoutsKey, JSON.stringify(layouts));
            }}
            displayNames={displayNames}
            fullscreenMode={operatorFullscreen}
            monitorMode={monitorMode}
            ecoMode={ecoMode}
            onFullscreenMode={setOperatorFullscreen}
            onMonitorMode={setMonitorMode}
            onEcoMode={setEcoMode}
            onRenameTile={renameTile}
            onResetTileName={resetTileName}
            onFocus={(cameraId, lens = "lens1") => openFocus(cameraId, lens)}
            onSnapshot={(cameraId) => void snapshotCamera(cameraId)}
          />
        ) : null}
        {!loading && view === "cameras" ? (
          <CamerasView
            cameras={filteredCameras}
            streams={streams}
            locationMap={locationMap}
            onFocus={(cameraId) => openFocus(cameraId)}
          />
        ) : null}
        {!loading && view === "streams" ? <StreamsView streams={streams} /> : null}
        {!loading && view === "events" ? <EventsView payload={frigateEvents} cameras={cameras} locations={locations} /> : null}
        {!loading && view === "recordings" ? <RecordingsView payload={frigateRecordings} cameras={cameras} /> : null}
        {!loading && view === "locations" ? <LocationsView locations={locations} cameras={cameras} /> : null}
        {!loading && view === "diagnostics" ? (
          <DiagnosticsView
            cameras={cameras}
            streams={streams}
            go2rtcHealth={go2rtcHealth}
            frigateHealth={frigateHealth}
          />
        ) : null}
        {!loading && view === "settings" ? <SettingsView /> : null}
      </main>

      {focus && focusCamera ? (
        <FocusMode
          token={token}
          camera={focusCamera}
          streams={streamsForCamera(focusCamera.id, streams)}
          policy={policiesBySlug.get(focusCamera.slug) || null}
          events={eventsForCamera(focusCamera, frigateEvents?.events || [])}
          recordings={recordingsForCamera(focusCamera, frigateRecordings?.recordings || [])}
          focus={focus}
          ptzState={ptzStates[focusCamera.id] || (focusCamera.has_ptz ? { state: "idle" } : { state: "not_supported" })}
          ptzSpeed={ptzSpeed}
          ptzDuration={ptzDuration}
          displayNames={displayNames}
          ptzTargetLens={ptzTargetLens[focusCamera.slug] || "unknown"}
          focusAudioEnabled={focusAudioEnabled}
          ptzControlUnlocked={ptzControlUnlocked}
          onPtzSpeed={setPtzSpeed}
          onPtzDuration={setPtzDuration}
          onFocusChange={updateFocus}
          onClose={closeFocus}
          onFocusAudio={setFocusAudioEnabled}
          onPtzControlUnlocked={setPtzControlUnlocked}
          onRenameCamera={renameCamera}
          onResetCamera={resetCameraName}
          onPtzTargetLens={(lens) => updatePtzTargetLens(focusCamera.slug, lens)}
          onSnapshot={(cameraId) => void snapshotCamera(cameraId)}
          onPtz={(command, durationMs, speed) => void runPtz(focusCamera, command, durationMs, speed)}
          onPolicyUpdated={(policy) => updatePolicyState(setRecordingPolicies, policy)}
        />
      ) : null}
    </div>
  );

  async function snapshotCamera(cameraId: number) {
    setToast("");
    try {
      const snapshot = await createSnapshot(token, cameraId);
      setToast(`Zrzut zapisany: ${snapshot.created_at}`);
    } catch (requestError) {
      setToast(apiErrorMessage(requestError));
    }
  }

  async function runPtz(camera: Camera, command: PtzCommand, durationMs: number, speed: number) {
    if (!ptzCommandAllowed(command, ptzControlUnlocked)) {
      setToast("PTZ zablokowane. Odblokuj ruch PTZ w focus mode albo użyj STOP awaryjnie.");
      return;
    }
    setPtzStates((items) => ({ ...items, [camera.id]: { state: "moving", command } }));
    try {
      const response = await sendPtzCommand(token, camera.id, command, durationMs, speed);
      setPtzStates((items) => ({ ...items, [camera.id]: { state: "stopped", command } }));
      const warning = response.warning ? ` ${sanitizePtzUiText(response.warning)}` : "";
      setToast(`PTZ: ${commandLabelPl(command)} - ${response.status === "stopped" ? "zatrzymano" : "wykonano"}.${warning}`);
    } catch (requestError) {
      const message = apiErrorMessage(requestError);
      setPtzStates((items) => ({
        ...items,
        [camera.id]: message.includes("PTZ not supported") ? { state: "not_supported" } : { state: "failed", message }
      }));
      setToast(sanitizePtzUiText(message));
    }
  }
}

function LoginView({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await login(username, password);
      onAuthenticated(response.access_token);
    } catch (requestError) {
      setError(apiErrorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-panel">
        <p className="eyebrow">{t("app.localOnly")}</p>
        <h1>{t("app.name")}</h1>
        <form onSubmit={submit} className="login-form">
          <label>
            <span>Użytkownik</span>
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            <span>Hasło</span>
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete="current-password"
            />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "Logowanie" : "Zaloguj"}
          </button>
        </form>
      </section>
    </main>
  );
}

function Topbar({
  view,
  search,
  onSearch,
  locations,
  locationFilter,
  onLocationFilter,
  backendHealth,
  go2rtcHealth,
  frigateHealth
}: {
  view: View;
  search: string;
  onSearch: (value: string) => void;
  locations: Location[];
  locationFilter: string;
  onLocationFilter: (value: string) => void;
  backendHealth: BackendHealth | null;
  go2rtcHealth: Go2RtcHealth | null;
  frigateHealth: FrigateHealth | null;
}) {
  return (
    <header className="operator-topbar">
      <div>
        <p className="eyebrow">Panel operatora</p>
        <h2>{viewLabel(view)}</h2>
      </div>
      <div className="topbar-controls">
        <input value={search} onChange={(event) => onSearch(event.target.value)} placeholder="Szukaj kamer..." />
        <select value={locationFilter} onChange={(event) => onLocationFilter(event.target.value)}>
          <option value="all">Wszystkie lokalizacje</option>
          {locations.map((location) => (
            <option key={location.id} value={String(location.id)}>
              {location.name}
            </option>
          ))}
        </select>
      </div>
      <div className="health-strip">
        <HealthPill label="API" ok={Boolean(backendHealth?.ok)} />
        <HealthPill label="go2rtc" ok={Boolean(go2rtcHealth?.reachable)} />
        <HealthPill label="Frigate" ok={Boolean(frigateHealth?.reachable)} />
        <span className="status-pill warn">HEVC / dysk</span>
      </div>
    </header>
  );
}

function Dashboard({
  cameras,
  streams,
  locations,
  go2rtcHealth,
  frigateHealth,
  events,
  policies,
  onView,
  onFocus
}: {
  cameras: Camera[];
  streams: Stream[];
  locations: Location[];
  go2rtcHealth: Go2RtcHealth | null;
  frigateHealth: FrigateHealth | null;
  events: FrigateEventsResponse | null;
  policies: RecordingPolicy[];
  onView: (view: View) => void;
  onFocus: (cameraId: number) => void;
}) {
  const unstable = cameras.filter((camera) => camera.reliability_status === "unstable").length;
  const liveStreams = streams.filter((stream) => qualityRoleForStream(stream) === "sub").length;
  const ptzCameras = cameras.filter((camera) => camera.has_ptz).length;
  const recordingEnabled = policies.filter((policy) => policy.enabled).length;
  const h9c = cameras.find((camera) => camera.slug === "lukow_h9c_98");
  const recentEvents = (events?.events || []).slice(0, 4);
  return (
    <section className="content-stack">
      <div className="control-room-grid">
        <Metric label="Kamery" value={cameras.length} />
        <Metric label="Strumienie live" value={liveStreams} />
        <Metric label="Kamery PTZ" value={ptzCameras} />
        <Metric label="Niestabilne" value={unstable} />
        <Metric label="Nagrywanie" value={recordingEnabled} />
        <Metric label="Lokalizacje" value={locations.length} />
      </div>
      <section className="surface dark-surface">
        <div className="section-heading">
          <div>
            <h3>Stan systemu</h3>
            <p>{t("nvr.engineNote")}</p>
          </div>
        </div>
        <div className="health-cards">
          <HealthCard title="Backend" ok={Boolean(go2rtcHealth || frigateHealth)} detail="API panelu lokalnego" />
          <HealthCard title="go2rtc" ok={Boolean(go2rtcHealth?.reachable)} detail={`${go2rtcHealth?.stream_count ?? 0} strumieni`} />
          <HealthCard title="Frigate" ok={Boolean(frigateHealth?.reachable)} detail={frigateHealth?.version || "wersja nieznana"} />
          <HealthCard title="Dysk" ok={false} detail="brak dokładnych danych" />
        </div>
        <StorageRetentionNotice />
      </section>
      <section className="operator-split">
        <div className="surface">
          <div className="section-heading">
            <div>
              <h3>Ostatnie zdarzenia</h3>
              <p>Mini timeline z lokalnego Frigate.</p>
            </div>
            <button className="ghost-button" onClick={() => onView("events")}>
              Zobacz zdarzenia
            </button>
          </div>
          <EventList events={recentEvents} emptyBody={t("events.emptyBody")} />
        </div>
        <div className="surface quick-launch">
          <h3>Szybki start</h3>
          <button className="primary-button" onClick={() => onView("live")}>
            Konsola podglądu
          </button>
          {h9c ? (
            <button className="ghost-button" onClick={() => onFocus(h9c.id)}>
              H9C - dwa obiektywy
            </button>
          ) : null}
          <button className="ghost-button" onClick={() => onView("recordings")}>
            Nagrania
          </button>
          <a className="ghost-link" href={FRIGATE_PUBLIC_URL} target="_blank" rel="noreferrer">
            Frigate lokalnie
          </a>
        </div>
      </section>
    </section>
  );
}

function LiveConsole({
  cameras,
  allCameraCount,
  streams,
  locationMap,
  policiesBySlug,
  events,
  layout,
  onLayout,
  statusFilter,
  onStatusFilter,
  consoleProfile,
  onConsoleProfile,
  cardProfiles,
  onCardProfile,
  loadedStreams,
  onLoadStream,
  onFocus,
  onSnapshot
}: {
  cameras: Camera[];
  allCameraCount: number;
  streams: Stream[];
  locationMap: Map<number, string>;
  policiesBySlug: Map<string, RecordingPolicy>;
  events: FrigateEvent[];
  layout: LayoutChoice;
  onLayout: (layout: LayoutChoice) => void;
  statusFilter: StatusFilter;
  onStatusFilter: (status: StatusFilter) => void;
  consoleProfile: PreviewProfile;
  onConsoleProfile: (profile: PreviewProfile) => void;
  cardProfiles: Record<number, PreviewProfile>;
  onCardProfile: (cameraId: number, profile: PreviewProfile) => void;
  loadedStreams: string[];
  onLoadStream: (streamName: string) => void;
  onFocus: (cameraId: number) => void;
  onSnapshot: (cameraId: number) => void;
}) {
  const limit = layoutLimit(layout);
  const visible = cameras.slice(0, limit);
  const hiddenCount = Math.max(cameras.length - visible.length, 0);
  return (
    <section className="content-stack">
      <div className="console-toolbar">
        <Segmented
          label="Układ"
          value={layout}
          options={[
            ["1", "1"],
            ["2", "2"],
            ["4", "4"],
            ["6", "6"],
            ["9", "9"],
            ["auto", "Auto"]
          ]}
          onChange={(value) => onLayout(value as LayoutChoice)}
        />
        <Segmented
          label="Jakość"
          value={consoleProfile}
          options={[
            ["auto", "Auto"],
            ["fast", "Szybka"],
            ["high", "Wysoka"]
          ]}
          onChange={(value) => onConsoleProfile(value as PreviewProfile)}
        />
        <select value={statusFilter} onChange={(event) => onStatusFilter(event.target.value as StatusFilter)}>
          <option value="all">Wszystkie statusy</option>
          <option value="online">Online</option>
          <option value="video_ok">Obraz OK</option>
          <option value="unstable">Niestabilna</option>
          <option value="no_video">Brak obrazu</option>
          <option value="ptz">PTZ</option>
          <option value="recording">Nagrywanie</option>
        </select>
      </div>
      <InlineAlert
        tone="info"
        title="Profile jakości"
        body="Auto w gridzie używa SUB. Powiększenie i fullscreen przełączają na MAIN, jeśli jest dostępny."
      />
      <div className={`camera-grid layout-${layout === "auto" ? "4" : layout}`}>
        {visible.map((camera) => (
          <CameraCard
            key={camera.id}
            camera={camera}
            locationName={locationMap.get(camera.location_id) || "Lokalizacja nieznana"}
            streams={streamsForCamera(camera.id, streams)}
            policy={policiesBySlug.get(camera.slug) || null}
            lastEvent={eventsForCamera(camera, events)[0]}
            profile={cardProfiles[camera.id] || consoleProfile}
            loadedStreams={loadedStreams}
            onProfile={(profile) => onCardProfile(camera.id, profile)}
            onLoadStream={onLoadStream}
            onFocus={() => onFocus(camera.id)}
            onSnapshot={() => onSnapshot(camera.id)}
          />
        ))}
      </div>
      {!visible.length ? <EmptyState title="Brak kamer" body="Filtry nie zwracają kamer do podglądu." /> : null}
      {hiddenCount ? (
        <InlineAlert
          tone="warn"
          title="Limit podglądu"
          body={`Pokazuję ${visible.length} z ${cameras.length} pasujących kamer. To chroni panel przed automatycznym ładowaniem wielu strumieni MAIN. Łącznie w bazie: ${allCameraCount}.`}
        />
      ) : null}
    </section>
  );
}

function CameraCard({
  camera,
  locationName,
  streams,
  policy,
  lastEvent,
  profile,
  loadedStreams,
  onProfile,
  onLoadStream,
  onFocus,
  onSnapshot
}: {
  camera: Camera;
  locationName: string;
  streams: Stream[];
  policy: RecordingPolicy | null;
  lastEvent?: FrigateEvent;
  profile: PreviewProfile;
  loadedStreams: string[];
  onProfile: (profile: PreviewProfile) => void;
  onLoadStream: (streamName: string) => void;
  onFocus: () => void;
  onSnapshot: () => void;
}) {
  const stream = selectStreamForSurface(streams, { profile, surface: "grid", lens: "lens1" });
  const isLoaded = Boolean(stream && loadedStreams.includes(stream.stream_name));
  const playerUrl = stream ? buildGo2RtcPlayerUrl(GO2RTC_PUBLIC_URL, stream.stream_name, { audio: "off" }) : "";
  const status = cameraStatusBadge(camera);
  const recording = Boolean(policy?.enabled);
  return (
    <article className="camera-card">
      <div className="camera-preview">
        {isLoaded && stream ? (
          <iframe title={stream.stream_name} src={playerUrl} />
        ) : (
          <div className="preview-placeholder">
            <strong>{camera.name}</strong>
            <span>Podgląd nie jest ładowany automatycznie</span>
            {stream ? (
              <button className="primary-button small" onClick={() => onLoadStream(stream.stream_name)}>
                Załaduj podgląd
              </button>
            ) : (
              <span className="badge muted">Brak strumienia</span>
            )}
          </div>
        )}
      </div>
      <div className="camera-card-body">
        <div className="section-heading compact">
          <div>
            <h3>{camera.name}</h3>
            <p>
              {locationName} / {camera.model}
            </p>
          </div>
          <span className={`badge ${status.tone}`}>{status.label}</span>
        </div>
        <StatusChips camera={camera} stream={stream} recording={recording} />
        <div className="quality-line">
          <span>Jakość: {profileLabel(profile)}</span>
          <span>Strumień: {stream ? qualityRoleForStream(stream).toUpperCase() : "-"}</span>
          <span>Rozdzielczość: {stream?.resolution || "-"}</span>
          <span>FPS: {formatFps(stream?.fps)}</span>
          <span>Kodek: {stream?.video_codec?.toUpperCase() || "-"}</span>
        </div>
        {lastEvent ? (
          <p className="muted">Ostatnie zdarzenie: {lastEvent.label || lastEvent.type || "zdarzenie"} / {formatTimestamp(lastEvent.start_time)}</p>
        ) : (
          <p className="muted">Brak ostatnich zdarzeń.</p>
        )}
        <div className="row-actions wrap">
          <button className="primary-button small" onClick={onFocus}>
            Powiększ
          </button>
          <button className="ghost-button" onClick={() => onProfile("high")}>
            Wysoka jakość
          </button>
          <button className="ghost-button" onClick={() => onProfile("fast")}>
            Szybki podgląd
          </button>
          <button className="ghost-button" onClick={onSnapshot}>
            Zrzut
          </button>
          <button className="ghost-button" onClick={onFocus}>
            Sterowanie
          </button>
        </div>
      </div>
    </article>
  );
}

function FocusMode({
  token,
  camera,
  streams,
  policy,
  events,
  recordings,
  focus,
  ptzState,
  ptzSpeed,
  ptzDuration,
  onPtzSpeed,
  onPtzDuration,
  displayNames,
  ptzTargetLens,
  focusAudioEnabled,
  ptzControlUnlocked,
  onFocusChange,
  onClose,
  onFocusAudio,
  onPtzControlUnlocked,
  onRenameCamera,
  onResetCamera,
  onPtzTargetLens,
  onSnapshot,
  onPtz,
  onPolicyUpdated
}: {
  token: string;
  camera: Camera;
  streams: Stream[];
  policy: RecordingPolicy | null;
  events: FrigateEvent[];
  recordings: FrigateRecording[];
  focus: FocusState;
  ptzState: PtzUiState;
  ptzSpeed: number;
  ptzDuration: number;
  displayNames: DisplayNameMaps;
  ptzTargetLens: PtzTargetLens;
  focusAudioEnabled: boolean;
  ptzControlUnlocked: boolean;
  onPtzSpeed: (speed: number) => void;
  onPtzDuration: (durationMs: number) => void;
  onFocusChange: (state: FocusState) => void;
  onClose: () => void;
  onFocusAudio: (enabled: boolean) => void;
  onPtzControlUnlocked: (unlocked: boolean) => void;
  onRenameCamera: (camera: Camera) => void;
  onResetCamera: (camera: Camera) => void;
  onPtzTargetLens: (lens: PtzTargetLens) => void;
  onSnapshot: (cameraId: number) => void;
  onPtz: (command: PtzCommand, durationMs: number, speed: number) => void;
  onPolicyUpdated: (policy: RecordingPolicy) => void;
}) {
  const [message, setMessage] = useState("");
  const [policyMode, setPolicyMode] = useState<RecordingPolicy["mode"]>(policy?.mode || "disabled");
  const [retentionDays, setRetentionDays] = useState(policy?.retention_days || 1);
  const hasLens2 = streams.some((stream) => streamLensRole(stream) === "lens2");
  const activeStream = selectStreamForSurface(streams, {
    profile: focus.profile,
    surface: "focus",
    lens: focus.lens
  });
  const splitStreams = [
    selectStreamForSurface(streams, { profile: "fast", surface: "split", lens: "lens1" }),
    selectStreamForSurface(streams, { profile: "fast", surface: "split", lens: "lens2" })
  ].filter(Boolean) as Stream[];
  const secondaryLens = focus.lens === "lens2" ? "lens1" : "lens2";
  const secondaryStream = hasLens2 ? selectStreamForSurface(streams, { profile: "fast", surface: "split", lens: secondaryLens }) : undefined;
  const focusTileId = `${camera.slug}:${hasLens2 ? focus.lens : "single"}`;
  const cameraDisplayName = sanitizeDisplayName(displayNames.cameraDisplayNames[camera.slug] || "") || camera.name;
  const focusDisplayName =
    sanitizeDisplayName(displayNames.tileDisplayNames[focusTileId] || "") ||
    (hasLens2 ? `${cameraDisplayName} - ${focus.lens === "lens2" ? "Obiektyw 2" : "Obiektyw 1"}` : cameraDisplayName);
  const activeAudioPolicy = playerAudioPolicy({
    surface: focus.mode === "split" ? "split" : "focus",
    hasAudio: Boolean(activeStream?.has_audio || camera.has_audio),
    requestedAudio: focusAudioEnabled,
    active: true
  });
  const timelineEvents = eventsForFocusLens(camera, events, focus.lens);
  const timelineRecordings = recordingsForFocusLens(camera, recordings, focus.lens);

  useEffect(() => {
    setPolicyMode(policy?.mode || "disabled");
    setRetentionDays(policy?.retention_days || 1);
  }, [policy?.mode, policy?.retention_days, camera.id]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName)) {
        return;
      }
      const command = keyboardCommand(event);
      if (!command) {
        return;
      }
      event.preventDefault();
      if (command === "close") {
        onClose();
        return;
      }
      onPtz(command, ptzDuration, ptzSpeed);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, onPtz, ptzDuration, ptzSpeed]);

  async function savePolicy() {
    const validation = recordingPolicyError({ mode: policyMode, retention_days: retentionDays });
    if (validation) {
      setMessage(validation);
      return;
    }
    try {
      const nextPolicy = await updateRecordingPolicy(token, camera.id, {
        mode: policyMode,
        retention_days: retentionDays
      });
      onPolicyUpdated(nextPolicy);
      setMessage("Polityka nagrywania zapisana.");
    } catch (requestError) {
      setMessage(apiErrorMessage(requestError));
    }
  }

  return (
    <aside className="focus-overlay" aria-label="Tryb powiększenia kamery">
      <div className="focus-main">
        <div className="focus-head">
          <div>
            <p className="eyebrow">{camera.slug}</p>
            <h3>{focusDisplayName}</h3>
            <p>{camera.model}</p>
          </div>
          <div className="row-actions wrap">
            <button className="ghost-button" onClick={() => onRenameCamera(camera)}>
              Zmień nazwę
            </button>
            <button className="ghost-button" onClick={() => onResetCamera(camera)}>
              Reset nazwy
            </button>
            <button className="ghost-button" onClick={() => onSnapshot(camera.id)}>
              Zrób zrzut
            </button>
            {activeStream ? (
              <a className="ghost-link" href={buildGo2RtcPlayerUrl(GO2RTC_PUBLIC_URL, activeStream.stream_name)} target="_blank" rel="noreferrer">
                Otwórz w odtwarzaczu
              </a>
            ) : null}
            <button className="ghost-button danger" onClick={onClose}>
              Zamknij
            </button>
          </div>
        </div>
        {hasLens2 ? (
          <Segmented
            label="Obiektyw"
            value={focus.mode === "split" ? "split" : focus.lens}
            options={[
              ["lens1", "Obiektyw 1"],
              ["lens2", "Obiektyw 2"],
              ["split", "Widok podzielony"]
            ]}
            onChange={(value) =>
              onFocusChange({
                ...focus,
                mode: value === "split" ? "split" : "single",
                lens: value === "lens2" ? "lens2" : "lens1",
                profile: value === "split" ? "fast" : "auto"
              })
            }
          />
        ) : null}
        <Segmented
          label="Jakość"
          value={focus.profile}
          options={[
            ["auto", "Auto"],
            ["fast", "Szybki podgląd"],
            ["high", "Wysoka jakość"]
          ]}
          onChange={(value) => onFocusChange({ ...focus, profile: value as PreviewProfile, mode: "single" })}
        />
        {activeStream ? (
          <AudioControl
            policy={activeAudioPolicy}
            split={focus.mode === "split"}
            onToggle={() => onFocusAudio(!activeAudioPolicy.enabled)}
          />
        ) : null}
        {focus.mode === "split" ? (
          <div className="split-view">
            {splitStreams.map((stream) => {
              const lens = streamLensRole(stream) === "lens2" ? "lens2" : "lens1";
              const isActiveLens = lens === focus.lens;
              const splitAudioPolicy = playerAudioPolicy({
                surface: "split",
                hasAudio: Boolean(stream.has_audio || camera.has_audio),
                requestedAudio: focusAudioEnabled,
                active: isActiveLens
              });
              return (
                <div className="split-player" key={stream.stream_name}>
                  <StreamPlayer stream={stream} audioMode={splitAudioPolicy.playerAudio} audioLabel={splitAudioPolicy.label} />
                  <button className="text-button" onClick={() => onFocusChange({ ...focus, lens, mode: "split", profile: "fast" })}>
                    {isActiveLens ? "Aktywny obiektyw" : "Ustaw aktywny dźwięk"}
                  </button>
                </div>
              );
            })}
          </div>
        ) : activeStream ? (
          <div className="focus-player-wrap">
            <StreamPlayer stream={activeStream} large audioMode={activeAudioPolicy.playerAudio} audioLabel={activeAudioPolicy.label} />
            {secondaryStream ? (
              <div className="lens-miniature">
                <button
                  className="text-button"
                  onClick={() => onFocusChange({ ...focus, lens: secondaryLens, profile: "auto", mode: "single" })}
                  aria-label="Przełącz na drugi obiektyw"
                >
                  {secondaryLens === "lens2" ? "Obiektyw 2" : "Obiektyw 1"}
                </button>
                <iframe
                  title={`${secondaryStream.stream_name}-mini`}
                  src={buildGo2RtcPlayerUrl(GO2RTC_PUBLIC_URL, secondaryStream.stream_name, { audio: "off" })}
                  allow="fullscreen"
                />
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState title="Brak strumienia" body="Brak strumienia wysokiej jakości. Używam podglądu szybkiego, jeśli jest dostępny." />
        )}
        <div className="stream-meta">
          <KeyValue label="Jakość" value={activeStream ? qualityLabel(qualityRoleForStream(activeStream)) : "-"} />
          <KeyValue label="Rozdzielczość" value={activeStream?.resolution || "-"} />
          <KeyValue label="FPS" value={formatFps(activeStream?.fps)} />
          <KeyValue label="Kodek" value={activeStream?.video_codec?.toUpperCase() || "-"} />
          <KeyValue label="Strumień techniczny" value={activeStream?.stream_name || "-"} />
        </div>
        <FocusTimeline events={timelineEvents} recordings={timelineRecordings} />
        {activeStream && qualityRoleForStream(activeStream) === "main" && activeStream.video_codec?.toLowerCase().includes("hevc") ? (
          <InlineAlert
            tone="warn"
            title="HEVC/H.265"
            body="Strumień wysokiej jakości używa HEVC/H.265. Jeśli obraz się nie odtwarza, użyj trybu szybkiego albo dodaj H.264 fallback w kolejnym etapie."
          />
        ) : null}
      </div>
      <div className="focus-side">
        {camera.has_ptz ? (
          <InlineAlert
            tone="info"
            title="Sterowanie kamerą fizyczną"
            body={`PTZ steruje fizyczną kamerą. Aktualnie przypisane do: ${ptzTargetLensLabel(ptzTargetLens)}.`}
          />
        ) : null}
        {camera.has_ptz && hasLens2 ? (
          <section className="surface ptz-target-card">
            <h4>PTZ steruje</h4>
            <p className="muted">Otwórz oba obiektywy, wykonaj krótki ruch PTZ i wybierz, który obraz się poruszył.</p>
            <select value={ptzTargetLens} onChange={(event) => onPtzTargetLens(event.target.value as PtzTargetLens)}>
              <option value="lens1">Obiektyw 1</option>
              <option value="lens2">Obiektyw 2</option>
              <option value="unknown">Nie wiem / do sprawdzenia</option>
            </select>
          </section>
        ) : null}
        {camera.has_ptz ? (
          <PtzSafetyLock unlocked={ptzControlUnlocked} onUnlocked={onPtzControlUnlocked} />
        ) : null}
        <PtzOptions speed={ptzSpeed} durationMs={ptzDuration} onSpeed={onPtzSpeed} onDuration={onPtzDuration} />
        <PtzJoystick
          camera={camera}
          state={ptzState}
          speed={ptzSpeed}
          durationMs={ptzDuration}
          movementUnlocked={ptzControlUnlocked}
          onCommand={onPtz}
        />
        <section className="surface">
          <h4>Polityka nagrywania</h4>
          <div className="policy-form">
            <label>
              <span>Tryb</span>
              <select value={policyMode} onChange={(event) => setPolicyMode(event.target.value as RecordingPolicy["mode"])}>
                <option value="disabled">Wyłączone</option>
                <option value="events_only">Tylko zdarzenia</option>
                <option value="continuous">Ciągłe</option>
                <option value="continuous_selected_hours">Wybrane godziny</option>
              </select>
            </label>
            <label>
              <span>Retencja dni</span>
              <input type="number" min={1} max={30} value={retentionDays} onChange={(event) => setRetentionDays(Number(event.target.value))} />
            </label>
            <button className="primary-button small" onClick={() => void savePolicy()}>
              Zapisz politykę
            </button>
          </div>
          {message ? <p className="muted">{message}</p> : null}
        </section>
        <section className="surface event-drawer">
          <h4>Ostatnie zdarzenia</h4>
          <EventList events={events.slice(0, 8)} emptyBody={t("events.emptyBody")} compact />
        </section>
        <section className="surface">
          <h4>Ostatnie nagrania</h4>
          {recordings.slice(0, 5).map((recording, index) => (
            <p className="muted" key={recording.id || index}>
              {formatTimestamp(recording.start_time)} - {formatTimestamp(recording.end_time)}
            </p>
          ))}
          {!recordings.length ? <p className="muted">Brak nagrań dla tej kamery.</p> : null}
        </section>
      </div>
    </aside>
  );
}

function PtzOptions({
  speed,
  durationMs,
  onSpeed,
  onDuration
}: {
  speed: number;
  durationMs: number;
  onSpeed: (speed: number) => void;
  onDuration: (durationMs: number) => void;
}) {
  return (
    <section className="surface ptz-options">
      <h4>Opcje ruchu</h4>
      <label>
        <span>Prędkość</span>
        <select value={speed} onChange={(event) => onSpeed(Number(event.target.value))}>
          <option value={0.15}>Wolna</option>
          <option value={0.3}>Średnia</option>
          <option value={0.65}>Szybka</option>
        </select>
      </label>
      <label>
        <span>Czas ruchu</span>
        <select value={durationMs} onChange={(event) => onDuration(Number(event.target.value))}>
          <option value={200}>200 ms</option>
          <option value={300}>300 ms</option>
          <option value={500}>500 ms</option>
        </select>
      </label>
      <p className="muted">Skróty: strzałki, +, -, spacja, Escape.</p>
    </section>
  );
}

function PtzSafetyLock({ unlocked, onUnlocked }: { unlocked: boolean; onUnlocked: (unlocked: boolean) => void }) {
  return (
    <section className={unlocked ? "surface ptz-safety-card unlocked" : "surface ptz-safety-card locked"}>
      <div className="section-heading compact">
        <div>
          <h4>Blokada ruchu PTZ</h4>
          <p>
            {unlocked
              ? "Ruch PTZ jest odblokowany tylko w tej sesji focus mode."
              : "Panel nie wyśle ruchu PTZ. STOP zostaje aktywny awaryjnie."}
          </p>
        </div>
        <label className="toggle-row">
          <input type="checkbox" checked={unlocked} onChange={(event) => onUnlocked(event.target.checked)} />
          <span>{unlocked ? "Ruch odblokowany" : "Odblokuj ruch"}</span>
        </label>
      </div>
      {!unlocked ? <p className="warning-text">Domyślnie zablokowane, żeby panel nie mógł przypadkowo ruszyć kamerą.</p> : null}
    </section>
  );
}

function AudioControl({
  policy,
  split,
  onToggle
}: {
  policy: ReturnType<typeof playerAudioPolicy>;
  split: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="audio-control">
      <div>
        <strong>Dźwięk</strong>
        <span>{split ? "Dźwięk z aktywnego obiektywu" : policy.label}</span>
      </div>
      {policy.canEnable ? (
        <button className={policy.enabled ? "ghost-button danger" : "primary-button small"} onClick={onToggle}>
          {policy.enabled ? "Wycisz" : "Włącz dźwięk"}
        </button>
      ) : (
        <span className="badge muted">{policy.label}</span>
      )}
    </div>
  );
}

function FocusTimeline({ events, recordings }: { events: FrigateEvent[]; recordings: FrigateRecording[] }) {
  const items = [
    ...events.slice(0, 6).map((event) => ({ kind: "event" as const, event, time: event.start_time || 0 })),
    ...recordings.slice(0, 4).map((recording) => ({ kind: "recording" as const, recording, time: recording.start_time || 0 }))
  ]
    .sort((a, b) => b.time - a.time)
    .slice(0, 8);

  return (
    <section className="focus-timeline">
      <div className="section-heading compact">
        <div>
          <h4>Ostatnie zdarzenia i nagrania</h4>
          <p>Mini timeline z lokalnego Frigate.</p>
        </div>
      </div>
      {!items.length ? <EmptyState title="Brak zdarzeń" body="Brak zdarzeń i nagrań dla tego obiektywu." /> : null}
      <div className="timeline-strip">
        {items.map((item, index) =>
          item.kind === "event" ? (
            <TimelineEventItem event={item.event} key={item.event.id || `event-${index}`} />
          ) : (
            <TimelineRecordingItem recording={item.recording} key={item.recording.id || `recording-${index}`} />
          )
        )}
      </div>
    </section>
  );
}

function TimelineEventItem({ event }: { event: FrigateEvent }) {
  const thumbUrl = event.id && (event.has_snapshot || event.has_clip) ? sanitizeNvrUrl(`${FRIGATE_PUBLIC_URL}/api/events/${event.id}/thumbnail.jpg`) : "";
  const clipUrl = event.id && event.has_clip ? sanitizeNvrUrl(`${FRIGATE_PUBLIC_URL}/api/events/${event.id}/clip.mp4`) : "";
  return (
    <article className="timeline-item">
      <span className="event-thumb small">{thumbUrl ? <img src={thumbUrl} alt="" /> : "Brak miniatury"}</span>
      <strong>{eventLabel(event)}</strong>
      <span>{formatTimestamp(event.start_time)}</span>
      {clipUrl ? (
        <a className="ghost-link" href={clipUrl} target="_blank" rel="noreferrer">
          Otwórz klip
        </a>
      ) : (
        <span className="muted">Zdarzenie</span>
      )}
    </article>
  );
}

function TimelineRecordingItem({ recording }: { recording: FrigateRecording }) {
  return (
    <article className="timeline-item">
      <span className="event-thumb small">Nagranie</span>
      <strong>{recording.camera || "kamera"}</strong>
      <span>{formatTimestamp(recording.start_time)}</span>
      <span className="muted">Nagranie lokalne</span>
    </article>
  );
}

function StreamPlayer({
  stream,
  large = false,
  audioMode = "off",
  audioLabel = "Dźwięk wyłączony"
}: {
  stream: Stream;
  large?: boolean;
  audioMode?: PlayerAudioMode;
  audioLabel?: string;
}) {
  return (
    <div className={large ? "stream-player large" : "stream-player"}>
      <iframe
        title={stream.stream_name}
        src={buildGo2RtcPlayerUrl(GO2RTC_PUBLIC_URL, stream.stream_name, { audio: audioMode })}
        allow={audioMode === "on" ? "autoplay; fullscreen" : "fullscreen"}
      />
      <div className="player-caption">
        <strong>{stream.camera_name}</strong>
        <span>
          {qualityLabel(qualityRoleForStream(stream))} / {stream.resolution || "-"} / {stream.video_codec?.toUpperCase() || "-"}
        </span>
        <span>{audioLabel}</span>
      </div>
    </div>
  );
}

function CamerasView({
  cameras,
  streams,
  locationMap,
  onFocus
}: {
  cameras: Camera[];
  streams: Stream[];
  locationMap: Map<number, string>;
  onFocus: (cameraId: number) => void;
}) {
  return (
    <section className="surface">
      <div className="section-heading">
        <div>
          <h3>Kamery</h3>
          <p>Inwentarz operatora bez haseł, RTSP URL-i i wartości sekretów.</p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Nazwa</th>
              <th>Model</th>
              <th>Lokalizacja</th>
              <th>Status</th>
              <th>Możliwości</th>
              <th>Strumienie</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {cameras.map((camera) => {
              const badge = cameraStatusBadge(camera);
              const cameraStreams = streamsForCamera(camera.id, streams);
              return (
                <tr key={camera.id}>
                  <td>
                    <strong>{camera.name}</strong>
                    <span className="muted-block">{camera.slug}</span>
                  </td>
                  <td>{camera.model || "-"}</td>
                  <td>{locationMap.get(camera.location_id) || "-"}</td>
                  <td>
                    <span className={`badge ${badge.tone}`}>{badge.label}</span>
                    <span className="muted-block">{camera.reliability_status || "nieznana"}</span>
                  </td>
                  <td>
                    {camera.has_ptz ? "PTZ" : "PTZ niedostępne"} / {camera.has_audio ? "Audio" : "Brak audio"}
                  </td>
                  <td>{cameraStreams.map((stream) => stream.stream_name).join(", ") || "brak"}</td>
                  <td>
                    <button className="text-button" onClick={() => onFocus(camera.id)}>
                      Powiększ
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StreamsView({ streams }: { streams: Stream[] }) {
  const [preview, setPreview] = useState<string | null>(null);
  return (
    <section className="surface">
      <div className="section-heading">
        <div>
          <h3>Strumienie</h3>
          <p>Otwieramy odtwarzacz po nazwie strumienia. RTSP i hasła zostają poza frontendem.</p>
        </div>
      </div>
      <div className="stream-list">
        {streams.map((stream) => {
          const isLoaded = preview === stream.stream_name;
          return (
            <article className="stream-row" key={stream.stream_name}>
              <div>
                <strong>{stream.stream_name}</strong>
                <span className="muted-block">
                  {stream.camera_name} / {qualityLabel(qualityRoleForStream(stream))} / {stream.resolution || "-"} /{" "}
                  {stream.video_codec || "-"}
                </span>
                {stream.warnings.length ? <p className="warning-text">{stream.warnings.join(" ")}</p> : null}
              </div>
              <div className="row-actions wrap">
                <button className="ghost-button" onClick={() => setPreview(isLoaded ? null : stream.stream_name)}>
                  {isLoaded ? "Ukryj podgląd" : "Załaduj podgląd"}
                </button>
                <button className="ghost-button" onClick={() => void navigator.clipboard.writeText(stream.stream_name)}>
                  Kopiuj nazwę
                </button>
                <a className="primary-link" href={buildGo2RtcPlayerUrl(GO2RTC_PUBLIC_URL, stream.stream_name)} target="_blank" rel="noreferrer">
                  Otwórz w odtwarzaczu
                </a>
              </div>
              {isLoaded ? <StreamPlayer stream={stream} /> : null}
            </article>
          );
        })}
      </div>
      {!streams.length ? <EmptyState title="Brak strumieni" body="Zaimportuj probe i wygeneruj runtime go2rtc." /> : null}
    </section>
  );
}

function EventsView({ payload, cameras, locations }: { payload: FrigateEventsResponse | null; cameras: Camera[]; locations: Location[] }) {
  const [cameraFilter, setCameraFilter] = useState("");
  const [labelFilter, setLabelFilter] = useState("");
  const [locationFilter, setLocationFilter] = useState("all");
  const cameraBySlug = new Map(cameras.map((camera) => [camera.slug, camera]));
  const events = payload?.events || [];
  const filtered = events.filter((event) => {
    const camera = event.camera ? cameraBySlug.get(event.camera.replace("_lens2", "")) : undefined;
    return (
      (!cameraFilter || event.camera === cameraFilter) &&
      (!labelFilter || (event.label || event.type || "").toLowerCase().includes(labelFilter.toLowerCase())) &&
      (locationFilter === "all" || String(camera?.location_id) === locationFilter)
    );
  });
  return (
    <section className="surface">
      <div className="section-heading">
        <div>
          <h3>Zdarzenia</h3>
          <p>Zdarzenia z lokalnego Frigate przez backend panelu.</p>
        </div>
        <div className="row-actions wrap">
          <select value={locationFilter} onChange={(event) => setLocationFilter(event.target.value)}>
            <option value="all">Wszystkie lokalizacje</option>
            {locations.map((location) => (
              <option key={location.id} value={String(location.id)}>
                {location.name}
              </option>
            ))}
          </select>
          <select value={cameraFilter} onChange={(event) => setCameraFilter(event.target.value)}>
            <option value="">Wszystkie kamery</option>
            {cameras.map((camera) => (
              <option key={camera.id} value={camera.slug}>
                {camera.name}
              </option>
            ))}
          </select>
          <input value={labelFilter} onChange={(event) => setLabelFilter(event.target.value)} placeholder="Filtr etykiety" />
        </div>
      </div>
      {!payload?.reachable ? <InlineAlert tone="warn" title="Frigate offline" body={payload?.error || "Nie załadowano zdarzeń."} /> : null}
      {payload?.reachable && !filtered.length ? <EmptyState title={t("events.emptyTitle")} body={t("events.emptyBody")} /> : null}
      <EventList events={filtered} emptyBody={t("events.emptyBody")} />
    </section>
  );
}

function RecordingsView({ payload, cameras }: { payload: FrigateRecordingsResponse | null; cameras: Camera[] }) {
  const [cameraFilter, setCameraFilter] = useState("");
  const recordings = payload?.recordings || [];
  const filtered = cameraFilter ? recordings.filter((recording) => recording.camera === cameraFilter) : recordings;
  const grouped = groupRecordingsByDay(filtered);
  return (
    <section className="surface">
      <div className="section-heading">
        <div>
          <h3>Nagrania</h3>
          <p>{t("nvr.detectRecord")}</p>
        </div>
        <select value={cameraFilter} onChange={(event) => setCameraFilter(event.target.value)}>
          <option value="">Wszystkie kamery</option>
          {cameras.map((camera) => (
            <option key={camera.id} value={camera.slug}>
              {camera.name}
            </option>
          ))}
        </select>
      </div>
      <InlineAlert
        tone="warn"
        title="HEVC/H.265"
        body="Odtwarzanie nagrań może zależeć od przeglądarki. H.264 fallback jest odłożony na kolejny etap."
      />
      <StorageRetentionNotice />
      {!payload?.reachable ? <InlineAlert tone="warn" title="Frigate offline" body={payload?.error || "Nie załadowano nagrań."} /> : null}
      {payload?.reachable && !filtered.length ? <EmptyState title={t("recordings.emptyTitle")} body={t("recordings.emptyBody")} /> : null}
      <div className="recording-groups">
        {Object.entries(grouped).map(([day, items]) => (
          <section key={day}>
            <h4>{day}</h4>
            {items.map((recording, index) => (
              <article className="event-row" key={recording.id || index}>
                <div>
                  <strong>{recording.camera || "kamera"}</strong>
                  <span className="muted-block">
                    {formatTimestamp(recording.start_time)} - {formatTimestamp(recording.end_time)}
                  </span>
                </div>
                <a className="ghost-link" href={FRIGATE_PUBLIC_URL} target="_blank" rel="noreferrer">
                  Otwórz lokalnie
                </a>
              </article>
            ))}
          </section>
        ))}
      </div>
    </section>
  );
}

function StorageRetentionNotice() {
  return (
    <div className="storage-retention">
      <KeyValue label="Nagrania lokalne" value="Frigate" />
      <KeyValue label="Retencja" value="1-2 dni" />
      <KeyValue label="Tryb" value="zdarzenia" />
      <KeyValue label="Dysk" value="brak danych" />
      <p>Szczegółowy monitoring dysku będzie dodany w kolejnym etapie.</p>
    </div>
  );
}

function LocationsView({ locations, cameras }: { locations: Location[]; cameras: Camera[] }) {
  return (
    <section className="surface">
      <h3>Lokalizacje</h3>
      <div className="location-grid">
        {locations.map((location) => (
          <div className="key-value" key={location.id}>
            <span>{location.slug}</span>
            <strong>{location.name}</strong>
            <p className="muted">{cameras.filter((camera) => camera.location_id === location.id).length} kamer</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function DiagnosticsView({
  cameras,
  streams,
  go2rtcHealth,
  frigateHealth
}: {
  cameras: Camera[];
  streams: Stream[];
  go2rtcHealth: Go2RtcHealth | null;
  frigateHealth: FrigateHealth | null;
}) {
  const unstable = cameras.filter((camera) => camera.reliability_status === "unstable");
  const hevcWarnings = streams.flatMap((stream) => stream.warnings).filter((warning) => warning.includes("HEVC"));
  return (
    <section className="content-stack">
      <section className="surface">
        <h3>Diagnostyka</h3>
        <div className="detail-grid">
          <KeyValue label="go2rtc" value={go2rtcHealth?.reachable ? "działa" : "offline"} />
          <KeyValue label="Frigate" value={frigateHealth?.reachable ? "działa" : "offline"} />
          <KeyValue label="Strumienie" value={go2rtcHealth?.stream_count ?? "nieznane"} />
          <KeyValue label="Niestabilne kamery" value={unstable.map((camera) => camera.slug).join(", ") || "brak"} />
          <KeyValue label="Ostrzeżenia HEVC" value={hevcWarnings.length} />
        </div>
      </section>
      <InlineAlert
        tone="info"
        title="Root Cause Lab"
        body="Aby znaleźć przyczynę lagów, uruchom najpierw szybki smoke: .\\scripts\\root_cause_stream_lab.ps1 -Quick -OnlyGo2rtc -SkipNetwork -VideoOnly. Pełny test 120 s trwa około 10+ min. Instrukcja: docs/root-cause-stream-lab.md."
      />
      <InlineAlert tone="warn" title="Logi" body="Nie wklejaj raw docker logs z go2rtc. Użyj scripts/go2rtc_logs_sanitized.ps1." />
      <InlineAlert tone="info" title="H8 101" body="H8 jest pominięta, dopóki brakuje CAMERA101_PASSWORD." />
      <InlineAlert tone="warn" title="C8C 102" body="C8C 102 pozostaje niestabilna i nie jest domyślnie włączona do NVR." />
      <InlineAlert tone="info" title="Tryb lokalny" body="go2rtc i Frigate są dostępne lokalnie. Etap 6A z publicznym dostępem jest odłożony." />
    </section>
  );
}

function SettingsView() {
  return (
    <section className="surface">
      <h3>Ustawienia</h3>
      <p>Konfiguracja produkcyjnego dostępu, wielu użytkowników i publicznego HTTPS jest odłożona na osobny etap.</p>
    </section>
  );
}

function EventList({ events, emptyBody, compact = false }: { events: FrigateEvent[]; emptyBody: string; compact?: boolean }) {
  if (!events.length) {
    return <EmptyState title={t("events.emptyTitle")} body={emptyBody} />;
  }
  return (
    <div className={compact ? "event-list compact" : "event-list"}>
      {events.map((event, index) => {
        const eventId = event.id || `event-${index}`;
        const thumbUrl = event.id && (event.has_snapshot || event.has_clip) ? sanitizeNvrUrl(`${FRIGATE_PUBLIC_URL}/api/events/${event.id}/thumbnail.jpg`) : "";
        const clipUrl = event.id && event.has_clip ? sanitizeNvrUrl(`${FRIGATE_PUBLIC_URL}/api/events/${event.id}/clip.mp4`) : "";
        return (
          <article className="event-card" key={eventId}>
            <div className="event-thumb">{thumbUrl ? <img src={thumbUrl} alt="" /> : <span>Brak miniatury</span>}</div>
            <div>
              <strong>{event.label || event.type || "zdarzenie"}</strong>
              <span className="muted-block">
                {event.camera || "-"} / {formatTimestamp(event.start_time)} / wynik {formatScore(event.score ?? event.top_score)}
              </span>
            </div>
            {clipUrl ? (
              <a className="ghost-link" href={clipUrl} target="_blank" rel="noreferrer">
                Otwórz klip
              </a>
            ) : (
              <span className="muted">Brak klipu</span>
            )}
          </article>
        );
      })}
    </div>
  );
}

function StatusChips({ camera, stream, recording }: { camera: Camera; stream?: Stream; recording: boolean }) {
  const chips = [
    camera.video_status === "ok" ? "NA ŻYWO" : "BRAK OBRAZU",
    stream?.video_codec?.toLowerCase().includes("hevc") ? "HEVC" : "",
    camera.has_ptz ? "PTZ" : "",
    camera.has_audio ? "AUDIO" : "",
    recording ? "REC" : "",
    camera.reliability_status === "unstable" ? "NIESTABILNA" : ""
  ].filter(Boolean);
  return (
    <div className="chip-row">
      {chips.map((chip) => (
        <span className="badge info" key={chip}>
          {chip}
        </span>
      ))}
    </div>
  );
}

function Segmented({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmented-wrap">
      <span>{label}</span>
      <div className="segmented">
        {options.map(([optionValue, optionLabel]) => (
          <button key={optionValue} className={value === optionValue ? "active" : ""} onClick={() => onChange(optionValue)}>
            {optionLabel}
          </button>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function HealthCard({ title, ok, detail }: { title: string; ok: boolean; detail: string }) {
  return (
    <div className="health-card">
      <span className={ok ? "status-light good" : "status-light warn"} />
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function HealthPill({ label, ok }: { label: string; ok: boolean }) {
  return <span className={ok ? "status-pill good" : "status-pill warn"}>{label}: {ok ? "OK" : "Offline"}</span>;
}

function KeyValue({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong>{value ?? "-"}</strong>
    </div>
  );
}

function InlineAlert({ tone, title, body }: { tone: "info" | "warn" | "bad"; title: string; body: string }) {
  return (
    <div className={`alert ${tone}`}>
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="skeleton-stack">
      <div />
      <div />
      <div />
    </div>
  );
}

function filterCameras(
  cameras: Camera[],
  streams: Stream[],
  policiesBySlug: Map<string, RecordingPolicy>,
  filters: { search: string; locationFilter: string; statusFilter: StatusFilter }
): Camera[] {
  const search = filters.search.trim().toLowerCase();
  return cameras.filter((camera) => {
    const cameraStreams = streamsForCamera(camera.id, streams);
    const policy = policiesBySlug.get(camera.slug);
    const matchesSearch =
      !search ||
      camera.name.toLowerCase().includes(search) ||
      camera.slug.toLowerCase().includes(search) ||
      camera.model.toLowerCase().includes(search);
    const matchesLocation = filters.locationFilter === "all" || String(camera.location_id) === filters.locationFilter;
    const matchesStatus =
      filters.statusFilter === "all" ||
      (filters.statusFilter === "online" && camera.enabled) ||
      (filters.statusFilter === "video_ok" && camera.video_status === "ok") ||
      (filters.statusFilter === "unstable" && camera.reliability_status === "unstable") ||
      (filters.statusFilter === "no_video" && ["failed", "unavailable"].includes(camera.video_status)) ||
      (filters.statusFilter === "ptz" && camera.has_ptz) ||
      (filters.statusFilter === "recording" && Boolean(policy?.enabled));
    return matchesSearch && matchesLocation && matchesStatus && (cameraStreams.length > 0 || filters.statusFilter !== "video_ok");
  });
}

function streamsForCamera(cameraId: number, streams: Stream[]): Stream[] {
  return streams.filter((stream) => stream.camera_id === cameraId);
}

function eventsForCamera(camera: Camera, events: FrigateEvent[]): FrigateEvent[] {
  return events.filter((event) => event.camera === camera.slug || event.camera === `${camera.slug}_lens2`);
}

function recordingsForCamera(camera: Camera, recordings: FrigateRecording[]): FrigateRecording[] {
  return recordings.filter((recording) => recording.camera === camera.slug || recording.camera === `${camera.slug}_lens2`);
}

function eventsForFocusLens(camera: Camera, events: FrigateEvent[], lens: StreamLens): FrigateEvent[] {
  if (lens === "lens2") {
    const lensEvents = events.filter((event) => event.camera === `${camera.slug}_lens2`);
    return lensEvents.length ? lensEvents : events;
  }
  const lens1Events = events.filter((event) => event.camera === camera.slug);
  return lens1Events.length ? lens1Events : events;
}

function recordingsForFocusLens(camera: Camera, recordings: FrigateRecording[], lens: StreamLens): FrigateRecording[] {
  if (lens === "lens2") {
    const lensRecordings = recordings.filter((recording) => recording.camera === `${camera.slug}_lens2`);
    return lensRecordings.length ? lensRecordings : recordings;
  }
  const lens1Recordings = recordings.filter((recording) => recording.camera === camera.slug);
  return lens1Recordings.length ? lens1Recordings : recordings;
}

function layoutLimit(layout: LayoutChoice): number {
  if (layout === "auto") {
    return 6;
  }
  return Number(layout);
}

function profileLabel(profile: PreviewProfile): string {
  if (profile === "high") {
    return "Wysoka";
  }
  if (profile === "fast") {
    return "Szybka";
  }
  return "Auto";
}

function formatTimestamp(value: number | undefined): string {
  if (!value) {
    return "-";
  }
  return new Date(value * 1000).toLocaleString("pl-PL");
}

function formatScore(value: number | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return value.toFixed(2);
}

function eventLabel(event: FrigateEvent): string {
  const raw = (event.label || event.type || "ruch").toLowerCase();
  if (raw.includes("person")) {
    return "Osoba";
  }
  if (raw.includes("car") || raw.includes("vehicle")) {
    return "Pojazd";
  }
  if (raw.includes("motion")) {
    return "Ruch";
  }
  return event.label || event.type || "Ruch";
}

function formatFps(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return value % 1 === 0 ? String(value) : value.toFixed(1);
}

function keyboardCommand(event: KeyboardEvent): PtzCommand | "close" | null {
  if (event.key === "Escape") {
    return "close";
  }
  if (event.key === "ArrowUp") {
    return "up";
  }
  if (event.key === "ArrowDown") {
    return "down";
  }
  if (event.key === "ArrowLeft") {
    return "left";
  }
  if (event.key === "ArrowRight") {
    return "right";
  }
  if (event.key === "+" || event.key === "=") {
    return "zoom_in";
  }
  if (event.key === "-" || event.key === "_") {
    return "zoom_out";
  }
  if (event.key === " ") {
    return "stop";
  }
  return null;
}

function commandLabelPl(command: PtzCommand): string {
  return {
    up: "góra",
    down: "dół",
    left: "lewo",
    right: "prawo",
    zoom_in: "zoom +",
    zoom_out: "zoom -",
    stop: "stop"
  }[command];
}

function groupRecordingsByDay(recordings: FrigateRecording[]): Record<string, FrigateRecording[]> {
  return recordings.reduce<Record<string, FrigateRecording[]>>((groups, recording) => {
    const day = recording.start_time ? new Date(recording.start_time * 1000).toLocaleDateString("pl-PL") : "Bez daty";
    groups[day] = groups[day] || [];
    groups[day].push(recording);
    return groups;
  }, {});
}

function loadSavedLayouts(): SavedLiveLayout[] {
  try {
    const raw = window.localStorage.getItem(liveLayoutsKey);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return sanitizeSavedLayouts(parsed);
  } catch {
    return [];
  }
}

function loadDisplayNames(): DisplayNameMaps {
  return {
    cameraDisplayNames: loadSafeNameMap(cameraDisplayNamesKey),
    tileDisplayNames: loadSafeNameMap(tileDisplayNamesKey)
  };
}

function loadSafeNameMap(key: string): Record<string, string> {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed)
        .map(([nameKey, value]) => [sanitizeDisplayName(nameKey), sanitizeDisplayName(String(value || ""))])
        .filter(([nameKey, value]) => nameKey && value)
    );
  } catch {
    return {};
  }
}

function loadPtzTargetLens(): Record<string, PtzTargetLens> {
  try {
    const raw = window.localStorage.getItem(ptzTargetLensKey);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).flatMap(([cameraSlug, value]) => {
        const safeSlug = sanitizeDisplayName(cameraSlug);
        return safeSlug && (value === "lens1" || value === "lens2" || value === "unknown") ? [[safeSlug, value as PtzTargetLens]] : [];
      })
    );
  } catch {
    return {};
  }
}

function updatePolicyState(setPolicies: (updater: (items: RecordingPolicy[]) => RecordingPolicy[]) => void, policy: RecordingPolicy) {
  setPolicies((items) =>
    items.some((item) => item.camera_id === policy.camera_id)
      ? items.map((item) => (item.camera_id === policy.camera_id ? policy : item))
      : [...items, policy]
  );
}
