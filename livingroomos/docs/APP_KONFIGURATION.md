# App-Konfigurationen

LivingroomOS lädt Web-Apps automatisch aus einzelnen Dateien unter
`backend/config/apps/`. Eine neue App benötigt keine Änderung an Python- oder
JavaScript-Code: Lege eine Datei mit der Endung `.cfg` an und starte das
Backend neu.

## Beispiel: netflix.cfg

```ini
[app]
id = netflix
title = Netflix
subtitle = Filme und Serien
icon = 🍿
color = #E50914
category = media

[browser]
executable = google-chrome-stable
url = https://www.netflix.com/
fullscreen = true
wayland = true
```

## Felder

### [app]

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `id` | Ja | Eindeutige ID; Kleinbuchstaben, Zahlen, `_` und `-`; maximal 32 Zeichen |
| `title` | Ja | Name der Kachel |
| `subtitle` | Nein | Untertitel der Kachel |
| `icon` | Nein | Kurzes Textsymbol oder Emoji |
| `color` | Nein | Kachelfarbe im Format `#RRGGBB` |
| `category` | Nein | `media` (Hauptmenü) oder `debug` (Diagnose) |

### [browser]

| Feld | Standard | Beschreibung |
|---|---|---|
| `executable` | `google-chrome-stable` | Unterstützt: `google-chrome-stable`, `google-chrome`, `chrome` |
| `url` | – | HTTP- oder HTTPS-Adresse der App |
| `fullscreen` | `true` | Startet Chrome im Vollbildmodus |
| `wayland` | `true` | Aktiviert die Wayland-Oberfläche |
| `long_running` | `true` | Behandelt die App als dauerhaft laufenden Prozess |

## Regeln und Sicherheit

- Der Dateiname muss exakt zur ID passen: `netflix.cfg` enthält `id = netflix`.
- Jede App erhält automatisch ein eigenes Chrome-Profil unter dem LivingroomOS-Datenverzeichnis.
- Die CFG-Datei kann keine freien Shell-Befehle oder beliebigen Browser-Programme starten.
- URL, Browser-Ausführungsdatei, Farbe und Kategorie werden beim Laden geprüft.
- Fehlerhafte Dateien werden übersprungen und in `GET /api/v1/system/status`
  unter `config_problems` gemeldet. Andere gültige Apps bleiben verfügbar.
- Die vorhandenen Debug- und Prozess-Testeinträge dürfen weiterhin in
  `backend/config/settings.json` stehen. Die Datei enthält ansonsten nur
  Server- und UI-Einstellungen.

## Installation und Pfade

Die mitgelieferten App-Dateien bleiben im Programmverzeichnis
`/opt/livingroomos/backend/config/apps/`. Die variable
`LIVINGROOMOS_CONFIG` kann weiterhin auf eine separate
`settings.json` im Benutzer-Datenverzeichnis zeigen; sie verschiebt nicht den
Ort der mitgelieferten App-CFG-Dateien.

Nach dem Hinzufügen oder Ändern einer CFG-Datei muss das Backend neu gestartet
werden. Das Hauptmenü übernimmt die App-Liste beim nächsten API-Aufruf.
