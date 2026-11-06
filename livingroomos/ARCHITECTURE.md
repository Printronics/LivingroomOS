# LivingroomOS – Softwarearchitektur

Stand: Version 0.5.0. Dieses Dokument beschreibt, was **tatsächlich implementiert** ist. Wo die Umsetzung vom
ursprünglichen Architekturentwurf abweicht, steht das mit Begründung in Abschnitt 11. Das Sicherheitskonzept steht in
[docs/SICHERHEIT.md](docs/SICHERHEIT.md), die Systempakete in
[docs/SYSTEMABHAENGIGKEITEN.md](docs/SYSTEMABHAENGIGKEITEN.md).

## 1. Zielbild und Leitprinzipien

LivingroomOS ist ein Appliance-System: Ein Debian-13-Rechner bootet ohne Desktop direkt in eine HTML-Oberfläche. Streaming-Anbieter,
Video-Webseiten, eigene Mediathek und andere Dienste laufen als austauschbare Fremdanwendungen daneben. Zur Laufzeit gibt es nur
**Compositor + Browser + einen Python-Dienst**.

1. Das Backend ist die einzige Instanz, die Prozesse startet und beendet. Das Frontend zeigt an und sendet Absichten
   („starte App X“).
2. Es läuft genau ein Vordergrundprogramm gleichzeitig. Das spart Arbeitsspeicher und macht Fokus und Rückkehr eindeutig.
3. Neue Apps entstehen durch einen Eintrag in `settings.json`, nicht durch neuen Code.
4. Alles Hardwarespezifische (x86_64) gehört in Konfiguration und Systempakete, nie in den Code.
5. Der Rückweg zum Launcher funktioniert auch, wenn eine Fremdanwendung hängt oder abstürzt.
6. Keine unnötigen Frameworks: kein Desktop, kein Frontend-Framework, kein Build-Schritt.

| Bereich | Festlegung |
| --- | --- |
| Zielhardware v1 | Intel NUC (x86_64) |
| Zielhardware später | x86_64-PC (Intel/AMD) |
| Betriebssystem | Debian 13 „trixie“, Pakete nur aus dem Debian-Archiv |
| Bedienung | Fernbedienung oder Tastatur (Pfeile, Enter, Zurück, Home), keine Maus |
| Nicht-Ziele v1 | Dateimanager, eigene Mediathek, Mehrbenutzerbetrieb, Fernzugriff über das Netzwerk |

## 2. Gesamtübersicht

```
 Einschalten
     │
     ▼
 systemd ──► greetd ──(initial_session, Benutzer livingroomos)──► livingroomos-session
                                                                  │  startet labwc, bei Absturz neu
                                                                  ▼
                                            labwc (Wayland-Compositor, Kiosk-Konfiguration)
                                                                  │  autostart: systemctl --user start livingroomos.target
                          ┌───────────────────────────────────────┴──────────────────────────┐
                          ▼                                                                   ▼
        livingroomos-backend.service                                              livingroomos-shell.service
        Uvicorn + FastAPI  127.0.0.1:8750                                     Google Chrome --kiosk  →  http://127.0.0.1:8750/
        ┌─────────────────────────────┐                                                      │
        │ api/       REST /api/v1/*   │◄────────── fetch (JSON, X-LivingroomOS) ─────────────────┘
        │ services/  app_launcher     │                                       Frontend: HTML/CSS/Vanilla-JS
        │            process_manager  │                                       remote.js → navigation.js → app.js
        │            settings_store   │
        └──────────────┬──────────────┘
                       │ asyncio.create_subprocess_exec (kein Shell, eigene Prozessgruppe)
                       ▼
        Fremdanwendung: google-chrome-stable --app=… --user-data-dir=<eigenes Profil>   (immer nur eine)
```

Fernbedienungstasten laufen **nicht** über das Backend. Sie erreichen das fokussierte Fenster als Tastaturereignisse über
den Compositor. Nur die Home-Taste ist ein Compositor-Kürzel, das `livingroomosctl home` aufruft (Abschnitt 6).

## 3. Projektstruktur und Verantwortlichkeiten

Es gibt genau einen Ort je Aufgabe. Abhängigkeiten zeigen nur nach unten: `api → services`. Die Dienste kennen weder
FastAPI noch das Frontend.

