import { memo, useEffect, useMemo, useRef, useState } from "react";
import { GO2RTC_PUBLIC_URL } from "./config";
import {
  buildOperatorTiles,
  selectTileStream,
  tileFallbackNotice,
  type OperatorTile,
  type TileStatusFilter
} from "./liveTiles";
import { displayNameForTile, playerAudioPolicy, type DisplayNameMaps } from "./operatorPreferences";
import { qualityLabel, qualityRoleForStream, type PreviewProfile, type StreamLens } from "./streamLinks";
import {
  activePreviewLimitOptions,
  buildLiveTilePlayerIdentity,
  liveTileClassName,
  liveTilePlaybackMode,
  operatorWallDefaults,
  streamStabilityStatus,
  tileRequiresManualLoad,
  tilePreviewLoadState,
  type ActivePreviewLimit
} from "./streamStability";
import { cameraStatusBadge } from "./status";
import type { Camera, RecordingPolicy, Stream } from "./types";

type LayoutChoice = "auto" | "1" | "2" | "4" | "6" | "9" | "custom";

type LiveWallConsoleProps = {
  cameras: Camera[];
  allCameraCount: number;
  streams: Stream[];
  locationMap: Map<number, string>;
  policiesBySlug: Map<string, RecordingPolicy>;
  layout: LayoutChoice;
  onLayout: (layout: LayoutChoice) => void;
  displayNames: DisplayNameMaps;
  onFocus: (cameraId: number, lens?: StreamLens) => void;
};

