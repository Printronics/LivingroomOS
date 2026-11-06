# LivingroomOS – Sicherheitskonzept Prozessmanagement

Stand: 2026-11-03 · Geltungsbereich: `backend/services/app_launcher.py`, `backend/services/process_manager.py`

## 1. Schutzziele

| Nr. | Ziel |
| --- | --- |
| S1 | Das Backend startet nur Programme, die der Administrator in `config/settings.json` vorab festgelegt hat, und nur mit den dort festgelegten Parametern. |
| S2 | Aus dem Frontend, aus dem Netzwerk oder aus einer Webseite lässt sich weder ein Befehl noch ein Parameter einschleusen. |
| S3 | Das Backend beendet ausschließlich Prozesse, die es selbst gestartet hat (oder nach einem Absturz sicher wiedererkennt). Andere Browserfenster, auch Google Chrome des Benutzers, bleiben unberührt. |
| S4 | Jede App ist von den anderen getrennt: eigenes Browserprofil, eigene Prozessgruppe, gefilterte Umgebung. |
| S5 | Ausfälle (Absturz, Hänger, Backend-Neustart) führen immer zurück in einen definierten Zustand und zum Launcher. |
| S6 | Fehler sind nachvollziehbar protokolliert, ohne dass Geheimnisse an die Oberfläche gelangen. |

## 2. Annahmen und Bedrohungsmodell

**Vertrauensgrenzen**

```
Webseite in einer App ──╳──►  127.0.0.1:8750 (Backend)      Host-Prüfung, X-LivingroomOS-Header, kein CORS
Launcher-Frontend  ──────►  Backend                         sendet nur App-IDs
Backend (Benutzer livingroomos) ──► App-Prozess (gleicher Benutzer)   gleiche Rechte: Isolation nur teilweise
settings.json  ◄── Administrator (vertraut)
```

**Wovor das Konzept schützt**

- Fremde Webseiten oder Skripte, die die lokale API ansprechen (CSRF, DNS-Rebinding).
- Manipulierte Eingaben an die API (Befehlseinschleusung, Pfad- oder Parameter-Manipulation).
- Versehentlich unsichere Konfiguration (z. B. `--no-sandbox`, Standard-Browserprofil, beschreibbare Programme).
- Falsches Beenden fremder Prozesse durch PID-Wiederverwendung oder zu breite Suchmuster.
- Verwaiste Prozesse nach Abstürzen und Doppelstarts.

**Wovor es nicht schützt (Restrisiken, siehe Abschnitt 7)**

- Code, der bereits als Benutzer `livingroomos` läuft (z. B. nach Browser-Exploit, der die Google Chrome-Sandbox verlässt).
- Angreifer mit physischem Zugriff oder Root-Rechten.
- Einen Administrator, der in `settings.json` bewusst Gefährliches einträgt (die Prüfungen fangen nur häufige Fehler ab).

## 3. Maßnahmen

