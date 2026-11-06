# LivingroomOS

LivingroomOS macht aus einem Debian-13-Rechner für x86_64-PCs einen Fernseher-Launcher: Der
Rechner bootet ohne Desktop direkt in eine große, mit Fernbedienung oder Tastatur bedienbare Oberfläche. konfigurierbare Web-Apps und lokale Mediatheken laufen als getrennte Anwendungen daneben, immer nur eine gleichzeitig.

- **Frontend:** HTML5, CSS3, Vanilla-JavaScript (ES-Module), kein Framework, kein Build-Schritt
- **Backend:** Python 3 mit FastAPI und Uvicorn, nur auf `127.0.0.1`
- **Fenster:** Compositor `labwc` (Wayland), Anmeldung über `greetd`, Browser `google-chrome-stable`, Dienste über `systemd`

> **Status: Prototyp, Version 0.6.0.** Backend-Logik, Prozessmanagement und Navigation sind mit echten Prozessen und
> einem echten Browser getestet. Die Systemdateien in `system/` (greetd, labwc, systemd) und die Wiedergabe in
> Streaming-Anbieter sind **noch nicht auf echter Hardware geprüft**. Details: Abschnitt „Teststatus“.

## Schnellstart zum Ausprobieren (Entwicklung)

Voraussetzung: Linux mit Python ≥ 3.11 und den Bibliotheken `fastapi` und `uvicorn`. Auf Debian 13 am einfachsten:

```bash
sudo apt install python3 python3-fastapi python3-uvicorn
./run.sh
```

Danach im Browser `http://127.0.0.1:8750` öffnen. Navigation mit Pfeiltasten, Enter und Escape. Die Testprozesse „Demo-App“ und „Absturz-Test“ befinden sich im Einstellungsbereich unter „Debug“.