### 3.1 Backend (`backend/`)

| Modul | Verantwortung | Bewusst nicht zuständig für |
| --- | --- | --- |
| `main.py` | App-Fabrik, Lebenszyklus (Sperre holen, Apps beenden), Host-Prüfung, CSRF-Header, Sicherheitsheader, Fehlerformat, Frontend ausliefern | Geschäftslogik |
| `version.py` | einzige Quelle der Versionsnummer | |
| `api/apps.py` | REST-Router für Apps: Liste, Status, Start, Stopp; übersetzt Ausnahmen in HTTP-Statuscodes | Prozesse, Dateisystem |
| `api/system.py` | `health` und `system/status` (nur lesend) | Systembefehle |
| `api/settings.py` | Oberflächeneinstellungen lesen und ändern (Eingabeprüfung mit Pydantic) | andere Konfigurationsabschnitte |
| `services/app_launcher.py` | übersetzt App-ID in einen geprüften Startbefehl; prüft Konfiguration, Programmpfad, Besitzer, Rechte, Profilordner, Umgebung; Rückkehr-Befehl | Prozessüberwachung |
| `services/process_manager.py` | startet, überwacht und beendet genau ein Programm; Doppelstart-Sperre, Absturzerkennung, Prozessgruppe, Nachzüglersuche, Zustandsdatei, Backend-Sperre | Aufbau der Befehlszeile |
| `services/settings_store.py` | lädt und schreibt `settings.json` (atomar, thread-sicher); nur der Abschnitt `ui` ist schreibbar | Prüfung der Apps |
| `config/settings.json` | Serverwerte, UI-Einstellungen, App-Definitionen | Laufzeitzustand |
| `tests/` | Unit-, Integrations- und Konsistenztests (Abschnitt 9) | |

### 3.2 Frontend (`frontend/`)

| Datei | Verantwortung |
| --- | --- |
| `index.html` | Gerüst: Kopfzeile, Ansichten, Dialog, Toast |
| `css/main.css` | Design-Tokens, Farben, Schrift, Fokuszustände, Dialog |
| `css/layout.css` | Raster, Abstände (berücksichtigen Overscan), Skalierung für 16:9 |
| `js/app.js` | Zustand und Darstellung: Kacheln, Einstellungen, Dialoge, Abfrage des Status, Reaktion auf Abstürze |
| `js/api.js` | `fetch`-Wrapper mit einheitlicher Fehlerbehandlung (`ApiError`) |
| `js/navigation.js` | eigenständig: räumliche Fokusnavigation, Fokus-Wiederherstellung, Schutz vor Doppelauslösung |
| `js/remote.js` | eigenständig: Tasten und Fernbedienungen → Aktionen, Entprellung, Wiederholungsschutz |
| `dev/` | Demo- und Tastentest für die Navigation, ohne Backend nutzbar (kein Teil des Betriebs) |

`app.js` ist der einzige Ort, der `navigation.js`, `remote.js` und `api.js` zusammenbringt. Die beiden
Navigationsmodule kennen weder einander noch die Anwendung.

### 3.3 Sitzungskonfiguration (`system/`, nur Dateien)

| Datei | Zweck |
| --- | --- |
| `greetd/config.toml` | Autologin des Benutzers `livingroomos` in `livingroomos-session`, Textanmeldung als Rückfall |
| `bin/livingroomos-session` | startet labwc, startet ihn nach Abstürzen neu (höchstens 5 in 60 s) |
| `labwc/autostart`, `labwc/rc.xml` | importiert `WAYLAND_DISPLAY`, startet `livingroomos.target`; Kiosk ohne Standardtastenkürzel, Home-Kürzel |
| `systemd/user/*` | `livingroomos-backend.service`, `livingroomos-shell.service`, `livingroomos.target` |
| `google-chrome-stable/livingroomos.json` | Google Chrome-Richtlinien (keine Entwicklerwerkzeuge, kein Passwortmanager, keine Synchronisation) |
| `bin/livingroomosctl` | kleines Werkzeug, spricht nur HTTP mit dem Backend (`home`, `status`, `wait`) |

`tools/check_system.py` prüft ein System auf Voraussetzungen (Architektur, Python, Kernel, Pakete, Konfiguration).

## 4. Kommunikation zwischen Frontend und Backend