| Anforderung | Maßnahme | Ort |
| --- | --- | --- |
| Nur vordefinierte Programme und Parameter | App-Liste nur aus `settings.json`; API nimmt nur eine App-ID mit festem Format (`^[a-z0-9][a-z0-9_-]{0,31}$`). Die Befehlszeile verlässt das Backend nie. | `app_launcher.parse_apps`, `api/apps.py` |
| Keine Shell | `asyncio.create_subprocess_exec` mit Argumentliste, nie `shell=True`. Erlaubt sind nur die Platzhalter `{python}` und `{profile_dir}`; jedes andere `{wort}` in einem Argument sowie NUL-Zeichen werden beim Laden abgelehnt (bewusst streng: Argumente mit geschweiften Klammern, z. B. JSON, sind nicht möglich). | `process_manager.start`, `parse_apps` |
| Programmpfad abgesichert | Bare Namen werden nur in `trusted_bin_dirs` gesucht (nicht in `$PATH` des Benutzers). Relative Pfade sind verboten. Der echte Pfad (`realpath`) muss in einem vertrauenswürdigen Verzeichnis liegen. Datei: Besitzer root oder Dienstbenutzer, nicht für Gruppe/Andere beschreibbar; Elternverzeichnis nicht für Andere beschreibbar. | `AppLauncher._resolve_executable` |
| Gefährliche Schalter | Liste verbotener Schalter (`--no-sandbox`, `--remote-debugging-*`, `--disable-web-security`, `--load-extension`, `--ignore-certificate-errors` …) wird beim Laden abgelehnt. | `FORBIDDEN_FLAGS` |
| Eigene Browserprofile | Browser (Google Chrome-Familie, Firefox) müssen ein `{profile_dir}`-Argument haben, sonst wird die App abgelehnt. Profil: `~/.local/share/livingroomos/profiles/<id>`, Modus 0700, Symlinks und fremder Besitzer werden abgelehnt. | `parse_apps`, `ensure_private_dir` |
| Kein Durchreichen der Umgebung | Start mit minimaler Umgebung: feste Liste (`HOME`, `XDG_RUNTIME_DIR`, `WAYLAND_DISPLAY` …) plus vertrauenswürdiger `PATH`. Zusätzliche App-Variablen nur nach Muster; `LD_*`, `PYTHON*`, `PATH`, `HOME` u. a. verboten. | `AppLauncher._build_env` |
| Prozess-IDs und Status | Status mit PID, Zustand und letztem Ende. Zustandsdatei im Laufzeitverzeichnis (Modus 0600) enthält PID, Prozessgruppe und Startzeit aus `/proc`. | `ProcessManager.status`, `_write_state` |
| Doppelte Starts | Zustand wird vor dem ersten `await` reserviert; Sperrdatei (`flock`) verhindert ein zweites Backend; Reste mit demselben Profil werden vor dem Start beendet. | `start`, `startup` |
| Abstürze erkennen | Beobachter wartet auf das Ende. Klassifikation: `stopped`, `ok`, `crashed` (nach Karenzzeit), `start_failed` (Ende innerhalb der Karenzzeit, auch bei Exit 0 – typisch für Übergabe an eine bereits laufende Browser-Instanz). Signalname bei Abbruch durch Signal. | `_finalize` |
| Gezieltes Beenden | Nur die eigene Prozessgruppe (eigene Sitzung per `start_new_session`). Reihenfolge SIGTERM, nach Frist SIGKILL. `POST /apps/{id}/stop` beendet nur, wenn genau diese App aktiv ist. | `stop`, `_signal_tree` |
| Keine fremden Browserfenster | Nachzügler (Renderer, die die Gruppe verlassen haben) werden über einen **exakten** argv-Eintrag `--user-data-dir=<Profil dieser App>` gefunden, nie über Programmnamen. Zusätzlich: nur eigene UID, Signal per `pidfd` (kein PID-Recycling), Gegenprüfung der Befehlszeile unmittelbar vor dem Signal. | `_find_pids_with_arg`, `_signal_verified` |
| Fehlerprotokollierung | Lebenszyklus über `logging` (journald unter systemd). Ausgabe der App in `~/.local/share/livingroomos/logs/<id>.log` (0600, Rotation bei 1 MiB). Bei Absturz die letzten Zeilen im Log, nicht in der API. Sicherheitsablehnungen als WARNING mit Grund. | `_open_log`, `_finalize`, `AppLauncher.launch` |
| Rückkehr zum Launcher | Nach jedem Ende wechselt der Zustand auf `idle`; das Frontend blendet den Launcher wieder ein. Optional ruft ein fest konfigurierter Befehl (`return_to_launcher_command`, z. B. `wlrctl`) den Fokus zurück, ebenfalls ohne Shell, mit Zeitlimit. | `AppLauncher._on_exit` |
| Backend-Absturz | Beim Start liest das Backend die Zustandsdatei, prüft PID **und** Startzeit und übernimmt die laufende App (Zustand `running`). Ist sie weg, werden Reste über das Profil beendet. | `_recover` |

## 4. Berechtigungen

**Benutzer und Gruppen**

