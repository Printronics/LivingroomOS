# LivingroomOS – Debian-Systemabhängigkeiten

Diese Datei dokumentiert alles, was LivingroomOS außerhalb von Python-Paketen braucht. Python-Bibliotheken stehen in
`requirements.txt`. Maschinenlesbar sind die Pakete in `debian-packages.txt` (Pflicht) und
`debian-packages-optional.txt`. Ein Test (`backend/tests/test_project_consistency.py`) stellt sicher, dass jedes dort
genannte Paket auch hier erklärt ist.

Zielsystem: **Debian 13 „trixie“ auf `amd64` / x86_64 (Intel/AMD)**. ARM wird nicht unterstützt.

## 1. Pflichtpakete

| Paket | Wofür | Hinweis |
| --- | --- | --- |
| `python3` | Laufzeit des Backends | Debian 13 liefert 3.13; benötigt wird mindestens 3.11 |
| `python3-fastapi` | Web-Framework (REST-API, Middleware) | zieht `python3-starlette` und `python3-pydantic` nach |
| `python3-uvicorn` | ASGI-Server auf 127.0.0.1 | reine Python-Version genügt, kein `uvloop` nötig |
| Google Chrome | Launcher-Fenster und Web-Apps | offizielles Google-`.deb`, separat installiert; nicht im Debian-Archiv |
| `labwc` | Wayland-Compositor | mit `--no-install-recommends` installieren, damit Xwayland entfällt |
| `greetd` | Autologin in die labwc-Sitzung | enthält `agreety` als Rückfall-Anmeldung |
| `systemd` | Dienste (Benutzer-Units) | auf Debian vorhanden |
| `dbus-user-session` | startet `systemd --user` je Sitzung | ohne dieses Paket laufen die Benutzer-Units nicht |
| `libpam-systemd` | logind-Sitzung | gibt dem Benutzer Zugriff auf GPU und Eingabegeräte |
| `polkitd` | Autorisierung von Neustart und Herunterfahren | lädt die mitgelieferte Regel `system/polkit/50-livingroomos-power.rules` aus `/etc/polkit-1/rules.d/` |
| `pipewire` | Audio | |
| `pipewire-pulse` | Audio-Kompatibilität | Google Chrome spricht PulseAudio |
| `wireplumber` | PipeWire-Sitzungsverwaltung | |
| `libgl1-mesa-dri` | Grafiktreiber | Intel/AMD-Grafik |
| `fonts-noto-core` | Schriften | Oberfläche und Webseiten |
| `fonts-noto-color-emoji` | Emoji | |

## 2. Optionale Pakete

| Paket | Wofür |
| --- | --- |
| `unzip` | nur zum Entpacken des Projektarchivs `livingroomos.zip` |
| `wlrctl` | Fokus nach dem Ende einer App aktiv zum Launcher zurückholen (`server.return_to_launcher_command`). Ob das Paket in Debian 13 verfügbar ist und das Protokoll von labwc unterstützt wird, ist vor dem Einsatz mit `apt-cache policy wlrctl` zu prüfen. Ohne dieses Paket fällt der Fokus von selbst auf den Launcher zurück, sobald das App-Fenster schließt. |
| `wlr-randr` | Auflösung und Wiederholrate im labwc-Autostart festlegen (auf dem Pi sinnvoll: 1920×1080) |
| `python3-venv` | nur für den pip-Weg (`INSTALL.md`, Variante B) |
| `python3-httpx` | nur für die API-Tests; ohne dieses Paket werden sie übersprungen |
| `intel-media-va-driver` | Hardware-Videodekodierung (VA-API) auf Intel-NUCs |
| `mesa-va-drivers` | VA-API für AMD-Grafik |
| `vainfo` | Diagnose, welche Codecs die Grafik beschleunigt |
| `unattended-upgrades` | automatische Sicherheitsupdates, vor allem für Google Chrome |
| `zram-tools` | komprimierter Swap im Arbeitsspeicher, sinnvoll auf Pi-Modellen mit 2 bis 4 GB |

## 3. Kernel, Python und Dateisystem

| Anforderung | Grund |
| --- | --- |
| Linux ≥ 5.3 | `pidfd_open` und `pidfd_send_signal` identifizieren Prozesse ohne PID-Verwechslung. Debian 13 liefert 6.12. |
| Python ≥ 3.11 | `TimeoutError` bei `asyncio.wait_for`, `umask=` bei `create_subprocess_exec`, `Path.is_relative_to` |
| `/proc` eingehängt | Startzeit und Argumente eines Prozesses für die Identitätsprüfung |
| `fcntl.flock` | Sperrdatei, damit nur ein Backend die Prozesse verwaltet |
| Dateisystem mit Unix-Rechten | Modi 0700/0600 für Profile, Logs und Zustandsdatei |

`tools/check_system.py` prüft diese Punkte und meldet, was fehlt.

## 4. Benutzer, Rechte, Verzeichnisse

| Was | Festlegung |
| --- | --- |
| Betriebssystembenutzer | `livingroomos`, gewöhnliches Konto ohne `sudo` und ohne besondere Capabilities |
| Zusätzliche Gruppen | normalerweise keine; logind vergibt GPU- und Audiozugriff je Sitzung. Nur wenn nötig auf dem Pi: `video`, `render`, `audio` |
| `/opt/livingroomos` | gehört `root`, lesbar für alle, nicht beschreibbar für `livingroomos` (Programmcode kann sich nicht selbst ändern) |
| `~/.config/livingroomos/settings.json` | gehört `livingroomos`, Modus 0600; das Backend schreibt nur den Abschnitt `ui` zurück |
| `~/.local/share/livingroomos/profiles/<id>/` | Browserprofile, Modus 0700 |
| `~/.local/share/livingroomos/logs/<id>.log` | Ausgabe der Apps, Modus 0600, Rotation bei 1 MiB |
| `$XDG_RUNTIME_DIR/livingroomos/` | `backend.lock` und `state.json`, Modus 0700 (liegt im RAM) |
| `/var/lib/livingroomos/.config/systemd/user/livingroomos*.{service,target}` | Benutzer-Units für das dedizierte Konto `livingroomos`; gehören diesem Benutzer |
| `/etc/greetd/config.toml` | Autologin-Konfiguration, gehört `root` |
| `/etc/polkit-1/rules.d/50-livingroomos-power.rules` | eng begrenzte Power-Aktionen für `livingroomos`, gehört `root` |
| `/etc/opt/chrome/policies/managed/livingroomos.json` | Google Chrome-Richtlinien, gehört `root` |

Netzwerk: Das Backend lauscht **nur** auf `127.0.0.1:8750`. Es gibt keinen eingehenden Port nach außen. Die Apps
brauchen ausgehende Verbindungen (HTTPS).

## 5. Zielarchitektur

Unterstützt wird ausschließlich `amd64` / x86_64. Die Systemprüfung lehnt ARM-Prozessoren ab.

## 6. Installationsquellen

Debian-Systempakete stammen aus dem offiziellen Debian-Archiv über `apt`. Google Chrome wird separat als offizielles 64-Bit-`.deb` des Herstellers installiert. Das Projekt lädt keine Skripte aus dem Netz, nutzt
kein `curl | sh` und fügt keine Fremd-Repositories hinzu. Der optionale pip-Weg (`requirements.txt`) bezieht
`fastapi` und `uvicorn` von PyPI und ist deshalb nur die zweite Wahl.
