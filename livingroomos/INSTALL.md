# LivingroomOS – Installation auf Debian 13

Diese Anleitung richtet einen frischen Debian-13-Rechner („trixie“) als Fernseher-Appliance ein: Der Rechner meldet den
Benutzer `livingroomos` automatisch an und zeigt direkt den LivingroomOS-Launcher.

> **Ehrlicher Stand:** Das Backend, die Prozessverwaltung und die Oberfläche sind in einer Entwicklungsumgebung getestet.
> Die Systemdateien in `system/` (greetd, labwc, systemd, Google Chrome-Richtlinien) wurden nach der Dokumentation der Programme
> geschrieben, aber **noch nicht auf echter Hardware ausgeführt**, ebenso die Streaming-Wiedergabe. Deshalb ist der
> Weg unten so aufgebaut, dass jeder Schritt einzeln prüfbar ist und der Rückweg immer offen bleibt. Mit `[prüfen]`
> markierte Stellen sind Annahmen, die du auf dem Gerät bestätigen musst.

Debian-Systempakete kommen aus dem **offiziellen Debian-Archiv** über `apt`. Google Chrome wird separat als offizielles Herstellerpaket installiert. Das Projekt lädt keine Installationsskripte aus dem Netz und trägt keine Fremd-Repositories ein.

## 0. Voraussetzungen

| Was | Anforderung |
| --- | --- |
| Rechner | x86_64-Rechner mit Intel- oder AMD-64-Bit-Prozessor. ARM wird nicht unterstützt. |
| Arbeitsspeicher / Platz | mindestens 4 GB RAM und 8 GB Speicher |
| Netzwerk | Verbindung für die Installation und für die Dienste (Streaming-Anbieter usw.) |
| Zugang zum Rechner | zweiter Rechner mit **SSH** – das ist der Rettungsweg (siehe Abschnitt 9) |
| Projekt | der Ordner `livingroomos/` oder das Archiv `livingroomos.zip` |

## 1. Debian 13 minimal installieren

1. Debian 13 „trixie“ von <https://www.debian.org/distrib/> laden und mit dem normalen Debian-Installer (netinst) installieren.
   Die Prüfsumme des Abbilds mit den dortigen `SHA256SUMS` vergleichen.
2. Bei der Softwareauswahl **alle Desktop-Umgebungen abwählen**. Angekreuzt bleiben nur **„SSH-Server“** und
   **„Standard-Systemwerkzeuge“**.
3. Während der Installation ein Administratorkonto anlegen (im Folgenden `admin`, mit `sudo`). Den Benutzer `livingroomos`
   legen wir in Abschnitt 3 an.
4. Nach dem ersten Start per SSH als `admin` anmelden und das System aktualisieren:

```bash
sudo apt update
sudo apt full-upgrade
```

Falls `sudo` fehlt: `su -` und `apt install sudo`, danach `usermod -aG sudo admin` und neu anmelden.

## 2. Pakete installieren

Google Chrome ist kein Paket aus dem Debian-Archiv. Lade das offizielle 64-Bit-Debian-Paket von Google herunter und installiere es separat:

```bash
sudo apt install wget
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb
```

Das Projekt enthält weder den Browser noch dessen Binärdateien. Die Installation erfolgt direkt durch den Administrator.


Mit dem Projektordner auf dem Rechner (zum Beispiel per `scp` nach `/tmp/livingroomos.zip`):

```bash
sudo apt install unzip
cd /tmp && unzip livingroomos.zip           # erzeugt /tmp/livingroomos
cd /tmp/livingroomos
```

Pflichtpakete (die Liste steht in `debian-packages.txt`, jedes Paket ist in `docs/SYSTEMABHAENGIGKEITEN.md` begründet):

```bash
sudo apt install --no-install-recommends $(grep -v '^[[:space:]]*#' debian-packages.txt | awk '{print $1}')
```

Prüfen, ob alle Pakete im Archiv gefunden wurden. Meldet `apt` bei einem Namen „Unable to locate package“, den Namen mit
`apt-cache policy <paket>` suchen und in `debian-packages.txt` anpassen [prüfen]. Die Paketnamen sind nach Dokumentation
von Debian 13 geschrieben, aber nicht auf einem installierten System bestätigt.

Optionale Pakete (siehe `debian-packages-optional.txt`) nach Bedarf, zum Beispiel für die Hardware-Videodekodierung auf
einem x86_64-PC:

```bash
sudo apt install intel-media-va-driver vainfo
```

## 3. Benutzer anlegen

Der Dienstbenutzer hat kein `sudo` und keine Zusatzrechte:

```bash
sudo adduser --disabled-password --gecos "LivingroomOS" livingroomos
```

Kein Kennwort: Er meldet sich nur über greetd an, nicht per SSH. Wer an der Konsole oder per SSH als `livingroomos` arbeiten
will, vergibt mit `sudo passwd livingroomos` ein Kennwort.