| Was | Anforderung |
| --- | --- |
| Dienstbenutzer | Eigener Benutzer `livingroomos`, **kein** root, **kein** sudo, keine Capabilities. |
| Gruppen | Normalerweise keine zusätzlichen: Zugriff auf GPU und Audio erteilt logind sitzungsbasiert (`uaccess`). Falls nötig: `video`, `render`, `audio`. Nur ergänzen, wenn ein Test es erfordert. |
| Sitzung | Start innerhalb der greetd-/logind-Sitzung, damit `XDG_RUNTIME_DIR` (`/run/user/<uid>`) und der Wayland-Socket existieren. |

**Dateisystem**

| Pfad | Zugriff | Modus |
| --- | --- | --- |
| `<Projekt>/backend/config/settings.json` | Lesen (Abschnitt `ui` wird atomar zurückgeschrieben) | 0644, Besitzer root oder `livingroomos`; `apps` nur vom Administrator ändern |
| `~/.local/share/livingroomos/profiles/<id>/` | Lesen/Schreiben | 0700 |
| `~/.local/share/livingroomos/logs/` | Schreiben | 0700, Dateien 0600 |
| `$XDG_RUNTIME_DIR/livingroomos/` (`backend.lock`, `state.json`) | Lesen/Schreiben | 0700, Dateien 0600 |
| `/usr/bin`, `/usr/local/bin`, `/opt` (`trusted_bin_dirs`) | nur Lesen/Ausführen | muss root gehören |
| `/proc/<pid>/{stat,cmdline}` | Lesen (eigene UID) | `hidepid` ist für eigene Prozesse unproblematisch |

**Signale:** Das Backend darf nur Prozesse seiner eigenen UID signalisieren; fremde UIDs werden gar nicht erst betrachtet.

## 5. Systemabhängigkeiten

| Abhängigkeit | Zweck | Hinweis |
| --- | --- | --- |
| Linux ab Kernel 5.3 | `pidfd_open`, `pidfd_send_signal`; Debian 13 liefert 6.12 | gilt für die unterstützte x86_64-Plattform |
| Python ≥ 3.11 | `TimeoutError`-Vereinheitlichung, `umask`-Parameter, `Path.is_relative_to` | Debian 13: 3.13 |
| `/proc` | Startzeit und Befehlszeile für die Identitätsprüfung | Linux-spezifisch, keine Portierung auf andere Systeme |
| `fcntl.flock` | Backend-Sperre | Standardbibliothek |
| Externe Python-Pakete | nur `fastapi` und `uvicorn` (bereits vorhanden); das Prozessmanagement selbst nutzt **ausschließlich die Standardbibliothek** | |
| Programme der Apps | z. B. Debian-Paket `google-chrome-stable` für Streaming-Webseiten und Mediatheken | Streaming-Anbieter verlangt Widevine, im Debian-Google Chrome nicht enthalten |
| Optional | `wlrctl` für „Fokus zurück zum Launcher“ | Paketverfügbarkeit in Debian 13 vor Nutzung prüfen; ohne es genügt das Schließen des App-Fensters |

## 6. Empfohlene systemd-Härtung (ungetestet, vor Einsatz prüfen)

Der Backend-Dienst als User-Unit kann sich selbst einschränken. **Achtung:** Kindprozesse erben diese Einschränkungen, und Google Chrome braucht Benutzer-Namensräume, Netzwerk (inkl. `AF_NETLINK`) und GPU-Zugriff. Jede Option einzeln einschalten und mit Google Chrome testen.

```ini
[Service]
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=%h/.local/share/livingroomos %t/livingroomos %h/.config/livingroomos
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
# Bewusst NICHT setzen, bevor Google Chrome getestet ist:
# PrivateDevices, RestrictNamespaces, SystemCallFilter, RestrictAddressFamilies, MemoryDenyWriteExecute
```

Der saubere nächste Schritt ist, Apps als **transiente systemd-User-Units** (`systemd-run --user`) zu starten: eigene cgroup, `MemoryMax`, vollständiges Beenden aller Kindprozesse ohne `/proc`-Suche, eigene Härtung je App unabhängig vom Backend. Die Schnittstelle `LaunchSpec` bleibt dabei gleich; nur `ProcessManager` wird ausgetauscht.

