import { memo, useEffect, useMemo, useRef, useState } from "react";
import { FRIGATE_PUBLIC_URL, GO2RTC_PUBLIC_URL } from "./config";
import {
  buildOperatorTiles,
  orderedTileIdsForLayout,
  defaultSavedLayouts,
  selectTileStream,
  tileFallbackNotice,
  visibleTileIdsForLayout,
  type NoVideoCamera,
  type OperatorTile,
  type SavedLiveLayout,
  type TileStatusFilter
} from "./liveTiles";
import { sanitizeNvrUrl } from "./nvr";
import { createSavedLayoutFromTiles, displayNameForTile, playerAudioPolicy, type DisplayNameMaps } from "./operatorPreferences";
import { qualityLabel, qualityRoleForStream, type PreviewProfile, type StreamLens } from "./streamLinks";
import {
  activePreviewLimitCount,
  activePreviewLimitOptions,
  buildLiveTilePlayerIdentity,
  effectivePreviewProfile,
  streamStabilityStatus,
  tilePreviewLoadState,
  type ActivePreviewLimit
} from "./streamStability";
import { cameraStatusBadge } from "./status";
import type { Camera, FrigateEvent, RecordingPolicy, Stream } from "./types";

type LayoutChoice = "auto" | "1" | "2" | "4" | "6" | "9" | "custom";
type StatusFilter = "all" | "online" | "video_ok" | "unstable" | "no_video" | "ptz" | "recording";

type LiveWallConsoleProps = {
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
  separateLenses: boolean;
  onSeparateLenses: (value: boolean) => void;
  showNoVideoInGrid: boolean;
  onShowNoVideoInGrid: (value: boolean) => void;
  customLayouts: SavedLiveLayout[];
  activeLayoutId: string;
  onActiveLayoutId: (id: string) => void;
  onCustomLayouts: (layouts: SavedLiveLayout[]) => void;
  displayNames: DisplayNameMaps;
  fullscreenMode: boolean;
  monitorMode: boolean;
  ecoMode: boolean;
  onFullscreenMode: (value: boolean) => void;
  onMonitorMode: (value: boolean) => void;
  onEcoMode: (value: boolean) => void;
  onRenameTile: (tile: OperatorTile) => void;
  onResetTileName: (tile: OperatorTile) => void;
  onFocus: (cameraId: number, lens?: StreamLens) => void;
  onSnapshot: (cameraId: number) => void;
};