Das Frontend spricht ausschließlich mit `http://127.0.0.1:8750`. Befehle sind REST-Aufrufe unter `/api/v1`, der Status
wird abgefragt.

| Methode und Pfad | Zweck | Besondere Antworten |
| --- | --- | --- |
| `GET /api/v1/health` | Bereitschaft (wartet die Shell-Unit ab) | |
| `GET /api/v1/system/status` | Version, Laufzeit, Architektur, Python, `config_problems`, App-Status | |
| `GET /api/v1/apps` | App-Liste (ohne Befehle) und Status | |
| `GET /api/v1/apps/status` | `state`, `app_id`, `pid`, `last_exit` | |
| `POST /api/v1/apps/{id}/launch` | App starten | 202; 404 unbekannt; 409 `busy`; 422 `not_installed` |
| `POST /api/v1/apps/stop` | aktive App beenden | |
| `POST /api/v1/apps/{id}/stop` | nur diese App beenden | 409 `not_running`, wenn sie nicht läuft |
| `GET /api/v1/settings`, `PATCH /api/v1/settings` | Oberflächeneinstellungen (`ui`) | 422 bei unbekannten Schlüsseln |

Regeln:

- **Nur Absichten:** Das Frontend sendet eine App-ID. Programm, Argumente und Umgebung stammen ausschließlich aus
  `settings.json` und sind in der Antwort nie enthalten.
- **Idempotenz:** `launch` für die bereits laufende App liefert denselben Status. `launch` einer anderen App bei laufender
  liefert 409 mit dem aktuellen Status; der Nutzer entscheidet im Dialog.
- **Schreibschutz:** Alle schreibenden Aufrufe brauchen den Header `X-LivingroomOS: 1` (CSRF-Schutz). `TrustedHostMiddleware`
  erlaubt nur `127.0.0.1` und `localhost` (DNS-Rebinding). Antworten tragen eine strikte Content-Security-Policy.
- **Fehlerformat:** `{"error": {"code": "...", "message": "..."}}`, `message` ist für Menschen und nennt keine Interna.
- **Versionierte Pfade** (`/api/v1`), damit ein späteres Netzwerk-Frontend (Handy) kompatibel bleiben kann.
- **Statusabfrage:** 1,2 s während eine App startet oder läuft, 4 s im Leerlauf, mindestens 6 s bei verstecktem Fenster,
  3 s bei Ausfall des Backends. `last_exit.seq` sorgt dafür, dass jedes Ende genau einmal gemeldet wird.

## 5. Prozessmanagement externer Anwendungen

Der Zustandsautomat des `ProcessManager`:

```
 idle ──start()──► starting ──(Startkarenzzeit überschritten)──► running
   ▲                  │                                             │
   │                  └───── Ende innerhalb der Karenzzeit ──────┐  │ stop() oder Ende
   │                                                              ▼  ▼
   └─────────────── Aufräumen, Ende melden (genau einmal) ◄── stopping
```

Ein Start ist nur aus `idle` möglich. Der Zustand wird **vor dem ersten `await` reserviert**, deshalb können auch
gleichzeitige Anfragen keinen Doppelstart auslösen.

**Start.** Der `AppLauncher` baut einen `LaunchSpec` (absoluter, geprüfter Pfad; Argumentliste; gefilterte Umgebung;
Logdatei; Instanzkennung). Der `ProcessManager` ruft `asyncio.create_subprocess_exec` auf: nie eine Shell, `stdin` ist
`/dev/null`, `start_new_session=True` (eigene Sitzung und Prozessgruppe), `umask 0077`, Ausgabe in
`logs/<id>.log` (0600, Rotation bei 1 MiB).

**Überwachung.** Ein Beobachter-Task wartet auf das Ende des Prozesses. Das Ende wird klassifiziert:

| Grund | Bedeutung |
| --- | --- |
| `stopped` | vom Nutzer oder Backend beendet |
| `ok` | Exit-Code 0 nach der Karenzzeit |
| `crashed` | Exit-Code ≠ 0 oder Signal nach der Karenzzeit |
| `start_failed` | Ende innerhalb der Karenzzeit (bei Exit 0 nur, wenn die App dauerhaft laufen sollte) |
| `ended` | übernommene App endete, Ursache unbekannt |

