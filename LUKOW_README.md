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
   - Domyslnie startuje panel + go2rtc + Frigate/NVR, czyli podglad, nagrania i wykrywanie.
   - Tryb bez NVR tylko awaryjnie: `START_PANEL_LUKOW.bat -SkipFrigate`.
   - Backend i frontend startuja w tle, wiec okno startowe zamknie sie samo.
   - Stopowanie panelu: `STOP_PANEL_LUKOW.bat`.
   - Logi panelu: `runtime\logs\panel\backend.out.log` i `runtime\logs\panel\frontend.out.log`.

Adresy lokalne:

- Panel: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`
- go2rtc: `http://127.0.0.1:1984`
- Frigate/NVR: `http://127.0.0.1:5000`

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

Dluzszy test stabilnosci, gdy kamera dziala chwile i potem zaczyna buforowac albo pada:

```powershell
TEST_STABILITY_LUKOW.bat
```

Domyslnie testuje H9C 98 obiektyw 1, H9C 98 obiektyw 2 i C8W 97: ping/RTSP port, go2rtc sekwencyjnie, go2rtc rownolegle oraz direct RTSP bez go2rtc. To moze potrwac kilkanascie minut, ale pokazuje postep po kazdym streamie.

Wariant szybki:

```powershell
TEST_STABILITY_LUKOW.bat -Quick
```

Wariant mocniejszy, jezeli problem pojawia sie dopiero po kilku minutach:

```powershell
TEST_STABILITY_LUKOW.bat -DurationSeconds 300
```

Nie wklejaj raw logow go2rtc. Uzywaj `scripts\go2rtc_logs_sanitized.ps1`.

## Wazne dla C8C

C8C 60 i C8C 102 sa wlaczone do Frigate/NVR ostroznie: detekcja i nagrania ida po SUB, bez obciazania MAIN. Jezeli po aktualizacji Frigate nadal pokazuje 3 pozycje, uruchom `START_PANEL_LUKOW.bat` ponownie, zeby przegenerowal `runtime\config\frigate\config.yml`.