## 7. Restrisiken

| Risiko | Bewertung | Gegenmaßnahme / Plan |
| --- | --- | --- |
| App und Backend laufen unter derselben UID. Eine kompromittierte App könnte Backend-Dateien lesen oder das Backend beenden. | Mittel | Google Chrome-Sandbox bleibt aktiv (nie `--no-sandbox`); später systemd-Units je App und ggf. eigene UID pro App. |
| Google Chrome-Prozesse, die weder in der Prozessgruppe noch mit dem Profil-Argument auftauchen, werden nicht erfasst. | Gering | Die Nachzügler-Suche deckt Renderer/GPU/Utility ab, weil Google Chrome das Argument vererbt. Mit cgroups (Abschnitt 6) lückenlos. |
| Übernommene App (nach Backend-Absturz): Exit-Code unbekannt, Absturz nicht von Normalende unterscheidbar (Grund `ended`). | Gering | Hinnehmbar; Hinweis im Log. |
| Fenster-Fokus zurück zum Launcher hängt vom Compositor ab. | Gering | Ohne `wlrctl`: Fenster schließt, Launcher liegt darunter und wird sichtbar. |
| Administratorfehler in `settings.json`. | Gering | Beim Laden geprüft; fehlerhafte Einträge werden übersprungen und unter `/api/v1/system/status` als `config_problems` gemeldet. |
| Race zwischen Prüfung und Signal bei Nachzüglern. | Sehr gering | `pidfd` fixiert den Prozess; Gegenprüfung unmittelbar vor dem Signal; nur eigene UID. |

## 8. Prüfliste vor dem Einsatz

- [ ] `settings.json` gehört root (oder `livingroomos`) und ist nicht für Andere beschreibbar.
- [ ] Alle Programme liegen in `trusted_bin_dirs` und gehören root.
- [ ] Jede Browser-App hat `--user-data-dir={profile_dir}`; kein verbotener Schalter.
- [ ] Backend läuft als `livingroomos`, nicht als root.
- [ ] `GET /api/v1/system/status` zeigt `config_problems: []`.
- [ ] Test: App starten, `kill -9` auf die App, Launcher erscheint wieder, Absturzmeldung kommt genau einmal.
- [ ] Test: Eigenes Google Chrome-Fenster parallel geöffnet; „App beenden“ lässt es unberührt.
- [ ] Test: Backend mit `kill -9` beenden und neu starten; laufende App wird übernommen.


## 9. Neustart und Herunterfahren

Die Oberfläche kann nur `POST /api/v1/system/power/restart` oder `POST /api/v1/system/power/shutdown` anfordern.
Das Backend mappt diese zwei Werte auf feste Argumentlisten (`systemctl reboot` bzw. `systemctl poweroff`).
Es gibt keine freie Befehls-, Parameter- oder Shell-Eingabe. Andere Aktionsnamen werden mit HTTP 404 abgewiesen.

**Berechtigungsgrenze:** Das Repository enthält derzeit keine eigene Polkit-Regel. Die Aktionen unterliegen deshalb
der systemweiten systemd-logind-/Polkit-Standardrichtlinie. Auf einem aktiven lokalen Benutzerplatz erlaubt die
Standardrichtlinie Neustart und Herunterfahren; diese Berechtigung ist nicht exklusiv auf `livingroomos`
beschränkt. Die Oberfläche begrenzt lediglich die angebotenen Aktionen, sie schafft keine zusätzliche
Berechtigungsgrenze gegenüber anderen Prozessen desselben aktiven Benutzers.

Vor einem Release muss diese Eigenschaft auf Debian 13 geprüft und in der Sicherheitsbewertung berücksichtigt
werden. Insbesondere darf die Dokumentation nicht behaupten, dass eine nicht vorhandene Projektregel die
Power-Aktionen ausschließlich dem Dienstkonto erlaubt.
