# LivingroomOS

**A lightweight, keyboard-friendly living-room interface for Debian 13 (x86_64).**

LivingroomOS is a minimal living-room interface for TV screens and media-center PCs. It provides an application launcher, system status, configurable settings, and basic power controls.

The project targets Debian 13 (Trixie) on x86_64 / amd64 only.

## Features

- TV-friendly application launcher and keyboard navigation
- HTML, CSS, and vanilla JavaScript frontend
- Python backend using FastAPI and Uvicorn
- Local-only HTTP API on `127.0.0.1:8750`
- Google Chrome Stable as the supported browser
- Wayland session using labwc, started by greetd
- Persistent user-interface settings
- System status, restart, and shutdown controls
- systemd user services for the backend and launcher
- Debug section for development and test applications
- Web apps loaded automatically from individual `backend/config/apps/*.cfg` files

## Add applications

Create a `.cfg` file in `backend/config/apps/` to add a web app without changing
Python or JavaScript code. Each file defines its title, subtitle, icon, color,
URL, and browser options. See [App Configuration](docs/APP_CONFIGURATION.md)
for the complete format and examples.

## Configuration model

Each web app has its own INI-style `.cfg` file in `backend/config/apps/`. The backend discovers and validates these files, then generates a restricted Chrome command. A file can set the app ID, title, subtitle, text/emoji icon, tile color, URL, fullscreen mode, and Wayland option. The filename must match the app ID (for example, `netflix.cfg` with `id = netflix`). Invalid files are skipped and reported as `config_problems` by the system-status API.

The supplied app definitions are installed under `/opt/livingroomos/backend/config/apps/` and are administrator-owned. The writable runtime `settings.json` in `/var/lib/livingroomos/.config/livingroomos/` is reserved for server/UI settings and optional debug entries. See [App Configuration](docs/APP_CONFIGURATION.md).

## Supported platform

| Component | Supported configuration |
|---|---|
| Operating system | Debian 13 (Trixie) |
| Architecture | x86_64 / amd64 |
| Display server | Wayland |
| Compositor | labwc |
| Login manager | greetd |
| Browser | Google Chrome Stable |
| Backend | Python 3.11+, FastAPI, Uvicorn |

ARM and ARM64 are not supported.

## Repository layout

The application is contained in the `livingroomos/` directory of the repository:

```text
LivingroomOS/
├── README.md
└── livingroomos/
    ├── README.md
    ├── INSTALL.md
    ├── DEBIANINSTALL.md
    ├── ARCHITECTURE.md
    ├── CHANGELOG.md
    ├── LICENSE
    ├── backend/
    │   ├── api/
    │   ├── config/
    │   ├── services/
    │   └── tests/
    ├── frontend/
    │   ├── css/
    │   └── js/
    ├── docs/
    ├── system/
    │   ├── bin/
    │   ├── chrome/
    │   ├── greetd/
    │   ├── labwc/
    │   ├── polkit/
    │   └── systemd/user/
    ├── tools/
    ├── debian-packages.txt
    ├── requirements.txt
    └── run.sh
```

## Installation

Install and prepare Debian first, then install LivingroomOS:

1. [Debian 13 installation guide](DEBIANINSTALL.md)
2. [LivingroomOS installation guide](INSTALL.md)

Follow the guides in that order. The installation guide contains the required commands for deploying the application files and configuring the system services.

## Architecture

LivingroomOS has three main parts:

1. **Frontend:** the launcher, application tiles, settings, and system status.
2. **Backend:** a local FastAPI service for application management, settings, status, and fixed power actions.
3. **System integration:** greetd starts the labwc session; labwc starts the systemd user target, which runs the backend and Chrome launcher.

The backend is intended to listen only on `127.0.0.1`, port `8750` by default. Do not expose this port to an untrusted network.

## Security notes

- The backend accepts connections only from loopback hostnames.
- State-changing API requests require the `X-LivingroomOS: 1` header.
- Web apps are defined by administrator-managed `backend/config/apps/*.cfg` files; `backend/config/settings.json` contains server/UI settings and optional legacy/debug entries. The frontend submits app IDs, never shell commands.
- Restart and shutdown are mapped to fixed system commands and authorized by the bundled Polkit rule for the dedicated `livingroomos` account.
- The service account should not own or be able to modify application code under `/opt/livingroomos`.
- The backend and launched applications currently share the dedicated `livingroomos` user. This limits isolation if an application is compromised; see [the security documentation](docs/SECURITY.md).

## Development and tests

For local development and the complete test suite, create a Python virtual environment and install the development dependencies. This also installs the runtime dependencies from `requirements.txt`:

```bash
sudo apt install -y python3-venv
cd livingroomos
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
./run.sh
```

The backend listens on:

```text
http://127.0.0.1:8750
```

Run the automated tests from the `livingroomos/` directory using the same virtual environment:

```bash
.venv/bin/python -B -m unittest discover -s backend/tests -v
```

The `requirements-dev.txt` file includes `httpx`, which is required by the API tests. A successful unit-test run does not replace testing the complete installation on Debian 13 hardware.

## Testing status

LivingroomOS is under development and is intended for internal testing until the installation and hardware checks are complete.

Before treating it as a stable release, verify at least:

- Automatic login and labwc session startup
- Display resolution, scaling, and HDMI audio
- Chrome launch and application navigation
- Settings persistence across restarts
- Recovery after backend or browser failure
- Restart and shutdown behavior
- Compatibility with the intended remote control and target hardware

The kiosk, input-device, and power-management integration must be tested on the actual target hardware.

## License and third-party components

LivingroomOS is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0); see [LICENSE](LICENSE).

The project depends on external software including Debian, Python, FastAPI, Uvicorn, labwc, greetd, systemd, Polkit, and Google Chrome. Each component remains subject to its own license and distribution terms. Review third-party components and assets before redistributing a release.
