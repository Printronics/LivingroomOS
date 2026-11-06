# LivingroomOS

**A lightweight, keyboard-friendly living-room interface for Debian 13 (x86_64).**

LivingroomOS is a minimal desktop environment designed for TV screens and living-room PCs. It provides a simple application launcher, system status information, configurable settings, and basic system power controls.

The project is designed around Debian 13 and targets x86_64 systems exclusively.

## Features

- TV-friendly application launcher
- Simple, clean interface built with HTML, CSS, and vanilla JavaScript
- Python backend using FastAPI
- Local-only backend API
- Google Chrome Stable as the supported browser
- Wayland session using labwc
- greetd-based automatic session startup
- System status information
- Settings interface for user preferences
- System restart and shutdown controls
- Debug section for development and test applications
- systemd integration
- Restricted system power operations

## Platform support

| Component | Supported configuration |
|---|---|
| Operating system | Debian 13 |
| Architecture | x86_64 / amd64 |
| Display server | Wayland |
| Window manager | labwc |
| Browser | Google Chrome Stable |
| Login manager | greetd |
| Backend | Python 3, FastAPI, Uvicorn |
| Frontend | HTML, CSS, JavaScript |

ARM and ARM64 systems are not supported.

## Project structure

```text
LivingroomOS/
├── backend/
│   └── main.py
├── frontend/
│   ├── index.html
│   ├── css/
│   └── js/
├── config/
├── system/
│   ├── bin/
│   ├── labwc/
│   ├── greetd/
│   ├── systemd/
│   └── polkit/
├── tools/
│   └── check_system.py
├── tests/
├── debian-packages.txt
├── run.sh
├── README.md
├── INSTALL.md
├── ARCHITECTURE.md
└── CHANGELOG.md
```

The exact contents may vary between development versions.

## Architecture

LivingroomOS consists of three main layers:

1. **Frontend:** Displays the launcher, settings, application entries, and system information.
2. **Backend:** Provides a local HTTP API for application data, settings, system status, and power operations.
3. **System integration:** Starts the graphical session and connects the interface to Debian system services.

The backend is intended to listen only on `127.0.0.1`, using port `8750` by default.

## Security

LivingroomOS is designed to keep system access limited:

- The backend listens on localhost rather than exposing its API to the network.
- State-changing API requests require the LivingroomOS request header.
- Power operations use fixed system commands.
- Polkit rules restrict permitted power operations to the dedicated LivingroomOS service account.
- Executable files and configuration are expected to have appropriate ownership and permissions.

Do not expose the backend port to an untrusted network.

## Installation

For a complete installation guide, see [INSTALL.md](INSTALL.md).

The installation guide covers:

- Debian 13 preparation
- Required packages
- Google Chrome installation
- Service account setup
- Project deployment
- systemd configuration
- greetd and labwc setup
- Power management permissions
- Initial testing and troubleshooting

## Development

Run the backend manually during development:

```bash
cd /opt/livingroomos
./run.sh
```

The default local address is:

```text
http://127.0.0.1:8750
```

For development and internal testing, use a regular non-root account wherever possible.

Run the test suite with:

```bash
python3 -B -m unittest discover -s tests -v
```

Some system integration tests require a properly configured Debian environment. File ownership and executable permission checks may also behave differently when tests are run as root or inside containers.

## Internal testing status

LivingroomOS is intended for internal testing and development.

Before using it as a daily living-room system, verify:

- Startup and automatic login
- Display resolution and scaling
- Google Chrome launch behavior
- Application navigation
- Settings persistence
- Restart and shutdown behavior
- Recovery from backend or browser failures
- Compatibility with the target hardware

System power controls should be tested carefully, preferably on a dedicated test machine.

## License and third-party components

LivingroomOS is intended to use original project code and assets wherever possible.

The project depends on external software such as Debian, Python, FastAPI, Uvicorn, labwc, greetd, systemd, Polkit, and Google Chrome. These components remain subject to their respective licenses and terms.

Any third-party assets or dependencies added in the future must be reviewed for licensing and redistribution requirements.

## Project goals

LivingroomOS aims to provide a small, maintainable, and understandable living-room interface without the overhead of a traditional desktop environment.

The focus is on simplicity, predictable system behavior, and compatibility with Debian 13 on x86_64 hardware.
