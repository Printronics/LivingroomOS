# Changelog

Alle Änderungen an LivingroomOS. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/). Die Versionsnummer steht an genau einer Stelle: `backend/version.py`.

Hinweis: Die Versionen 0.1.0 bis 0.4.0 wurden während der Entwicklung nicht einzeln veröffentlicht. Sie sind hier
nachträglich aus den Entwicklungsschritten abgeleitet, damit jede Änderung nachvollziehbar bleibt. Dateien, die von einem
Schritt betroffen sind, stehen jeweils dabei.

## [0.6.0] – 2026-11-06

### Geändert
- Projekt vollständig in LivingroomOS umbenannt: Verzeichnisse, Dateien, Dienste, Konfiguration, Umgebungsvariablen und API-Header.
- Zielplattform auf Debian 13 `amd64` / x86_64 begrenzt; ARM-Zielprofile und Installationshinweise entfernt.
- Browseraufrufe auf `google-chrome-stable` umgestellt; Chrome wird separat über das offizielle Herstellerpaket installiert und nicht mitgeliefert.
- Standard-Apps auf neutrale, editierbare Web-App-Beispiele umgestellt; keine fremden Logos, Grafiken oder Anbieterassets eingebettet.
- Einstellungsoberfläche in Allgemein, System und Debug gegliedert; zusätzliche Anzeigeoptionen und reduzierte Animationen ergänzt.
- Testanwendungen aus dem Startmenü entfernt und in den Debug-Reiter verschoben.
- Neustart und Herunterfahren über fest erlaubte Backend-Aktionen ergänzt; Berechtigung wird eng auf den LivingroomOS-Dienstbenutzer und die zwei lokalen Power-Aktionen begrenzt.
- Installations-, Abhängigkeits-, Sicherheits- und Architektur-Dokumentation aktualisiert.

### Prüfung
- Konsistenztests: 21/21 bestanden.
- API-/Prozessstarttests in dieser Entwicklungsumgebung teilweise durch die unsicheren Dateirechte des vorgegebenen Python-Virtualenv-Interpreters blockiert; auf einem regulären Debian-13-System erneut ausführen.
- Kiosk-/Power-Integration muss auf echter Hardware geprüft werden.

## [0.5.0] – 2026-11-04

Projekt als eigenständig installierbarer Ordner: Dokumentation, Systemdateien, Abhängigkeitslisten, Tests.

### Hinzugefügt
- `README.md`: Beschreibung, Schnellstart, Bedienung, Tests, Struktur, Konfiguration, HTTP-Schnittstelle, Teststatus.
- `INSTALL.md`: vollständige Installation auf Debian 13 (amd64, x86_64), Prüfung, Fehlersuche, Update, Rückbau.
- `ARCHITECTURE.md`: tatsächlich umgesetzte Architektur; Abweichungen vom ersten Entwurf mit Begründung.
- `CHANGELOG.md`: diese Datei.
- `docs/SYSTEMABHAENGIGKEITEN.md`: alle Debian-Pakete, Kernel- und Python-Anforderungen, Verzeichnisse, Rechte, x86_64-Systemdetails.
- `debian-packages.txt`, `debian-packages-optional.txt`: maschinenlesbare Paketlisten, nur aus dem Debian-Archiv.
- `requirements.txt`, `requirements-dev.txt`: Python-Abhängigkeiten (Laufzeit und Tests), jeweils mit Begründung.
- `backend/version.py`: einzige Quelle der Versionsnummer, genutzt von `main.py` und vom Systemstatus.
- `system/greetd/config.toml`, `system/bin/livingroomos-session`, `system/labwc/autostart`, `system/labwc/rc.xml`,
  `system/systemd/user/livingroomos-backend.service`, `livingroomos-shell.service`, `livingroomos.target`,
  `system/chrome/livingroomos.json`: Dateien für den Fernseher-Betrieb (noch nicht auf Hardware geprüft).
- `system/bin/livingroomosctl`: HTTP-Werkzeug für Tastenkürzel (`home`, `status`, `wait`), nur Standardbibliothek.
- `tools/check_system.py`: Systemprüfung für ausschließlich x86_64, ändert nichts am System.
- Tests: `backend/tests/test_api.py`, `test_settings_store.py`, `test_livingroomosctl.py`, `test_project_consistency.py`.
  Letzterer erzwingt Projektregeln automatisch: jede Python-Abhängigkeit in `requirements.txt`, jedes Debian-Paket
  dokumentiert, keine Architekturnamen im Code, keine Skripte mit Netz-Installation, Pflichtdokumente und Verweise vorhanden.

### Geändert
- `run.sh`: nutzt `.venv`, falls vorhanden; Port über `LIVINGROOMOS_PORT`.
- `backend/main.py`: Konfigurationspfad über `LIVINGROOMOS_CONFIG` einstellbar; Version aus `version.py`.