export function LiveWallConsole({
  cameras,
  allCameraCount,
  streams,
  locationMap,
  policiesBySlug,
  layout,
  onLayout,
  displayNames,
  onFocus
}: LiveWallConsoleProps) {
  const [activePreviewLimit, setActivePreviewLimit] = useState<ActivePreviewLimit>(operatorWallDefaults.activePreviewLimit);
  const [manualTileLoads, setManualTileLoads] = useState<Set<string>>(() => new Set());
  const tileResult = useMemo(
    () =>
      buildOperatorTiles(cameras, streams, policiesBySlug, {
        separateLenses: operatorWallDefaults.separateLenses,
        showNoVideoInGrid: operatorWallDefaults.showNoVideoInGrid,
        statusFilter: normalizeTileStatusFilter(operatorWallDefaults.statusFilter)
      }),
    [cameras, streams, policiesBySlug]
  );
  const orderedTiles = tileResult.tiles;
  const effectiveProfile = operatorWallDefaults.previewProfile;
  const visibleTiles = orderedTiles.slice(0, layoutLimit(layout));
  const hiddenCount = Math.max(orderedTiles.length - visibleTiles.length, 0);

  function focusTile(tile: OperatorTile) {
    onFocus(tile.camera_id, tile.lens === "lens2" ? "lens2" : "lens1");
  }

  function loadTileManually(tileId: string) {
    setManualTileLoads((current) => new Set([...current, tileId]));
  }

  return (
    <section className="content-stack">
      <div className="console-toolbar video-wall-toolbar stable-wall-toolbar">
        <Segmented
          label="Układ"
          value={layout === "custom" ? "auto" : layout}
          options={[
            ["auto", "Auto"],
            ["1", "1"],
            ["2", "2"],
            ["4", "4"],
            ["6", "6"],
            ["9", "9"]
          ]}
          onChange={(value) => onLayout(value as LayoutChoice)}
        />
        <label className="field-inline">
          <span>Aktywne podglądy</span>
          <select value={activePreviewLimit} onChange={(event) => setActivePreviewLimit(event.target.value as ActivePreviewLimit)}>
            {activePreviewLimitOptions
              .filter((option) => option.value !== "unlimited")
              .map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
          </select>
        </label>
      </div>

      <div className="quality-help stable-wall-note">
        <span>Podgląd stabilny: szybkie streamy SUB, MSE/MJPEG, audio wyłączone.</span>
      </div>

      <div className="live-wall-layout">
        <div className="live-wall-main">
          <div className={`camera-grid video-wall layout-${layout === "auto" || layout === "custom" ? "4" : layout}`}>
            {visibleTiles.map((tile, index) => {
              const manuallyLoaded = manualTileLoads.has(tile.tile_id);
              const loadState = tilePreviewLoadState({
                index,
                limit: activePreviewLimit,
                manuallyLoaded,
                requiresManualLoad: tileRequiresManualLoad(tile)
              });
              return (
                <RawLiveTile
                  key={tile.tile_id}
                  tile={tile}
                  locationName={locationMap.get(tile.camera.location_id) || "Lokalizacja nieznana"}
                  displayName={displayNameForTile(tile, displayNames)}
                  profile={effectiveProfile}
                  loadState={loadState}
                  onManualLoad={() => loadTileManually(tile.tile_id)}
                  onFocus={() => focusTile(tile)}
                />
              );
            })}
          </div>
          {!visibleTiles.length ? <EmptyState title="Brak kamer" body="Filtry nie zwracają kamer do podglądu." /> : null}
        </div>
      </div>

      {hiddenCount ? (
        <InlineAlert
          tone="warn"
          title="Limit podglądu"
          body={`Pokazuję ${visibleTiles.length} z ${orderedTiles.length} okien, żeby nie ładować za wielu streamów naraz. Łącznie w bazie: ${allCameraCount}.`}
        />
      ) : null}
    </section>
  );
}

const RawLiveTile = memo(function RawLiveTile({
  tile,
  displayName,
  locationName,
  profile,
  loadState,
  onManualLoad,
  onFocus
}: {
  tile: OperatorTile;
  displayName: string;
  locationName: string;
  profile: PreviewProfile;
  loadState: ReturnType<typeof tilePreviewLoadState>;
  onManualLoad: () => void;
  onFocus: () => void;
}) {
  const stream = selectTileStream(tile, profile, "grid");
  const playbackMode = liveTilePlaybackMode(tile, stream);
  const playerIdentity = useMemo(
    () =>
      buildLiveTilePlayerIdentity({
        baseUrl: GO2RTC_PUBLIC_URL,
        tileId: tile.tile_id,
        streamName: stream?.stream_name || null,
        audio: operatorWallDefaults.audio,
        mode: playbackMode,
        reloadToken: 0
      }),
    [playbackMode, stream?.stream_name, tile.tile_id]
  );
  const shouldRenderPlayer = Boolean(stream && loadState.active);
  const pausedReason = !stream ? "Brak obrazu" : loadState.requiresManualLoad && !loadState.active ? "Kliknij, aby zaladowac" : "Podglad wstrzymany";

  return (
    <article className={liveTileClassName({ hasStream: Boolean(stream), paused: loadState.paused, rawMonitorMode: operatorWallDefaults.rawMonitorMode })}>
      <div className="camera-preview live-tile-preview raw-live-preview">
        {shouldRenderPlayer ? <iframe title={stream?.stream_name} src={playerIdentity.src} allow="fullscreen" loading="eager" /> : null}
        {shouldRenderPlayer ? <button className="raw-tile-open" type="button" onClick={onFocus} aria-label={`Otworz szczegoly ${displayName}`} /> : null}
        {!shouldRenderPlayer ? (
          <div className="preview-placeholder paused raw-placeholder" onClick={stream ? onManualLoad : undefined}>
            <strong>{displayName}</strong>
            <span>{pausedReason}</span>
            <button className="ghost-button" onClick={stream ? onManualLoad : onFocus}>
              {stream ? "Kliknij, aby zaladowac" : "Ponow"}
            </button>
          </div>
        ) : null}
        <div className="raw-tile-caption">
          <strong>{displayName}</strong>
          <span>{locationName}</span>
        </div>
      </div>
    </article>
  );
});

const liveTileMountCounts = new Map<string, number>();

const LiveTile = memo(function LiveTile({
  tile,
  displayName,
  locationName,
  profile,
  loadState,
  onManualLoad,
  onFocus
}: {
  tile: OperatorTile;
  displayName: string;
  locationName: string;
  profile: PreviewProfile;
  loadState: ReturnType<typeof tilePreviewLoadState>;
  onManualLoad: () => void;
  onFocus: () => void;
}) {
  const articleRef = useRef<HTMLElement | null>(null);
  const mountCountRef = useRef(incrementTileMountCount(tile.tile_id));
  const lastSrcRef = useRef("");
  const [reloadToken, setReloadToken] = useState(0);
  const [lastLoadedAt, setLastLoadedAt] = useState("");
  const [lastError, setLastError] = useState("");
  const [playerState, setPlayerState] = useState<"connecting" | "loaded" | "unstable" | "missing">("connecting");
  const [isInViewport, setIsInViewport] = useState(true);
  const stream = selectTileStream(tile, profile, "grid");
  const audioPolicy = playerAudioPolicy({
    surface: "grid",
    hasAudio: Boolean(stream?.has_audio || tile.camera.has_audio),
    requestedAudio: false
  });
  const playbackMode = liveTilePlaybackMode(tile, stream);
  const playerIdentity = useMemo(
    () =>
      buildLiveTilePlayerIdentity({
        baseUrl: GO2RTC_PUBLIC_URL,
        tileId: tile.tile_id,
        streamName: stream?.stream_name || null,
        audio: operatorWallDefaults.audio,
        mode: playbackMode,
        reloadToken
      }),
    [playbackMode, reloadToken, stream?.stream_name, tile.tile_id]
  );
  const fallback = tileFallbackNotice(tile, profile);
  const status = cameraStatusBadge(tile.camera);
  const stability = streamStabilityStatus({ slug: tile.camera_slug, reliabilityStatus: tile.camera.reliability_status });
  const shouldRenderPlayer = Boolean(stream && loadState.active && isInViewport);
  const pausedReason = !stream
    ? "Brak obrazu"
    : loadState.requiresManualLoad && !loadState.active
      ? "Niestabilna kamera - kliknij, aby załadować"
      : !loadState.active
        ? "Podgląd wstrzymany"
        : !isInViewport
          ? "Podgląd poza ekranem"
          : "";
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
    setReloadToken((value) => value + 1);
    setLastError("");
    setPlayerState("connecting");
  }

  return (
    <article ref={articleRef} className={liveTileClassName({ hasStream: Boolean(stream), paused: loadState.paused })}>
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
        <div className="tile-hover-panel">
          <div className="tile-actions">
            <button className="primary-button small" onClick={onFocus}>
              Powiększ
            </button>
            <button className="ghost-button" onClick={retryPlayer}>
              Ponów
            </button>
          </div>
          <div className="tile-details">
            <span>Lokalizacja: {locationName}</span>
            <span>Status: {status.label}</span>
            <span>Stabilność: {stability.label}</span>
            <span>Jakość: {qualityText}</span>
            <span>Stream: {stream?.stream_name || "-"}</span>
            <span>FPS: {formatFps(stream?.fps)}</span>
            <span>{audioPolicy.label}</span>
            <span>Mount: {mountCountRef.current}</span>
            <span>Ostatnio: {lastLoadedAt || "-"}</span>
            <span>Błąd: {lastError || "-"}</span>
          </div>
          {fallback ? <p className="warning-text">{fallback}</p> : null}
        </div>
      </div>
    </article>
  );
});

function incrementTileMountCount(tileId: string): number {
  const next = (liveTileMountCounts.get(tileId) || 0) + 1;
  liveTileMountCounts.set(tileId, next);
  return next;
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

function layoutLimit(layout: LayoutChoice): number {
  if (layout === "auto" || layout === "custom") {
    return 6;
  }
  return Number(layout);
}

function normalizeTileStatusFilter(filter: string): TileStatusFilter {
  return filter === "all" ? "all" : (filter as TileStatusFilter);
}

function formatFps(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "-";
  }
  return value % 1 === 0 ? String(value) : value.toFixed(1);
}