Zugriff auf Grafik und Eingabegeräte vergibt `logind` je Sitzung. Nur falls `labwc` später „Permission denied“ auf
`/dev/dri/*` oder `/dev/input/*` meldet, die Gruppen ergänzen: `sudo adduser livingroomos video` und `sudo adduser livingroomos render`
(auf dem Zielsystem eventuell zusätzlich `audio`).

## 4. Projekt nach `/opt/livingroomos` kopieren

Der Programmcode gehört `root` und ist für `livingroomos` nur lesbar. So kann sich die Anwendung nicht selbst verändern.

```bash
sudo cp -a /tmp/livingroomos /opt/livingroomos
sudo chown -R root:root /opt/livingroomos
sudo chmod -R go-w /opt/livingroomos
sudo chmod 755 /opt/livingroomos/run.sh /opt/livingroomos/system/bin/livingroomos-session /opt/livingroomos/system/bin/livingroomosctl
```

## 5. Konfiguration des Benutzers

Das Backend schreibt Oberflächeneinstellungen zurück. Deshalb liegt die Konfiguration im Benutzerverzeichnis:

```bash
sudo -u livingroomos install -d -m 0700 /home/livingroomos/.config/livingroomos
sudo -u livingroomos install -m 0600 /opt/livingroomos/backend/config/settings.json /home/livingroomos/.config/livingroomos/settings.json
```

Die Apps stehen in dieser Datei (`/home/livingroomos/.config/livingroomos/settings.json`). Die Beispiel-Einträge „Demo-App“ und
„Absturz-Test“ dienen dem Ausprobieren und können später entfernt werden. Regeln für Einträge: README.md, Abschnitt
„Konfiguration“.

## 6. Systemprüfung und Tests

Als `livingroomos`, ohne Bytecode-Dateien unter `/opt` zu schreiben:

```bash
sudo -u livingroomos python3 -B /opt/livingroomos/tools/check_system.py --config /home/livingroomos/.config/livingroomos/settings.json
cd /opt/livingroomos/backend && sudo -u livingroomos python3 -B -m unittest discover -s tests
```

`check_system.py` meldet `OK`, `FEHLT` (Pflicht) oder `HINWEIS` (optional). Es darf kein `FEHLT` bleiben. Die Tests laufen
ohne Zusatzpakete bis auf die HTTP-Tests (`test_api.py`), die `python3-httpx` brauchen und sonst übersprungen werden.
Für sie: `sudo apt install python3-httpx`. Alle Tests sollten bestehen.

## 7. Backend allein ausprobieren

Noch ohne Autologin, nur das Backend:

```bash
sudo -u livingroomos env LIVINGROOMOS_CONFIG=/home/livingroomos/.config/livingroomos/settings.json /opt/livingroomos/run.sh
```

In einem zweiten Terminal:

```bash
curl -s http://127.0.0.1:8750/api/v1/health                     # {"status":"ok"}
curl -s http://127.0.0.1:8750/api/v1/apps
curl -s -X POST -H 'X-LivingroomOS: 1' http://127.0.0.1:8750/api/v1/apps/demo/launch
curl -s http://127.0.0.1:8750/api/v1/apps/status                # state: running
curl -s -X POST -H 'X-LivingroomOS: 1' http://127.0.0.1:8750/api/v1/apps/demo/stop
```

Mit `Strg+C` beenden. Funktioniert das, ist das Backend in Ordnung.

## 8. Systemdateien einrichten

### 8.1 systemd-Benutzer-Units, Google-Chrome-Richtlinien und Power-Berechtigung

```bash
sudo cp /opt/livingroomos/system/systemd/user/livingroomos-backend.service \
        /opt/livingroomos/system/systemd/user/livingroomos-shell.service \
        /opt/livingroomos/system/systemd/user/livingroomos.target /etc/systemd/user/
sudo install -D -m 0644 /opt/livingroomos/system/polkit/50-livingroomos-power.rules \
        /etc/polkit-1/rules.d/50-livingroomos-power.rules
sudo install -d /etc/opt/chrome/policies/managed
sudo cp /opt/livingroomos/system/chrome/livingroomos.json /etc/opt/chrome/policies/managed/livingroomos.json
```

Nach jeder Änderung an den Units im Projektordner erneut kopieren. Ob Google Chrome sein Richtlinienverzeichnis unter
`/etc/opt/chrome/policies/managed` liest, bestätigt `chrome://policy` im Launcher-Fenster [prüfen].

### 8.2 Zuerst ohne Autologin testen

Der sichere erste Test: als `livingroomos` an der Konsole anmelden und den Compositor von Hand starten. Dafür vorher ein
Kennwort setzen (`sudo passwd livingroomos`), dann an der Konsole mit Strg+Alt+F2 wechseln und anmelden.

```bash
labwc -C /opt/livingroomos/system/labwc
```

