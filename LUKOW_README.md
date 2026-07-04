# Panel kamer - Lukow local install

## Pierwsze uruchomienie

1. Rozpakuj ZIP do np. `C:\KAMERY_PANEL`.
2. Kliknij `INSTALL_LUKOW.bat`.
   - Instalator sprobuje doinstalowac FFmpeg przez `winget`, jezeli nie ma go w PATH.
   - Awaryjnie mozesz kliknac `INSTALL_FFMPEG_LUKOW.bat`.
   - Instalator seeduje lokalne kamery Lukow do bazy bez hasel: H9C 98, C8W 97 i C8C 60 jako disabled/diagnostic.
3. Uzupelnij lokalne pliki, ktore nie ida do GitHuba:
   - `secrets.local.env` - verification codes / hasla kamer,
   - `cameras.local.yml` - hosty kamer w lokalnym LAN, jesli robisz probe.
4. Kliknij `START_PANEL_LUKOW.bat`.

Adresy lokalne:

- Panel: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- go2rtc: `http://127.0.0.1:1984`
- Frigate: `http://127.0.0.1:5000`

## Aktualizacja z GitHuba

Kliknij:

```powershell
UPDATE_LUKOW.bat
```

Skrypt pobiera `https://github.com/niewczas13-lang/kamery.git`, resetuje pliki projektu do brancha `main`, instaluje zaleznosci i renderuje runtime configi.

Lokalne pliki `.env`, `secrets.local.env`, `cameras.local.yml` i `runtime/` zostaja poza Gitem.

## Testy streamow

Szybki test go2rtc:

```powershell
TEST_STREAMY_LUKOW.bat
```

Direct RTSP bez go2rtc, Frigate i panelu:

```powershell
TEST_DIRECT_LUKOW.bat
```

Nie wklejaj raw logow go2rtc. Uzywaj `scripts\go2rtc_logs_sanitized.ps1`.

## Wazne dla C8C 60

C8C 60 jest wyjeta z domyslnego smoke walla i domyslnego Frigate/NVR. Direct RTSP pokazal, ze kamera/link potrafi zrywac stream bez udzialu panelu. Otwieraj ja recznie do testow, dopoki lokalny link w Lukowie nie bedzie stabilny.