export function LiveWallConsole({
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
  separateLenses,
  onSeparateLenses,
  showNoVideoInGrid,
  onShowNoVideoInGrid,
  customLayouts,
  activeLayoutId,
  onActiveLayoutId,
  onCustomLayouts,
  displayNames,
  fullscreenMode,
  monitorMode,
  ecoMode,
  onFullscreenMode,
  onMonitorMode,
  onEcoMode,
  onRenameTile,
  onResetTileName,
  onFocus,
  onSnapshot
}: LiveWallConsoleProps) {
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [layoutEditorOpen, setLayoutEditorOpen] = useState(false);
  const [eventCameraFilter, setEventCameraFilter] = useState("");
  const [streamDiagnosticsOpen, setStreamDiagnosticsOpen] = useState(false);
  const [activePreviewLimit, setActivePreviewLimit] = useState<ActivePreviewLimit>("4");
  const [manualTileLoads, setManualTileLoads] = useState<Set<string>>(() => new Set());
  const tileResult = useMemo(
    () => buildOperatorTiles(cameras, streams, policiesBySlug, { separateLenses, showNoVideoInGrid, statusFilter: normalizeTileStatusFilter(statusFilter) }),
    [cameras, streams, policiesBySlug, separateLenses, showNoVideoInGrid, statusFilter]
  );
  const defaultLayouts = useMemo(() => defaultSavedLayouts(tileResult.tiles), [tileResult.tiles]);
  const layouts = [...defaultLayouts, ...customLayouts];
  const activeLayout = layouts.find((item) => item.id === activeLayoutId) || layouts[0];
  const tileById = new Map(tileResult.tiles.map((tile) => [tile.tile_id, tile]));
  const allOrderedIds = activeLayout ? orderedTileIdsForLayout(activeLayout, tileResult.tiles) : tileResult.tiles.map((tile) => tile.tile_id);
  const visibleOrderedIds = activeLayout ? visibleTileIdsForLayout(activeLayout, tileResult.tiles) : tileResult.tiles.map((tile) => tile.tile_id);
  const allOrderedTiles = allOrderedIds.map((id) => tileById.get(id)).filter(Boolean) as OperatorTile[];
  const orderedTiles = visibleOrderedIds.map((id) => tileById.get(id)).filter(Boolean) as OperatorTile[];
  const selectedProfile = monitorMode && consoleProfile === "high" ? "auto" : consoleProfile;
  const effectiveProfile = effectivePreviewProfile(selectedProfile, ecoMode);
  const selectedActiveLimit = monitorMode && activePreviewLimitCount(activePreviewLimit) > 4 ? "4" : activePreviewLimit;
  const visibleTiles = layout === "custom" ? orderedTiles : orderedTiles.slice(0, layoutLimit(layout));
  const hiddenCount = Math.max(orderedTiles.length - visibleTiles.length, 0);
  const highQualityWarning = effectiveProfile === "high" && visibleTiles.length > 4;
  const unlimitedWarning = selectedActiveLimit === "unlimited";

  function saveCurrentLayout() {
    const next = createSavedLayoutFromTiles({
      id: `custom-${Date.now()}`,
      name: "Własny układ",
      tiles: allOrderedTiles.length ? allOrderedTiles : tileResult.tiles,
      hiddenTileIds: activeLayout?.hiddenTileIds || [],
      layoutSize: layout,
      qualityMode: effectiveProfile,
      separateLenses
    });
    onCustomLayouts([...customLayouts, next]);
    onActiveLayoutId(next.id);
    onLayout("custom");
  }

  function restoreDefaultLayout() {
    onActiveLayoutId("all");
    onLayout("auto");
    onConsoleProfile("auto");
  }

  function mutateWorkingLayout(mutator: (layout: SavedLiveLayout) => SavedLiveLayout) {
    const current =
      customLayouts.find((item) => item.id === activeLayoutId) ||
      ({
        id: `custom-${Date.now()}`,
        name: "Własny układ",
        tileIds: allOrderedTiles.map((tile) => tile.tile_id),
        hiddenTileIds: []
      } satisfies SavedLiveLayout);
    const next = mutator(current);
    onCustomLayouts([...customLayouts.filter((item) => item.id !== current.id), next]);
    onActiveLayoutId(next.id);
    onLayout("custom");
  }

  function moveTile(tileId: string, direction: -1 | 1) {
    mutateWorkingLayout((current) => {
      const ids = orderedTileIdsForLayout(current, tileResult.tiles);
      const index = ids.indexOf(tileId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= ids.length) {
        return current;
      }
      const nextIds = [...ids];
      [nextIds[index], nextIds[target]] = [nextIds[target], nextIds[index]];
      return { ...current, tileIds: nextIds };
    });
  }

  function toggleTile(tileId: string) {
    mutateWorkingLayout((current) => {
      const hidden = new Set(current.hiddenTileIds);
      if (hidden.has(tileId)) {
        hidden.delete(tileId);
      } else {
        hidden.add(tileId);
      }
      return { ...current, tileIds: orderedTileIdsForLayout(current, tileResult.tiles), hiddenTileIds: [...hidden] };
    });
  }

  function focusTile(tile: OperatorTile) {
    onFocus(tile.camera_id, tile.lens === "lens2" ? "lens2" : "lens1");
  }

  function loadTileManually(tileId: string) {
    setManualTileLoads((current) => new Set([...current, tileId]));
  }

  return (
    <section className="content-stack">
      <div className="console-toolbar video-wall-toolbar">
        {!monitorMode ? (
          <>
            <Segmented
              label="Układ"
              value={layout}
              options={[
                ["auto", "Auto"],
                ["1", "1"],
                ["2", "2"],
                ["4", "4"],
                ["6", "6"],
                ["9", "9"],
                ["custom", "Własny"]
              ]}
              onChange={(value) => onLayout(value as LayoutChoice)}
            />
            <Segmented
              label="Jakość"
              value={effectiveProfile}
              options={[
                ["auto", "Auto"],
                ["fast", "Szybka"],
                ["high", "Wysoka"]
              ]}
              onChange={(value) => onConsoleProfile(value as PreviewProfile)}
            />
            <select value={statusFilter} onChange={(event) => onStatusFilter(event.target.value as StatusFilter)}>
              <option value="all">Wszystkie</option>
              <option value="online">Online</option>
              <option value="ptz">PTZ</option>
              <option value="recording">Nagrywane</option>
              <option value="unstable">Niestabilne</option>
              <option value="no_video">Brak obrazu</option>
            </select>
            <select value={activeLayoutId} onChange={(event) => onActiveLayoutId(event.target.value)}>
              {layouts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            <label className="toggle-row">
              <input type="checkbox" checked={separateLenses} onChange={(event) => onSeparateLenses(event.target.checked)} />
              <span>Obiektywy jako osobne okna</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={showNoVideoInGrid} onChange={(event) => onShowNoVideoInGrid(event.target.checked)} />
              <span>Pokaż kamery bez obrazu w gridzie</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={streamDiagnosticsOpen} onChange={(event) => setStreamDiagnosticsOpen(event.target.checked)} />
              <span>Pokaż diagnostykę streamów</span>
            </label>
            <label className="toggle-row">
              <input type="checkbox" checked={ecoMode} onChange={(event) => onEcoMode(event.target.checked)} />
              <span>Tryb oszczędny</span>
            </label>
            <label className="field-inline">
              <span>Maksymalna liczba aktywnych podglądów</span>
              <select value={activePreviewLimit} onChange={(event) => setActivePreviewLimit(event.target.value as ActivePreviewLimit)}>
                {activePreviewLimitOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button className="ghost-button" onClick={saveCurrentLayout}>
              Zapisz układ
            </button>
            <button className="ghost-button" onClick={() => setLayoutEditorOpen((value) => !value)}>
              {layoutEditorOpen ? "Zamknij edycję" : "Edytuj układ"}
            </button>
            <button className="ghost-button" onClick={restoreDefaultLayout}>
              Przywróć domyślny
            </button>
          </>
        ) : (
          <span className="monitor-badge">Tryb monitora: video wall i zdarzenia, audio wyłączone</span>
        )}
        <button className={fullscreenMode ? "primary-button small" : "ghost-button"} onClick={() => onFullscreenMode(!fullscreenMode)}>
          {fullscreenMode ? "Wyjdź z pełnego ekranu" : "Tryb pełnoekranowy"}
        </button>
        <button className={monitorMode ? "primary-button small" : "ghost-button"} onClick={() => onMonitorMode(!monitorMode)}>
          Tryb monitora
        </button>
        <button className="ghost-button" onClick={() => setDrawerOpen((value) => !value)}>
          {drawerOpen ? "Ukryj zdarzenia" : "Pokaż zdarzenia"}
        </button>
      </div>

      <div className="quality-help">
        <span>Jakość: {profileLabel(effectiveProfile)}</span>
        <button
          className="help-dot"
          title="Auto: w gridzie używa szybkiego strumienia, w powiększeniu wysokiej jakości. Szybka: używa SUB. Wysoka: używa MAIN, jeśli jest dostępny."
          aria-label="Opis profili jakości"
        >
          ?
        </button>
        <span>W konsoli podglądu kamery są domyślnie wyciszone</span>
      </div>
      {monitorMode ? (
        <InlineAlert tone="info" title="Tryb monitora" body="Panele edycji są ukryte, a wszystkie kafelki pozostają wyciszone." />
      ) : null}
      {highQualityWarning ? (
        <InlineAlert tone="warn" title="Wysoka jakość" body="Wysoka jakość dla wielu kamer może obciążyć sieć i komputer." />
      ) : null}
      {ecoMode ? (
        <InlineAlert tone="info" title="Tryb oszczędny" body="Ładuję tylko pierwsze dwa aktywne podglądy, wymuszam szybką jakość i zostawiam audio wyłączone." />
      ) : null}
      {unlimitedWarning ? (
        <InlineAlert tone="warn" title="Bez limitu" body="Bez limitu może powodować lagi przy HEVC/H.265." />
      ) : null}

      <div className={drawerOpen ? "live-wall-layout with-drawer" : "live-wall-layout"}>
        <div className="live-wall-main">
          <div className={`camera-grid video-wall layout-${layout === "auto" || layout === "custom" ? "4" : layout}`}>
            {visibleTiles.map((tile, index) => {
              const loadState = tilePreviewLoadState({
                index,
                limit: selectedActiveLimit,
                manuallyLoaded: manualTileLoads.has(tile.tile_id),
                ecoMode
              });
              return (
                <LiveTile
                  key={tile.tile_id}
                  tile={tile}
                  locationName={locationMap.get(tile.camera.location_id) || "Lokalizacja nieznana"}
                  lastEvent={eventsForCamera(tile.camera, events)[0]}
                  displayName={displayNameForTile(tile, displayNames)}
                  profile={effectiveProfile}
                  monitorMode={monitorMode || fullscreenMode}
                  showDiagnostics={streamDiagnosticsOpen}
                  loadState={loadState}
                  onManualLoad={() => loadTileManually(tile.tile_id)}
                  onFocus={() => focusTile(tile)}
                  onRename={() => onRenameTile(tile)}
                  onResetName={() => onResetTileName(tile)}
                  onSnapshot={() => onSnapshot(tile.camera_id)}
                />
              );
            })}
          </div>
          {!visibleTiles.length ? <EmptyState title="Brak kamer" body="Filtry nie zwracają kamer do podglądu." /> : null}
          <NoVideoPanel cameras={tileResult.noVideoCameras} />
          {!monitorMode && layoutEditorOpen ? (
            <LayoutManager
              tiles={allOrderedTiles}
              activeLayout={activeLayout}
              displayNames={displayNames}
              onMove={moveTile}
              onToggle={toggleTile}
              onSave={saveCurrentLayout}
            />
          ) : null}
        </div>
        {drawerOpen ? (
          <EventDrawer
            events={events.slice(0, 24)}
            cameraFilter={eventCameraFilter}
            onCameraFilter={setEventCameraFilter}
            onFocus={(slug) => focusEventCamera(slug, tileResult.tiles, onFocus)}
          />
        ) : null}
      </div>

      {hiddenCount ? (
        <InlineAlert
          tone="warn"
          title="Limit podglądu"
          body={`Pokazuję ${visibleTiles.length} z ${orderedTiles.length} pasujących okien. To ogranicza automatyczne ładowanie wielu strumieni. Łącznie w bazie: ${allCameraCount}.`}
        />
      ) : null}
    </section>
  );
}

const liveTileMountCounts = new Map<string, number>();

const LiveTile = memo(function LiveTile({
  tile,
  displayName,
  locationName,
  lastEvent,
  profile,
  monitorMode,
  showDiagnostics,
  loadState,
  onManualLoad,
  onFocus,
  onRename,
  onResetName,
  onSnapshot
}: {
  tile: OperatorTile;
  displayName: string;
  locationName: string;
  lastEvent?: FrigateEvent;
  profile: PreviewProfile;
  monitorMode: boolean;
  showDiagnostics: boolean;
  loadState: ReturnType<typeof tilePreviewLoadState>;
  onManualLoad: () => void;
  onFocus: () => void;
  onRename: () => void;
  onResetName: () => void;
  onSnapshot: () => void;
}) {
  const articleRef = useRef<HTMLElement | null>(null);
  const mountCountRef = useRef(incrementTileMountCount(tile.tile_id));
  const lastSrcRef = useRef("");
  const [reloadToken, setReloadToken] = useState(0);
  const [reloadCount, setReloadCount] = useState(0);
  const [srcChanges, setSrcChanges] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState("");
  const [lastError, setLastError] = useState("");
  const [playerState, setPlayerState] = useState<"connecting" | "loaded" | "unstable" | "missing">("connecting");
  const [isInViewport, setIsInViewport] = useState(true);
  const stream = selectTileStream(tile, profile, "grid");
  const audioPolicy = playerAudioPolicy({ surface: monitorMode ? "monitor" : "grid", hasAudio: Boolean(stream?.has_audio || tile.camera.has_audio), requestedAudio: false });
  const playerIdentity = useMemo(
    () =>
      buildLiveTilePlayerIdentity({
        baseUrl: GO2RTC_PUBLIC_URL,
        tileId: tile.tile_id,
        streamName: stream?.stream_name || null,
        audio: audioPolicy.playerAudio,
        reloadToken
      }),
    [audioPolicy.playerAudio, reloadToken, stream?.stream_name, tile.tile_id]
  );
  const fallback = tileFallbackNotice(tile, profile);
  const status = cameraStatusBadge(tile.camera);
  const stability = streamStabilityStatus({ slug: tile.camera_slug, reliabilityStatus: tile.camera.reliability_status });
  const shouldRenderPlayer = Boolean(stream && loadState.active && isInViewport);
  const pausedReason = !stream ? "Brak obrazu" : !loadState.active ? "Podgląd wstrzymany" : !isInViewport ? "Podgląd poza ekranem" : "";
  const qualityText = stream ? qualityLabel(qualityRoleForStream(stream)) : "-";

  useEffect(() => {
    if (!("IntersectionObserver" in window)) {
      setIsInViewport(true);
      return;
    }
    const node = articleRef.current;
    if (!node) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        setIsInViewport(Boolean(entries[0]?.isIntersecting));
      },
      { rootMargin: "180px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!playerIdentity.src) {
      setPlayerState("missing");
      lastSrcRef.current = "";
      return;
    }
    if (lastSrcRef.current && lastSrcRef.current !== playerIdentity.src) {
      setSrcChanges((value) => value + 1);
    }
    lastSrcRef.current = playerIdentity.src;
    if (shouldRenderPlayer) {
      setPlayerState("connecting");
    }
  }, [playerIdentity.src, shouldRenderPlayer]);

  function retryPlayer() {
    if (!stream) {
      onFocus();
      return;
    }
    setReloadCount((value) => value + 1);
    setReloadToken((value) => value + 1);
    setLastError("");
    setPlayerState("connecting");
  }

  return (
    <article ref={articleRef} className={stream ? `camera-card live-tile${lastEvent ? " has-event" : ""}` : "camera-card live-tile no-video"}>
      <div className="camera-preview live-tile-preview">
        <div className="stream-skeleton">
          <span>Łączenie...</span>
        </div>
        {shouldRenderPlayer ? (
          <iframe
            title={stream?.stream_name}
            src={playerIdentity.src}
            allow="fullscreen"
            onLoad={() => {
              setPlayerState("loaded");
              setLastLoadedAt(new Date().toLocaleTimeString("pl-PL"));
              setLastError("");
            }}
            onError={() => {
              setPlayerState("unstable");
              setLastError("Błąd ładowania playera");
            }}
          />
        ) : (
          <div className="preview-placeholder paused" onClick={stream ? onManualLoad : undefined}>
            <strong>{displayName}</strong>
            <span>{pausedReason}</span>
            <button className="ghost-button" onClick={stream ? onManualLoad : onFocus}>
              {stream ? "Kliknij, aby załadować" : "Ponów"}
            </button>
          </div>
        )}
        {shouldRenderPlayer && playerState === "unstable" ? (
          <div className="tile-state unstable">
            <strong>Stream niestabilny</strong>
            <button className="ghost-button" onClick={retryPlayer}>
              Ponów
            </button>
          </div>
        ) : null}
        {shouldRenderPlayer && playerState === "connecting" ? <span className="tile-state connecting">Łączenie...</span> : null}
        <div className="tile-gradient" />
        <div className="tile-caption">
          <div>
            <h3>{displayName}</h3>
            <span className="muted-block">{tile.title}</span>
            {tile.is_dual_lens && tile.lens === "combined" ? <span className="badge info">2 obiektywy</span> : null}
          </div>
          <div className="chip-row">
            {tile.badges.map((badge) => (
              <span className={`badge ${badge === "REC" ? "rec" : "info"}`} key={badge}>
                {badge}
              </span>
            ))}
          </div>
        </div>
        {lastEvent ? <TileEventOverlay event={lastEvent} /> : null}
        <div className="tile-hover-panel">
          <div className="tile-actions">
            <button className="primary-button small" onClick={onFocus}>
              Powiększ
            </button>
            <button className="ghost-button" onClick={onSnapshot}>
              Zrzut
            </button>
            <button className="ghost-button" onClick={onFocus}>
              Sterowanie
            </button>
            <button className="ghost-button" onClick={onFocus}>
              Zdarzenia
            </button>
            <button className="ghost-button" onClick={onRename}>
              Zmień nazwę
            </button>
            <button className="ghost-button" onClick={onResetName}>
              Reset nazwy
            </button>
            <button className="ghost-button" onClick={retryPlayer}>
              Ponów
            </button>
          </div>
          <div className="tile-tech">
            <span>Jakość: {qualityText}</span>
            <span>Stream: {stream ? qualityRoleForStream(stream).toUpperCase() : "-"}</span>
            <span>Rozdzielczość: {stream?.resolution || "-"}</span>
            <span>FPS: {formatFps(stream?.fps)}</span>
            <span>Kodek: {stream?.video_codec?.toUpperCase() || "-"}</span>
            <span>{audioPolicy.label}</span>
          </div>
          <div className="tile-details">
            <span>Lokalizacja: {locationName}</span>
            <span>Model: {tile.camera.model || "-"}</span>
            <span>Status: {status.label}</span>
            <span>Stabilność: {stability.label}</span>
            <span>Ostatnie zdarzenie: {lastEvent ? `${lastEvent.label || lastEvent.type || "zdarzenie"} ${formatTimestamp(lastEvent.start_time)}` : "brak"}</span>
          </div>
          {fallback ? <p className="warning-text">{fallback}</p> : null}
        </div>
        {showDiagnostics ? (
          <div className="stream-diagnostics-overlay">
            <span>tile_id: {tile.tile_id}</span>
            <span>stream: {stream?.stream_name || "-"}</span>
            <span>jakość: {qualityText}</span>
            <span>aktywny: {loadState.active && isInViewport ? "tak" : "nie"}</span>
            <span>wstrzymany: {!shouldRenderPlayer ? "tak" : "nie"}</span>
            <span>mount count: {mountCountRef.current}</span>
            <span>reload count: {reloadCount}</span>
            <span>src changes: {srcChanges}</span>
            <span>ostatnio załadowany: {lastLoadedAt || "-"}</span>
            <span>ostatni błąd: {lastError || "-"}</span>
            <span>poza limitem: {loadState.overActiveLimit ? "tak" : "nie"}</span>
            <span>poza ekranem: {!isInViewport ? "tak" : "nie"}</span>
            <span>stabilność: {stability.label}</span>
          </div>
        ) : null}
      </div>
    </article>
  );
});

function incrementTileMountCount(tileId: string): number {
  const next = (liveTileMountCounts.get(tileId) || 0) + 1;
  liveTileMountCounts.set(tileId, next);
  return next;
}

function TileEventOverlay({ event }: { event: FrigateEvent }) {
  const thumbUrl = event.id && (event.has_snapshot || event.has_clip) ? sanitizeNvrUrl(`${FRIGATE_PUBLIC_URL}/api/events/${event.id}/thumbnail.jpg`) : "";
  return (
    <div className="tile-event-overlay">
      <span className="event-thumb tiny">{thumbUrl ? <img src={thumbUrl} alt="" /> : "Brak miniatury"}</span>
      <span>
        <strong>Nowe zdarzenie</strong>
        <small>
          {eventLabel(event)} / {formatTimestamp(event.start_time)}
        </small>
      </span>
    </div>
  );
}

function LayoutManager({
  tiles,
  activeLayout,
  displayNames,
  onMove,
  onToggle,
  onSave
}: {
  tiles: OperatorTile[];
  activeLayout: SavedLiveLayout | undefined;
  displayNames: DisplayNameMaps;
  onMove: (tileId: string, direction: -1 | 1) => void;
  onToggle: (tileId: string) => void;
  onSave: () => void;
}) {
  if (!tiles.length) {
    return null;
  }
  return (
    <section className="layout-manager">
      <div className="section-heading compact">
        <div>
          <h3>Zapisane układy</h3>
          <p>Ukryj okna albo zmień kolejność. Zapis jest lokalny w tej przeglądarce.</p>
        </div>
        <button className="ghost-button" onClick={onSave}>
          Ustaw jako domyślny
        </button>
      </div>
      <div className="layout-tile-list">
        {tiles.map((tile, index) => (
          <div className="layout-tile-row" key={tile.tile_id}>
            <label>
              <input type="checkbox" checked={!activeLayout?.hiddenTileIds.includes(tile.tile_id)} onChange={() => onToggle(tile.tile_id)} />
              <span>{displayNameForTile(tile, displayNames)}</span>
            </label>
            <div className="row-actions">
              <button className="text-button" disabled={index === 0} onClick={() => onMove(tile.tile_id, -1)}>
                Góra
              </button>
              <button className="text-button" disabled={index === tiles.length - 1} onClick={() => onMove(tile.tile_id, 1)}>
                Dół
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function NoVideoPanel({ cameras }: { cameras: NoVideoCamera[] }) {
  if (!cameras.length) {
    return null;
  }
  return (
    <section className="no-video-panel">
      <h3>Kamery bez obrazu</h3>
      <div className="no-video-list">
        {cameras.map((camera) => (
          <span key={camera.slug}>
            {camera.name} - {camera.reason}
          </span>
        ))}
      </div>
    </section>
  );
}

function EventDrawer({
  events,
  cameraFilter,
  onCameraFilter,
  onFocus
}: {
  events: FrigateEvent[];
  cameraFilter: string;
  onCameraFilter: (cameraSlug: string) => void;
  onFocus: (cameraSlug: string) => void;
}) {
  const cameras = Array.from(new Set(events.map((event) => event.camera).filter(Boolean))) as string[];
  const filtered = cameraFilter ? events.filter((event) => event.camera === cameraFilter) : events;
  return (
    <aside className="event-drawer-panel">
      <div className="section-heading compact">
        <div>
          <h3>Ostatnie zdarzenia</h3>
          <p>Lokalny pasek zdarzeń z Frigate.</p>
        </div>
        <select value={cameraFilter} onChange={(event) => onCameraFilter(event.target.value)}>
          <option value="">Wszystkie kamery</option>
          {cameras.map((cameraSlug) => (
            <option key={cameraSlug} value={cameraSlug}>
              {cameraSlug}
            </option>
          ))}
        </select>
      </div>
      {!filtered.length ? <EmptyState title="Brak zdarzeń" body="Brak zdarzeń. Przejdź przed kamerę, żeby przetestować detekcję." /> : null}
      <div className="event-drawer-list">
        {filtered.slice(0, 8).map((event, index) => {
          const eventId = event.id || `event-${index}`;
          const thumbUrl = event.id && (event.has_snapshot || event.has_clip) ? sanitizeNvrUrl(`${FRIGATE_PUBLIC_URL}/api/events/${event.id}/thumbnail.jpg`) : "";
          return (
            <button className="drawer-event" key={eventId} onClick={() => event.camera && onFocus(event.camera)}>
              <span className="event-thumb small">{thumbUrl ? <img src={thumbUrl} alt="" /> : "Brak miniatury"}</span>
              <span>
                <strong>{eventLabel(event)}</strong>
                <small>
                  {event.camera || "-"} / {formatTimestamp(event.start_time)} / wynik {formatScore(event.score ?? event.top_score)}
                </small>
              </span>
            </button>
          );
        })}
      </div>
    </aside>
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

function eventsForCamera(camera: Camera, events: FrigateEvent[]): FrigateEvent[] {
  return events.filter((event) => event.camera === camera.slug || event.camera === `${camera.slug}_lens2`);
}

function focusEventCamera(cameraSlug: string, tiles: OperatorTile[], onFocus: (cameraId: number, lens?: StreamLens) => void) {
  const normalized = cameraSlug.replace("_lens2", "");
  const tile = tiles.find((item) => item.camera_slug === normalized && (cameraSlug.endsWith("_lens2") ? item.lens === "lens2" : true));
  if (tile) {
    onFocus(tile.camera_id, tile.lens === "lens2" ? "lens2" : "lens1");
  }
}

function layoutLimit(layout: LayoutChoice): number {
  if (layout === "auto" || layout === "custom") {
    return 6;
  }
  return Number(layout);
}

function normalizeTileStatusFilter(filter: StatusFilter): TileStatusFilter {
  return filter === "video_ok" ? "online" : filter;
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
