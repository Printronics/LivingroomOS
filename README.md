# LivingroomOS

LivingroomOS is a Linux-based operating system environment designed for living rooms and media center setups. Built on Debian 13, it provides a TV-oriented interface for accessing and managing web applications and media services.

**Current version:** 0.6.0  
**Project status:** In development  
**Target platform:** Debian 13 – x86_64 (AMD64)

## Features

- TV-oriented user interface
- Centralized application management
- Integration of web-based applications
- Configurable application settings
- System controls and power management
- Security-focused system configuration
- Recovery and maintenance functionality

## Requirements

The intended target environment includes:

- Debian 13 (64-bit, AMD64)
- Python 3.11 or newer
- A compatible graphical environment
- Network connectivity for web applications and updates
- Suitable input devices, such as a remote control, keyboard, or mouse

For detailed dependency information, see [System Dependencies](livingroomos/docs/SYSTEMABHAENGIGKEITEN.md).

## Installation

Installation instructions are available in the following documents:

- [Debian Installation Guide](livingroomos/DEBIANINSTALL.md)
- [Installation Overview](livingroomos/INSTALL.md)

Please review the requirements and instructions before installing LivingroomOS on a target system.

## Project Structure

```text
LivingroomOS/
├── README.md
├── LICENSE
└── livingroomos/
    ├── README.md
    ├── INSTALL.md
    ├── DEBIANINSTALL.md
    ├── ARCHITECTURE.md
    ├── CHANGELOG.md
    ├── LICENSE
    ├── backend/
    │   ├── config/
    │   └── tests/
    ├── docs/
    │   ├── SICHERHEIT.md
    │   └── SYSTEMABHAENGIGKEITEN.md
    ├── system/
    └── ...
```

This is a simplified overview of the main project directories.

## Running Tests

The automated test suite can be run from the `livingroomos/` directory:

```bash
python3 -B -m unittest discover -s backend/tests -v
```

The tests cover selected aspects of the project, including project structure, configuration files, and system components.

A successful test run does not necessarily mean that all features have been verified on the intended target hardware.

## Documentation

Additional technical information is available in the following documents:

- [Architecture](livingroomos/ARCHITECTURE.md)
- [Changelog](livingroomos/CHANGELOG.md)
- [Security Documentation](livingroomos/docs/SICHERHEIT.md)
- [System Dependencies](livingroomos/docs/SYSTEMABHAENGIGKEITEN.md)

## Development Status

LivingroomOS is currently under active development and testing.

Before a stable release, the following areas still require verification:

- Complete testing on the intended target hardware
- Automatic startup and login
- Display and browser integration
- Application navigation and settings persistence
- Power management
- Recovery functionality
- Final installation and security testing

## License

LivingroomOS is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

The license text is provided in the repository:

- [Root LICENSE](LICENSE)
- [Application LICENSE](livingroomos/LICENSE)

See the license files for the complete terms and conditions.

## Disclaimer

LivingroomOS is currently a development project and is not yet considered a finished product. Features, configurations, and installation procedures may change as development continues.