Alternativ mit virtueller Umgebung (Pakete von PyPI):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh        # nutzt .venv automatisch, falls vorhanden
```

`run.sh` startet nur das Backend, schreibt nichts außerhalb des Projektordners und nutzt Port 8750
(`LIVINGROOMOS_PORT=9000 ./run.sh` ändert ihn). Browserprofile und Logs der Apps landen unter
`~/.local/share/livingroomos/`.

Die vollständige Einrichtung als Fernseher-Appliance (Autologin, Kiosk, Dienste) steht in [INSTALL.md](INSTALL.md).

## Bedienung

| Taste | Wirkung |
| --- | --- |
| Pfeiltasten | Fokus bewegen (räumlich, nächstes Element in Pfeilrichtung) |
| Enter, Leertaste | Öffnen / Bestätigen |
| Escape, Backspace, Zurück-Taste der Fernbedienung | Zurück, Dialog schließen |
| Home-Taste der Fernbedienung | zum Launcher: beendet die laufende App (im Kiosk über labwc, siehe `system/labwc/rc.xml`) |
| Tab | wie „nächstes Element“ (nicht nötig) |

Eine Maus wird nicht gebraucht. Neue Fernbedienungen werden in [frontend/js/remote.js](frontend/js/remote.js) mit einer
Zeile zugeordnet; die Seite `frontend/dev/navigation-demo.html` zeigt, welche Tastencodes ein Gerät sendet.

## Tests

```bash
cd backend
python3 -B -m unittest discover -s tests -v
```

| Datei | Prüft | Braucht |
| --- | --- | --- |
| `test_process_management.py` | Start, Stopp, Absturz, Doppelstart, Rechteprüfungen, Übernahme nach Backend-Absturz | Standardbibliothek |
| `test_settings_store.py` | Laden, Fehlermeldungen, atomares und paralleles Speichern | Standardbibliothek |
| `test_livingroomosctl.py` | Tastenkürzel-Werkzeug gegen Testserver | Standardbibliothek |
| `test_project_consistency.py` | Konfiguration, Abhängigkeiten, x86_64-Zielarchitektur, Dokumentation | Standardbibliothek |
| `test_api.py` | HTTP-Schnittstelle, Sicherheitsheader, Fehlerformat | `fastapi`, `httpx` (sonst übersprungen) |

Für `test_api.py`: `sudo apt install python3-httpx` oder `pip install -r requirements-dev.txt`.
Ohne Installation prüft `python3 tools/check_system.py`, was auf dem System fehlt.

## Projektstruktur

```
livingroomos/
├── README.md  INSTALL.md  ARCHITECTURE.md  CHANGELOG.md
├── requirements.txt            Python-Abhängigkeiten (Laufzeit)
├── requirements-dev.txt        zusätzlich für Tests
├── debian-packages.txt         Debian-Pflichtpakete
├── debian-packages-optional.txt
├── run.sh                      startet das Backend
├── backend/
│   ├── main.py                 App, Lifespan, Sicherheits-Middleware, Frontend ausliefern
│   ├── version.py              einzige Quelle der Versionsnummer
│   ├── api/                    apps.py, system.py, settings.py (dünne REST-Router)
│   ├── services/               process_manager.py, app_launcher.py, settings_store.py
│   ├── config/settings.json    Apps, Serverwerte, Oberflächeneinstellungen
│   └── tests/
├── frontend/
│   ├── index.html  css/  js/   app.js, navigation.js, remote.js, api.js
│   └── dev/                    Demo und Tastentest für die Navigation (ohne Backend nutzbar)
├── system/                     Dateien für den Fernseher-Betrieb (nur Dateien, kein Code)
│   ├── greetd/  labwc/  systemd/user/  chrome/  polkit/  bin/
├── tools/check_system.py       Systemprüfung (nur x86_64)
└── docs/                       SICHERHEIT.md, SYSTEMABHAENGIGKEITEN.md
```

## Konfiguration

Alle Apps stehen in `backend/config/settings.json` (im Fernseher-Betrieb: `~/.config/livingroomos/settings.json`).
Das Frontend sendet nur die App-ID; Programm und Parameter kommen ausschließlich aus dieser Datei.

```json
{
  "id": "webapp-one",
  "title": "Streaming-App 1",
  "command": ["google-chrome-stable", "--app=https://example.com/", "--user-data-dir={profile_dir}",
              "--ozone-platform=wayland", "--start-fullscreen"]
}
```

Regeln (werden beim Laden geprüft, ungültige Einträge übersprungen und in `/api/v1/system/status` unter
`config_problems` gemeldet):

- `command` ist eine Liste, nie ein Text. Es gibt keine Shell.
- Erlaubte Platzhalter: `{python}` (der Python-Interpreter des Backends) und `{profile_dir}` (eigenes Profil dieser App).
- Browser müssen `{profile_dir}` verwenden, jede App bekommt ein eigenes Profil.
- Programme werden nur in `server.trusted_bin_dirs` gesucht und müssen `root` oder dem Dienstbenutzer gehören und
  dürfen für Gruppe und Andere nicht beschreibbar sein.
- Verboten sind unter anderem `--no-sandbox`, `--remote-debugging-*`, `--disable-web-security`; ebenso `LD_*`-Variablen.

Alle Gründe und Berechtigungen: [docs/SICHERHEIT.md](docs/SICHERHEIT.md).

## Einstellungen und Systemaktionen

Die Einstellungen sind in die Bereiche **Allgemein**, **System** und **Debug** gegliedert. Allgemein enthält Uhrzeitformat,
Uhranzeige, Kachelgröße, App-Beschreibungen und reduzierte Animationen. System enthält die Bestätigung vor Power-Aktionen
sowie **PC neu starten** und **PC herunterfahren**. Die beiden eingebauten Testprozesse erscheinen ausschließlich im
Debug-Bereich. Power-Aktionen sind serverseitig auf die beiden festen systemd-Befehle begrenzt; die Polkit-Regel erteilt
nur dem dedizierten Dienstkonto die nötige Berechtigung.

## HTTP-Schnittstelle

Nur `127.0.0.1`; schreibende Aufrufe brauchen den Header `X-LivingroomOS: 1`. Fehler haben das Format
`{"error": {"code": "...", "message": "..."}}`.

| Methode und Pfad | Zweck |
| --- | --- |
| `GET /api/v1/health` | Bereitschaft |
| `GET /api/v1/system/status` | Version, Laufzeit, Architektur, Konfigurationsprobleme, App-Status |
| `GET /api/v1/apps` | App-Liste (ohne Befehle) und Status |
| `GET /api/v1/apps/status` | Status: `state`, `app_id`, `pid`, `last_exit` |
| `POST /api/v1/apps/{id}/launch` | App starten (202; 409 wenn eine andere läuft) |
| `POST /api/v1/apps/stop` | laufende App beenden |
| `POST /api/v1/apps/{id}/stop` | nur diese App beenden (409, wenn sie nicht läuft) |
| `GET /api/v1/settings`, `PATCH /api/v1/settings` | Oberflächeneinstellungen (`ui`) |\n| `POST /api/v1/system/power/restart` | kontrollierter Neustart |\n| `POST /api/v1/system/power/shutdown` | kontrolliertes Herunterfahren |

## Teststatus

| Bereich | Stand |
| --- | --- |
| Prozessmanagement, Einstellungen, Konfigurationsprüfung, `livingroomosctl` | automatisch getestet, echte Prozesse |
| Oberfläche und Navigation | im echten Google Chrome getestet (1920×1080), 41 + 39 Prüfungen in der Entwicklung |
| HTTP-Schnittstelle (`main.py`, `api/*.py`) | Tests geschrieben (`test_api.py`), in der Entwicklungsumgebung **nicht ausgeführt**, weil dort kein `fastapi` installierbar war. Bitte nach der Installation einmal ausführen. |
| `system/` (greetd, labwc, systemd, Google Chrome-Richtlinien) | **ungetestet**, nach Dokumentation der Programme geschrieben |
| Streaming-Anbieter (Widevine), Hardware-Videodekodierung, ARM | **nicht unterstützt** |

## Dokumente

- [INSTALL.md](INSTALL.md) – Debian-13-Installation Schritt für Schritt
- [ARCHITECTURE.md](ARCHITECTURE.md) – Aufbau, Entscheidungen und Abweichungen vom ursprünglichen Entwurf
- [CHANGELOG.md](CHANGELOG.md) – alle Änderungen
- [docs/SICHERHEIT.md](docs/SICHERHEIT.md) – Sicherheitskonzept, Berechtigungen
- [docs/SYSTEMABHAENGIGKEITEN.md](docs/SYSTEMABHAENGIGKEITEN.md) – Debian-Pakete, Kernel, Verzeichnisse