Der Absturzdialog erscheint bei `crashed` und `start_failed`. Bei jedem Ende wird der Zustand `idle`, das Frontend zeigt
den Launcher wieder, und optional holt `return_to_launcher_command` (zum Beispiel `wlrctl`) den Fokus zurück.

**Beenden.** `stop()` sendet SIGTERM an die **Prozessgruppe** der App, nach `stop_timeout_s` SIGKILL. Google Chrome-Renderer, die
die Gruppe verlassen, werden über den exakten Argumentwert `--user-data-dir=<Profil dieser App>` gefunden (nie über den
Programmnamen) und mit `pidfd` beendet. Fremde Browserfenster bleiben dadurch unberührt. Jedes Signal prüft vorher
Besitzer und Startzeit des Prozesses.

**Identität.** Ein Prozess wird über `/proc/<pid>/stat` (Startzeit) und `pidfd_open` identifiziert. PID-Wiederverwendung
führt daher nie zum Beenden eines fremden Prozesses.

**Backend-Absturz.** `state.json` (0600, im RAM unter `$XDG_RUNTIME_DIR`) hält PID und Startzeit der laufenden App. Ein neues
Backend übernimmt sie, wenn diese Daten noch stimmen. Eine Sperrdatei (`flock`) verhindert zwei Backends. Mit dem Standard
`KillMode=control-group` der Unit endet die App allerdings mit dem Backend; die Übernahme ist nur relevant, wenn der
Administrator `KillMode=process` wählt (docs/SICHERHEIT.md).

## 6. Boot- und Startkette

1. Firmware, Bootloader, Kernel, systemd.
2. `greetd` startet beim Boot eine `initial_session` für den Benutzer `livingroomos`. PAM legt eine logind-Sitzung an;
   dadurch gibt es `XDG_RUNTIME_DIR` und einen `systemd --user`-Manager.
3. `livingroomos-session` startet `labwc` in einer Schleife. greetd führt die `initial_session` nur einmal pro Boot aus, deshalb
   steckt die Neustart-Logik im Skript. Nach 5 Abstürzen innerhalb von 60 s endet das Skript, und greetd zeigt die
   Textanmeldung.
4. Der labwc-Autostart importiert `WAYLAND_DISPLAY` in den systemd-Benutzermanager und startet `livingroomos.target`.
5. `livingroomos-backend.service` (Uvicorn), danach `livingroomos-shell.service` (Google Chrome im Kiosk-Modus; wartet per
   `livingroomosctl wait` auf `/api/v1/health`). Beide mit `Restart=on-failure`. Die Shell-Unit hängt nur mit `After=` am
   Backend, damit der Launcher bei einem Backend-Neustart offen bleibt und „Backend nicht erreichbar“ zeigt.

Die **Home-Taste** der Fernbedienung (`XF86HomePage`) ist ein labwc-Kürzel (`rc.xml`) und ruft `livingroomosctl home` auf. Das
sendet `POST /api/v1/apps/stop`. Sendet die Fernbedienung keine Home-Taste, beendet `Strg+Alt+Pos1` die App.

Messziel: Launcher sichtbar in unter 15 s (NUC) beziehungsweise 25 s (Pi). Das ist eine Annahme und noch nicht gemessen.

## 7. Sicherheit (Kurzfassung)

Das Backend lauscht nur auf Loopback und kennt keine Anmeldung, weil jeder, der Zugriff auf `127.0.0.1` hat, bereits Zugriff
auf den Rechner hat. Geschützt wird gegen Fehlbedienung und gegen Webseiten im Browser (CSRF, DNS-Rebinding), nicht gegen
Angreifer am Gerät. Kern der Maßnahmen: nur vordefinierte Programme, keine Shell, geprüfte Pfade und Rechte, gefilterte
Umgebung, getrennte Browserprofile, verbotene Browser-Schalter, gezieltes Beenden. Vollständig: docs/SICHERHEIT.md.

## 8. Zielarchitektur\n\nLivingroomOS unterstützt ausschließlich `amd64` / x86_64. ARM-Prozessoren werden von `tools/check_system.py` abgewiesen.\n
## 9. Tests