Erwartet: leerer schwarzer Bildschirm, kurz darauf der LivingroomOS-Launcher im Vollbild. Eine App mit Enter starten,
`Strg+Alt+Pos1` beendet sie wieder. Weil das Kiosk-labwc keine Konsolenwechsel erlaubt, beendest du den Test per SSH:
`sudo pkill -u livingroomos -x labwc`. Läuft das, ist der Rest nur noch Autostart.

### 8.3 Autologin mit greetd

greetd soll die Sitzung beim Start automatisch starten.

```bash
sudo cp /etc/greetd/config.toml /etc/greetd/config.toml.orig        # Sicherung
sudo cp /opt/livingroomos/system/greetd/config.toml /etc/greetd/config.toml
getent passwd _greetd            # muss einen Eintrag zeigen; sonst `user = "_greetd"` in config.toml anpassen [prüfen]
sudo systemctl enable greetd
sudo systemctl set-default graphical.target
```

Falls bereits ein anderer Anmeldemanager installiert ist (gdm3, sddm, lightdm), diesen vorher entfernen oder deaktivieren
(`sudo systemctl disable gdm3`), damit nur ein Anmeldemanager startet.

Dann neu starten:

```bash
sudo reboot
```

Erwartet: Nach dem Boot meldet greetd `livingroomos` an, `livingroomos-session` startet labwc, labwc startet `livingroomos.target`, und
der Launcher erscheint. Pfeiltasten und Enter bedienen ihn.

## 9. Fehlersuche und Rettung

Der Kiosk-Compositor sperrt Konsolenwechsel (`system/labwc/rc.xml` enthält bewusst keine Standardkürzel). **SSH ist der
Rettungsweg.** Alle Befehle per SSH als `admin`:

| Problem | Maßnahme |
| --- | --- |
| Schwarzer Bildschirm | `journalctl -b -u greetd` und `sudo -u livingroomos journalctl --user -b` ansehen |
| Backend läuft nicht | `sudo -u livingroomos XDG_RUNTIME_DIR=/run/user/$(id -u livingroomos) systemctl --user status livingroomos-backend` |
| Launcher zeigt „Backend nicht erreichbar“ | Backend-Log wie oben, dann `curl http://127.0.0.1:8750/api/v1/health` |
| App startet nicht | Meldung im Dialog; Ausgabe der App in `/home/livingroomos/.local/share/livingroomos/logs/<id>.log` |
| `config_problems` im Status | `curl -s http://127.0.0.1:8750/api/v1/system/status`; ungültige App-Einträge werden dort begründet |
| Autologin abschalten | `sudo cp /etc/greetd/config.toml.orig /etc/greetd/config.toml` und neu starten, oder `sudo systemctl disable greetd` |
| Normale Konsole zurück | `sudo systemctl set-default multi-user.target` und neu starten |

Die Datei `/home/livingroomos/.config/livingroomos/settings.json` enthält die Konfiguration. Nach Änderungen das Backend neu starten:
`sudo -u livingroomos XDG_RUNTIME_DIR=/run/user/$(id -u livingroomos) systemctl --user restart livingroomos-backend`.

## 10. Update und Rückbau

**Update:** neuen Projektordner nach `/tmp` entpacken, Abschnitt 4 wiederholen (`/opt/livingroomos` vorher umbenennen), Units aus
Abschnitt 8.1 neu kopieren, `sudo reboot`. Die Konfiguration unter `/home/livingroomos/.config/livingroomos/` bleibt unberührt. Neue
Einstellungsschlüssel stehen im CHANGELOG.

**Rückbau:**

```bash
sudo systemctl disable greetd
sudo systemctl set-default multi-user.target
sudo rm /etc/systemd/user/livingroomos-backend.service /etc/systemd/user/livingroomos-shell.service /etc/systemd/user/livingroomos.target
sudo rm /etc/opt/chrome/policies/managed/livingroomos.json
sudo rm -r /opt/livingroomos
sudo deluser --remove-home livingroomos
```

## 11. DRM und geschützte Wiedergabe

Ob DRM-geschützte Inhalte funktionieren, hängt vom jeweiligen Anbieter und dessen Browseranforderungen ab. LivingroomOS installiert keine DRM-Komponenten oder proprietären Medienmodule. Die Unterstützung muss pro Anbieter auf dem Zielgerät geprüft werden.

## 12. Alternative: Python-Pakete aus PyPI (virtuelle Umgebung)

Der Standardweg nutzt `python3-fastapi` und `python3-uvicorn` aus Debian. Wer neuere Versionen will, kann stattdessen die
Pakete aus `requirements.txt` von PyPI beziehen. PyPI ist eine zweite Quelle neben Debian und bekommt keine
Sicherheitsupdates über `apt`.

```bash
sudo apt install python3-venv
sudo python3 -m venv /opt/livingroomos/.venv
sudo /opt/livingroomos/.venv/bin/pip install -r /opt/livingroomos/requirements.txt
sudo chmod -R go-w /opt/livingroomos/.venv
```

`run.sh` nutzt `/opt/livingroomos/.venv` automatisch. Die benötigten Pakete sind reine Python-Pakete; es wird nichts kompiliert.
