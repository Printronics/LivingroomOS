# Changelog

All notable changes to LivingroomOS are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning follows [Semantic Versioning](https://semver.org/).

The version number is defined in exactly one place: `backend/version.py`.

**Note:** Versions 0.1.0 through 0.4.0 were not released individually during development. They have been reconstructed retrospectively from the development steps so that each change remains traceable. Files affected by each step are listed where applicable.

## [0.6.0] – 2026-11-06

### Added
- Added individual INI-style `.cfg` files for web applications under `backend/config/apps/`; new web apps no longer require editing Python, JavaScript, or the central settings file.
- Added validation for app IDs, matching filenames, HTTP(S) URLs, browser executables, colors, and categories; invalid app files are skipped and reported through system status.
- Added documentation and automated tests for file-based app configuration.

### Changed
- Moved the example streaming apps from `settings.json` into separate Netflix, Disney+, YouTube, and Jellyfin configuration files.
- Kept `settings.json` for server/UI settings and optional legacy/debug application entries.

### Changed

- Renamed the entire project to LivingroomOS: directories, files, services, configuration, environment variables, and API headers.
- Restricted the target platform to Debian 13 `amd64` / x86_64; removed ARM target profiles and installation instructions.
- Switched browser launches to `google-chrome-stable`; Chrome is installed separately using the official vendor package and is not bundled with the project.
- Replaced the default applications with neutral, editable web application examples; no third-party logos, graphics, or provider assets are embedded.
- Reorganized the settings interface into General, System, and Debug sections; added additional display options and reduced-motion support.
- Removed test applications from the main launcher and moved them to the Debug tab.
- Added restart and shutdown through fixed backend actions and a bundled Polkit rule allowing the dedicated LivingroomOS service user and root while denying other users.
- Updated the installation, dependency, security, and architecture documentation.
- Fixed the labwc XML comment so the supplied configuration parses correctly.
- Documented and configured the greetd/`getty@tty1` conflict so greetd can own virtual terminal 1.
- Configured dedicated writable Chrome XDG configuration and cache directories in the launcher unit; the unit creates them before starting Chrome.
- Updated the installation guide to deploy the corrected `main` branch rather than the older `v0.6` tag, and included the Mesa DRI driver package.

### Verification

- The previous development run reported 21/21 consistency tests passing. The suite has since been extended; rerun it for this revision before release.
- API and process-start tests were partially blocked in this development environment by the unsafe file ownership of the supplied Python virtual environment interpreter; run them again on a regular Debian 13 system.
- Kiosk and power-management integration must be tested on real hardware.

## [0.5.0] – 2026-11-04

Standalone, installable project directory containing documentation, system files, dependency lists, and tests.

### Added

- `README.md`: project description, quick start, controls, tests, structure, configuration, HTTP interface, and testing status.
- `INSTALL.md`: complete installation on Debian 13 (amd64, x86_64), verification, troubleshooting, updates, and removal.
- `ARCHITECTURE.md`: description of the implemented architecture and justified differences from the initial design.
- `CHANGELOG.md`: this file.
- `docs/SYSTEM_DEPENDENCIES.md`: all Debian packages, kernel and Python requirements, directories, permissions, and x86_64 system details.
- `debian-packages.txt`, `debian-packages-optional.txt`: machine-readable package lists containing packages from the Debian archive only.
- `requirements.txt`, `requirements-dev.txt`: Python dependencies for runtime and tests, each with an explanation.
- `backend/version.py`: single source of the version number, used by `main.py` and the system status endpoint.
- `system/greetd/config.toml`, `system/bin/livingroomos-session`, `system/labwc/autostart`, `system/labwc/rc.xml`, `system/systemd/user/livingroomos-backend.service`, `livingroomos-shell.service`, `livingroomos.target`, `system/chrome/livingroomos.json`: files for TV operation (not yet tested on physical hardware).
- `system/bin/livingroomosctl`: HTTP utility for keyboard shortcuts (`home`, `status`, `wait`), using only the standard library.
- `tools/check_system.py`: system checker for x86_64 only; does not modify the system.
- Tests: `backend/tests/test_api.py`, `test_settings_store.py`, `test_livingroomosctl.py`, `test_project_consistency.py`. The latter automatically enforces project rules: every Python dependency must be listed in `requirements.txt`, every Debian package must be documented, architecture names must not appear in application code, scripts must not perform network-based installations, and required documents and references must exist.

### Changed

- `run.sh`: uses `.venv` if available; port can be configured through `LIVINGROOMOS_PORT`.
- `backend/main.py`: configuration path can be set through `LIVINGROOMOS_CONFIG`; version is read from `version.py`.

### Known Limitations

- `test_api.py` was not executed in the development environment because `fastapi` could not be installed; it was written but not run.
- `system/` and playback on streaming services have not been tested on physical hardware; ARM is not supported.

## [0.4.0] – 2026-11-04

TV-oriented navigation system.

### Changed

- `frontend/js/navigation.js`: rewritten as a standalone module. Geometry-based spatial navigation, fixed targets through `data-nav-*`, focus memory for each area, automatic focus restoration, Enter-key lock after opening a new dialog, protection against duplicate activation, edge indicators, and `Tab` as "next element".
- `frontend/js/remote.js`: rewritten. Key mappings for keyboards, HID remote controls (`BrowserBack`, `BrowserHome`, `ContextMenu`), and TV browsers (Android TV, Tizen, webOS); throttling of held direction keys, debouncing, no activation through auto-repeat, and `bind`/`emit` support for new remote controls and other input sources.
- `frontend/js/app.js`: `next`/`prev`, `data-repeatable` for settings rows, and protection against settings writes being overtaken by later key presses.
- `frontend/css/main.css`: focus ring fallback for every selectable element, edge animation.
- `frontend/css/layout.css`: `scroll-padding`.

### Added

- `frontend/dev/navigation-demo.html`, `demo.js`, `demo.css`: standalone navigation demo and keyboard test without the backend; displays the `key`, `code`, and `keyCode` of every key to help map new remote controls.

## [0.3.0] – 2026-11-03

Secure process management.

### Added

- `docs/SECURITY.md`: security concept (security objectives, threat model, measures, permissions, hardening, residual risks).
- `backend/tests/test_process_management.py`: 22 tests using real processes.
- `POST /api/v1/apps/{id}/stop`: stops only the specified application.

### Changed

- `backend/services/process_manager.py`: rewritten. Process groups and separate sessions, process identity validation using `/proc` start time and `pidfd`, duplicate-start prevention, crash classification (`stopped`, `ok`, `crashed`, `start_failed`, `ended`), remaining-process detection using the exact `--user-data-dir` value, log files with rotation, backend lock, state file, and recovery after a backend crash.
- `backend/services/app_launcher.py`: rewritten. Configuration validation (placeholders, prohibited switches, browsers require their own profile, environment variables), path, ownership and permission checks, trusted directories, filtered environment, and return to the launcher.
- `backend/main.py`: lifecycle management with locking and orderly shutdown.
- `backend/api/apps.py`: new stop route.
- `backend/config/settings.json`: `trusted_bin_dirs`, `startup_grace_s`, `stop_timeout_s`, `return_to_launcher_command`.

## [0.2.0] – 2026-11-03

Working minimal prototype.

### Added

- Frontend: `frontend/index.html`, `css/main.css`, `css/layout.css`, `js/app.js`, `js/navigation.js`, `js/remote.js`, `js/api.js`. Dark TV interface, large tiles, arrow-key navigation, Enter and Escape support, focus states, dialogs for launch, crashes, and missing backend.
- Backend: `backend/main.py`, `api/apps.py`, `api/system.py`, `api/settings.py`, `services/app_launcher.py`, `services/process_manager.py`, `services/settings_store.py`, `config/settings.json`, `requirements.txt`, `run.sh`. Local HTTP interface under `/api/v1`, no arbitrary shell commands from the frontend, and error handling for missing or crashed services.

### Decision

- Status polling instead of SSE. See `ARCHITECTURE.md`, Section 11, for the rationale.

## [0.1.0] – 2026-11-02

### Added

- Initial software architecture (document, no application code): modules, responsibilities, communication, process management, x86_64 target architecture, resource and security risks, and justified design decisions. Its implementation and differences from the original design are documented in `ARCHITECTURE.md`.
