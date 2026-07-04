const pl = {
  "app.name": "EZVIZ Panel",
  "app.localOnly": "Tryb lokalny / VPN",
  "common.auto": "Auto",
  "common.fast": "Szybka",
  "common.high": "Wysoka",
  "common.loading": "Ładowanie",
  "common.error": "Błąd",
  "common.retry": "Ponów",
  "common.refresh": "Odśwież",
  "common.logout": "Wyloguj",
  "common.close": "Zamknij",
  "common.save": "Zapisz",
  "common.open": "Otwórz",
  "common.copyName": "Kopiuj nazwę",
  "common.unavailable": "niedostępne",
  "common.unknown": "nieznane",
  "events.emptyTitle": "Brak zdarzeń",
  "events.emptyBody": "Przejdź przed kamerą, żeby sprawdzić detekcję.",
  "recordings.emptyTitle": "Brak nagrań",
  "recordings.emptyBody": "Frigate nie zwrócił jeszcze nagrań dla wybranych filtrów.",
  "ptz.disabled": "PTZ niedostępne",
  "ptz.safeNudge": "Bezpieczny ruch",
  "ptz.stop": "Stop",
  "ptz.up": "Góra",
  "ptz.down": "Dół",
  "ptz.left": "Lewo",
  "ptz.right": "Prawo",
  "ptz.zoomIn": "Zoom +",
  "ptz.zoomOut": "Zoom -",
  "quality.auto": "Auto",
  "quality.fast": "Szybka",
  "quality.high": "Wysoka",
  "quality.main": "Wysoka",
  "quality.sub": "Szybka",
  "quality.unknown": "Nieznana",
  "status.online": "Online",
  "status.offline": "Offline",
  "status.videoOk": "Obraz OK",
  "status.noVideo": "Brak obrazu",
  "status.unstable": "Niestabilna",
  "status.failed": "Błąd",
  "status.partial": "Częściowo",
  "status.unknown": "Nieznany",
  "nvr.engineNote": "Frigate jest silnikiem NVR. Główny panel operatora to EZVIZ Panel.",
  "nvr.detectRecord": "Detekcja: szybki strumień. Nagrania: wysoka jakość, jeśli MAIN istnieje."
} as const;

export type TranslationKey = keyof typeof pl;

export type ViewKey =
  | "dashboard"
  | "live"
  | "cameras"
  | "streams"
  | "events"
  | "recordings"
  | "locations"
  | "diagnostics"
  | "settings"
  | "nvr";

export function t(key: TranslationKey): string {
  return pl[key];
}

export function viewLabel(view: string): string {
  const labels: Record<ViewKey, string> = {
    dashboard: "Pulpit",
    live: "Konsola podglądu",
    cameras: "Kamery",
    streams: "Strumienie",
    events: "Zdarzenia",
    recordings: "Nagrania",
    locations: "Lokalizacje",
    diagnostics: "Diagnostyka",
    settings: "Ustawienia",
    nvr: "NVR"
  };
  return labels[view as ViewKey] || view;
}
