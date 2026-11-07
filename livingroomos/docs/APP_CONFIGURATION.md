# App Configuration

LivingroomOS automatically loads web apps from individual files in
`backend/config/apps/`. Adding an app does not require changes to Python or
JavaScript code: create a file with the `.cfg` extension and restart the
backend.

## Example: netflix.cfg

```ini
[app]
id = netflix
title = Netflix
subtitle = Movies and TV shows
icon = 🍿
color = #E50914
category = media

[browser]
executable = google-chrome-stable
url = https://www.netflix.com/
fullscreen = true
wayland = true
```

## Fields

### [app]

| Field | Required | Description |
|---|---|---|
| `id` | Yes | Unique ID; lowercase letters, numbers, `_`, and `-`; maximum 32 characters |
| `title` | Yes | Tile name |
| `subtitle` | No | Tile subtitle |
| `icon` | No | Short text symbol or emoji |
| `color` | No | Tile color in `#RRGGBB` format |
| `category` | No | `media` (main menu) or `debug` (diagnostics) |

### [browser]

| Field | Default | Description |
|---|---|---|
| `executable` | `google-chrome-stable` | Supported values: `google-chrome-stable`, `google-chrome`, `chrome` |
| `url` | — | HTTP or HTTPS URL of the app |
| `fullscreen` | `true` | Starts Chrome in fullscreen mode |
| `wayland` | `true` | Enables the Wayland interface |
| `long_running` | `true` | Treats the app as a long-running process |

## Rules and security

- The filename must match the ID exactly: `netflix.cfg` must contain `id = netflix`.
- Each app automatically receives its own Chrome profile in the LivingroomOS data directory.
- CFG files cannot execute arbitrary shell commands or launch arbitrary browser executables.
- The URL, browser executable, color, and category are validated when the file is loaded.
- Invalid files are skipped and reported as `config_problems` by `GET /api/v1/system/status`. Other valid apps remain available.
- Existing debug and process-test entries may remain in `backend/config/settings.json`. Otherwise, that file contains only server and UI settings.

## Installation and paths

The supplied app files remain in the program directory
`/opt/livingroomos/backend/config/apps/`. The
`LIVINGROOMOS_CONFIG` variable can still point to a separate
`settings.json` in the user's data directory; it does not change the location
of the supplied app CFG files.

After adding or changing a CFG file, restart the backend. The main menu picks
up the app list on its next API request.