| Datei | Prüft |
| --- | --- |
| `test_process_management.py` | echte Prozesse: Start, Stopp, SIGKILL, Prozessgruppe, Absturzarten, Logs, Doppelstart, Rechteprüfung, Profilordner, Nachzüglersuche, Backend-Sperre, Übernahme, PID-Wiederverwendung |
| `test_settings_store.py` | Laden, Fehlermeldungen, atomares und paralleles Speichern |
| `test_livingroomosctl.py` | Werkzeug gegen einen Testserver |
| `test_project_consistency.py` | ausgelieferte Konfiguration, `requirements.txt`, Debian-Paketdokumentation, x86_64-Zielarchitektur, keine Netz-Installationsbefehle, Dokumentation, Verweise |
| `test_api.py` | HTTP-Schnittstelle: Statuscodes, Header, Fehlerformat (braucht `fastapi` und `httpx`, sonst übersprungen) |

Die Oberfläche wurde in der Entwicklung mit Playwright und Google Chrome geprüft (Navigation, Dialoge, Abstürze, Offline). Diese
Skripte gehören nicht zum Projekt, weil sie Playwright voraussetzen.

## 10. Wichtige Entscheidungen und Begründungen

| Entscheidung | Begründung | Alternative |
| --- | --- | --- |
| labwc statt Desktop oder Cage | schlanker Wayland-Compositor mit Tastenkürzeln und Fensterregeln; kein Desktop nötig | Cage (zu starr für Kürzel) |
| greetd statt GDM/SDDM | kleiner Autologin ohne grafischen Greeter | getty-Autologin plus Profilskript |
| Google Chrome als einziger Browser | alle Zieldienste sind Webseiten; ein Browser, getrennte Profile | Firefox (zweites Profilmodell) |
| Python 3 + FastAPI + Uvicorn | in Debian paketiert, für x86_64 vorgesehen, geringe Last | Go-Binary (zweite Toolchain) |
| Frontend ohne Framework und Build | weniger Speicher und Angriffsfläche, nichts zu kompilieren | Preact/Vite |
| Prozessmanagement nur mit Standardbibliothek | keine Abhängigkeit, gut testbar mit echten Prozessen | `psutil` |
| Ein Vordergrundprogramm | Fokus und Rückkehr eindeutig, weniger RAM | mehrere Fenster |
| Loopback, kein Netzwerkzugriff | kleinste Angriffsfläche | LAN-Fernsteuerung (später) |
| Konfiguration in JSON | `json` ist in der Standardbibliothek; vom Projektauftrag so vorgegeben (`settings.json`) | TOML |
| Pakete aus Debian statt PyPI als Standardweg | eine Quelle, Sicherheitsupdates über `apt` | venv mit pip (Variante B) |
| Programmcode unter `/opt` gehört root | die Anwendung kann sich nicht selbst verändern | Installation im Benutzerverzeichnis |

## 11. Abweichungen vom ursprünglichen Entwurf

Der erste Entwurf war ein Zielbild. Die Umsetzung ist ein Prototyp, der es in kleineren Schritten erreicht. Die Abweichungen
und ihre Gründe:

| Entwurf | Umsetzung | Begründung |
| --- | --- | --- |
| Apps als transiente systemd-Units (`systemd-run`), `livingroomos-apps.slice`, `MemoryMax` | direkter Start mit `create_subprocess_exec`, eigene Prozessgruppe, Beenden über Signale | Vorgabe des Auftrags („subprocess ohne shell=True“, PIDs überwachen, gezielt beenden); testbar ohne systemd; der `LaunchSpec` bleibt als Schnittstelle, ein Runner mit `systemd-run` kann ihn später ersetzen. **Folge:** keine Speichergrenze und keine cgroup-Kontrolle über Google Chrome-Helferprozesse, ausgeglichen durch Prozessgruppe und Nachzüglersuche. |
| SSE-Strom `/api/v1/events` mit Snapshot | Abfrage von `/apps/status` (1,2 s bis 6 s) | SSE braucht eine dauerhafte Verbindung, Ereignisbus und Wiederverbindungslogik. Für einen Zustand, der sich selten ändert, ist die Abfrage einfacher und in 4 s Leerlauf billig. **Folge:** bis zu 1,2 s Verzögerung bei Zustandsänderungen. Ersetzbar, ohne den Vertrag zu ändern. |
| Paket `livingroomos/` mit `registry`, `supervisor`, `launchers`, `runner`, `compositor`, `events`, `platform`, `security`, `config` | flache Module `api/`, `services/` mit den vom Auftrag vorgegebenen Dateinamen | Der Auftrag legte die Dateien fest. Die Verantwortlichkeiten sind trotzdem getrennt (Konfigurationsprüfung und Befehlsbau im `AppLauncher`, Prozesslebenszyklus im `ProcessManager`). |
| Konfiguration als TOML mit Pydantic und Schichten (`/etc`, Benutzer) | eine JSON-Datei, im Betrieb unter `~/.config/livingroomos/settings.json` (`LIVINGROOMOS_CONFIG`) | Der Auftrag nannte `settings.json`. Die Prüfung steckt in `parse_apps`. |
| Endpunkte `/state`, `/home`, `/session/foreground/stop`, `/audio/volume`, `/system/power`, `/events` | `/apps/status`, `/apps/stop`, `/apps/{id}/stop`, `/system/status`, `/settings` | Nur das, was der Prototyp braucht. Audio und Energie sind nicht umgesetzt. |
| Fehlerformat RFC 9457 | `{"error": {"code", "message"}}` | Einfacher für das Frontend; gleiche Information. |
| Sicherheits-Middleware mit Origin-Prüfung und JSON-Pflicht | Host-Prüfung plus Pflichtheader `X-LivingroomOS` | Der eigene Header erfüllt den CSRF-Schutz ohne Origin-Auswertung. |
| Compositor-Bridge als eigenes Modul (`WlrctlBridge`) | optionaler Rückkehr-Befehl `server.return_to_launcher_command` | Der Fokus fällt nach dem Schließen des App-Fensters meist von selbst zurück; der Befehl ist nur ein Zusatz. |
| Frontend `main.js`, `nav.js`, `events.js`, `store.js`, `views/`, `components/` | `app.js`, `navigation.js`, `remote.js`, `api.js` | Dateinamen vom Auftrag vorgegeben. |
| `platform/`-Profile für Architekturen | keine; Architektur steht nur im Systemstatus | Bisher gibt es nichts Architekturabhängiges. Profile werden ergänzt, wenn Messungen auf dem Pi es verlangen. |

Unverändert aus dem Entwurf: das Ein-Vordergrundprogramm-Prinzip, die Startkette greetd → `livingroomos-session` → labwc →
`livingroomos.target`, die zwei Units, `livingroomosctl`, loopback-only, versionierte Pfade, Idempotenz und 409 bei Konflikt,
getrennte Browserprofile.

## 12. Ressourcen und Risiken

| Thema | Einschätzung und Gegenmaßnahme |
| --- | --- |
| Arbeitsspeicher | Google Chrome ist der größte Verbraucher (Launcher und App zusammen mehrere hundert MB). Nur ein Vordergrundprogramm; auf dem Pi `zram-tools`. Keine harte Grenze (siehe Abweichung zu `MemoryMax`). |
| CPU im Leerlauf | Backend wartet; Abfrage nur alle 4 s; Animationen sind kurz und rein CSS. |
| Widevine (Streaming-Anbieter) | Das Debian-Google Chrome enthält kein Widevine. Streaming-Anbieter-Wiedergabe ist **nicht zugesichert**; das Projekt installiert kein Widevine. |
| Hardware-Videodekodierung | auf dem NUC über VA-API möglich, auf dem Pi nicht zugesichert. Messen. |
| Rettung bei Fehlkonfiguration | Das Kiosk-labwc sperrt Konsolenwechsel. SSH ist der Rettungsweg und gehört zur Installation. |
| App und Backend teilen eine UID | eine kompromittierte App könnte das Backend beeinflussen. Weitere Isolation: `systemd-run` mit Sandboxing (siehe Ausblick). |
| Ungetestete Systemdateien | `system/` (greetd, labwc, systemd) ist nach Dokumentation geschrieben, aber nicht auf Hardware geprüft. |

## 13. Ausblick

- Apps als transiente systemd-Units mit `MemoryMax` und Sandboxing. Nur der Runner im `ProcessManager` ändert sich.
- Statusereignisse per SSE statt Abfrage.
- Plattformprofile (Google Chrome-Flags je Gerät) nach Messungen auf dem x86_64-PC.
- Audio (Lautstärke) und Energie (Ausschalten, Neustart) als eigene, kleine Dienste.