### Bekannte Einschränkungen
- `test_api.py` wurde in der Entwicklungsumgebung nicht ausgeführt (kein `fastapi` installierbar), nur geschrieben.
- `system/` und die Streaming-Anbieter-Wiedergabe sind auf echter Hardware ungeprüft; ARM wird nicht unterstützt.

## [0.4.0] – 2026-11-04

Navigationssystem für Fernseher.

### Geändert
- `frontend/js/navigation.js`: neu geschrieben als eigenständiges Modul. Räumliche Navigation nach Geometrie, feste Ziele
  über `data-nav-*`, Fokusgedächtnis je Bereich, automatische Fokus-Wiederherstellung, Enter-Sperre nach neuem Dialog,
  Schutz vor Doppelauslösung, Randhinweis, `Tab` als „nächstes Element“.
- `frontend/js/remote.js`: neu geschrieben. Tastenbelegung für Tastatur, HID-Fernbedienungen (`BrowserBack`, `BrowserHome`,
  `ContextMenu`) und TV-Browser (Android TV, Tizen, webOS); Drosselung gehaltener Richtungstasten, Entprellung, kein
  Auslösen durch Auto-Repeat, `bind`/`emit` für neue Fernbedienungen und andere Eingabequellen.
- `frontend/js/app.js`: `next`/`prev`, `data-repeatable` für Einstellungszeilen, Speichern von Einstellungen gegen
  Überholen durch spätere Tastendrücke abgesichert.
- `frontend/css/main.css`: Fokusring als Rückfall für jedes anwählbare Element, Randanimation.
- `frontend/css/layout.css`: `scroll-padding`.

### Hinzugefügt
- `frontend/dev/navigation-demo.html`, `demo.js`, `demo.css`: Demo und Tastentest ohne Backend; zeigt `key`, `code` und
  `keyCode` jeder Taste, um neue Fernbedienungen zuzuordnen.

## [0.3.0] – 2026-11-03

Sicheres Prozessmanagement.

### Hinzugefügt
- `docs/SICHERHEIT.md`: Sicherheitskonzept (Schutzziele, Bedrohungsmodell, Maßnahmen, Berechtigungen, Härtung, Restrisiken).
- `backend/tests/test_process_management.py`: 22 Tests mit echten Prozessen.
- `POST /api/v1/apps/{id}/stop`: beendet nur die genannte App.

### Geändert
- `backend/services/process_manager.py`: neu geschrieben. Prozessgruppe und eigene Sitzung, Identitätsprüfung über
  `/proc`-Startzeit und `pidfd`, Doppelstart-Sperre, Absturzklassifikation (`stopped`, `ok`, `crashed`, `start_failed`,
  `ended`), Nachzüglersuche über exakten `--user-data-dir`-Wert, Logdateien mit Rotation, Backend-Sperre, Zustandsdatei und
  Übernahme nach Backend-Absturz.
- `backend/services/app_launcher.py`: neu geschrieben. Konfigurationsprüfung (Platzhalter, verbotene Schalter, Browser
  brauchen eigenes Profil, Umgebungsvariablen), Pfad-, Besitzer- und Rechteprüfung, vertrauenswürdige Verzeichnisse,
  gefilterte Umgebung, Rückkehr zum Launcher.
- `backend/main.py`: Lebenszyklus mit Sperre und geordnetem Beenden.
- `backend/api/apps.py`: neue Stopp-Route.
- `backend/config/settings.json`: `trusted_bin_dirs`, `startup_grace_s`, `stop_timeout_s`, `return_to_launcher_command`.

## [0.2.0] – 2026-11-03

Lauffähiger Minimalprototyp.

### Hinzugefügt
- Frontend: `frontend/index.html`, `css/main.css`, `css/layout.css`, `js/app.js`, `js/navigation.js`, `js/remote.js`,
  `js/api.js`. Dunkle TV-Oberfläche, große Kacheln, Bedienung mit Pfeiltasten, Enter und Escape, Fokuszustände, Dialoge für
  Start, Absturz und fehlendes Backend.
- Backend: `backend/main.py`, `api/apps.py`, `api/system.py`, `api/settings.py`, `services/app_launcher.py`,
  `services/process_manager.py`, `services/settings_store.py`, `config/settings.json`, `requirements.txt`, `run.sh`.
  Lokale HTTP-Schnittstelle unter `/api/v1`, keine beliebigen Shell-Befehle aus dem Frontend, Fehlerbehandlung für fehlende
  und abgestürzte Dienste.

### Entscheidung
- Statusabfrage statt SSE. Begründung: ARCHITECTURE.md, Abschnitt 11.

## [0.1.0] – 2026-11-02

### Hinzugefügt
- Erste Softwarearchitektur (Dokument, kein Anwendungscode): Module, Verantwortlichkeiten, Kommunikation, Prozessmanagement,
  x86_64-Zielarchitektur, Ressourcen- und Sicherheitsrisiken, begründete Entscheidungen. Ihre Umsetzung und die Abweichungen
  davon beschreibt `ARCHITECTURE.md`.
