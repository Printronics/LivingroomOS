# LivingroomOS

**A lightweight, keyboard-friendly living-room interface for Debian 13 (x86_64).**

LivingroomOS is a minimal living-room interface designed for TV screens and dedicated living-room PCs. It provides an application launcher, system status information, configurable settings, and basic system power controls.

The project targets Debian 13 (Trixie) on x86_64 / amd64 systems exclusively.

## Features

- TV-friendly application launcher
- Keyboard-oriented user interface
- HTML, CSS, and vanilla JavaScript frontend
- Python backend using FastAPI
- Local-only backend API
- Google Chrome Stable as the supported browser
- Wayland session using labwc
- greetd-based automatic session startup
- System status information
- Settings interface
- Restart and shutdown controls
- Debug section for development and test applications
- systemd integration
- Restricted system power operations

## Platform support

| Component | Supported configuration |
|---|---|
| Operating system | Debian 13 (Trixie) |
| Architecture | x86_64 / amd64 |
| Display server | Wayland |
| Window manager | labwc |
| Browser | Google Chrome Stable |
| Login manager | greetd |
| Backend | Python 3, FastAPI, Uvicorn |
| Frontend | HTML, CSS, JavaScript |

ARM and ARM64 systems are not supported.

## Repository structure

The application and its documentation are located in the `livingroomos/` subdirectory.

```text
LivingroomOS/
├── README.md
└── livingroomos/
    ├── README.md
    ├── INSTALL.md
    ├── DEBIANINSTALL.md
    ├── ARCHITECTURE.md
    ├── CHANGELOG.md
    ├── backend/
    ├── frontend/
    ├── config/
    ├── system/
    ├── tools/
    ├── tests/
    ├── debian-packages.txt
    └── requirements.txt
```

The exact contents may vary between development versions.

## Installation

Installation consists of two steps. Follow the guides in this order:

1. [Debian 13 base installation](livingroomos/DEBIANINSTALL.md) – install and prepare a minimal Debian 13 system.
2. [LivingroomOS installation](livingroomos/INSTALL.md) – deploy and configure LivingroomOS.

The application documentation is located in the [`livingroomos/`](livingroomos/) directory.

## Architecture

LivingroomOS consists of three main layers:

1. **Frontend:** Displays the launcher, settings, application entries, and system information.
2. **Backend:** Provides a local HTTP API for application data, settings, system status, and power operations.
3. **System integration:** Connects the interface to Debian system services and starts the graphical session.

The backend is intended to listen only on `127.0.0.1`, using port `8750` by default.

See [ARCHITECTURE.md](livingroomos/ARCHITECTURE.md) for further details.

## Security

LivingroomOS is designed to limit system access:

- The backend listens on localhost rather than exposing its API to the network.
- State-changing API requests require the LivingroomOS request header.
- Power operations use fixed system commands.
- Polkit rules restrict permitted power operations to the intended service account.
- Executable files and configuration are expected to have appropriate ownership and permissions.

Do not expose the backend port to an untrusted network.

## License

LivingroomOS is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

The license information is available through the [LivingroomOS repository on GitHub](https://github.com/Printronics/LivingroomOS).

Third-party software and components remain subject to their own licenses and terms. In particular, Google Chrome is distributed under Google's own terms and is not relicensed under the project's AGPL license.

## Development and testing

For development, work from the application directory:

```bash
cd livingroomos
```

Run the test suite with:

```bash
python3 -B -m unittest discover -s tests -v
```

Some system integration tests require a properly configured Debian environment. File ownership and executable permission checks may behave differently when tests are run as root or inside containers.

## Testing status

LivingroomOS is intended for internal testing and development.

Before using it as a daily living-room system, verify:

- Automatic startup and login
- Display resolution and scaling
- Google Chrome launch behavior
- Application navigation
- Settings persistence
- Restart and shutdown behavior
- Recovery from backend or browser failures
- Compatibility with the target hardware

System power controls should be tested carefully, preferably on a dedicated test machine.

## Project goals

LivingroomOS aims to provide a small, maintainable, and understandable living-room interface without the overhead of a traditional desktop environment.

The focus is on simplicity, predictable system behavior, and compatibility with Debian 13 on x86_64 hardware.
