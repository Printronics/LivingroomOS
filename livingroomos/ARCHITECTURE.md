# LivingroomOS – Software Architecture

**Status: Version 0.6.0**

This document describes what is **actually implemented**. Where the implementation differs from the original architectural design, the reasons are documented in Section 11.

The security concept is documented in [docs/SICHERHEIT.md](docs/SICHERHEIT.md), and the system packages are listed in [docs/SYSTEMABHAENGIGKEITEN.md](docs/SYSTEMABHAENGIGKEITEN.md).

## 1. Goals and Design Principles

LivingroomOS is an appliance-style system: a Debian 13 computer boots directly into an HTML interface without a traditional desktop environment. Streaming services, video websites, a personal media library, and other services run alongside it as replaceable external applications.

At runtime, the system consists of only **a compositor, a browser, and one Python service**.

1. The backend is the only component that starts and stops processes. The frontend displays information and sends requests (for example, "start app X").
2. Exactly one foreground application runs at a time. This reduces memory usage and makes focus management and returning to the launcher predictable.
3. New applications are added through an entry in `settings.json`, without requiring additional application code.
4. All hardware-specific details (x86_64) belong in configuration and system packages, never in application code.
5. Returning to the launcher must also work if an external application freezes or crashes.
6. No unnecessary frameworks: no desktop environment, no frontend framework, and no build step.

| Area | Decision |
|---|---|
| Initial target hardware | Intel NUC (x86_64) |
| Future target hardware | x86_64 PC (Intel/AMD) |
| Operating system | Debian 13 "Trixie", packages from the Debian archive only |
| Input | keyboard and mouse (arrow keys, Enter, Back, Home); |
| Initial non-goals | File manager, built-in media library, multi-user operation, remote access over the network |

## 2. System Overview

```text
 Power on
     │
     ▼
 systemd ──► greetd ──(initial_session, user livingroomos)──► livingroomos-session
                                                                  │  starts labwc, restarts after crashes
                                                                  ▼
                                            labwc (Wayland compositor, kiosk configuration)
                                                                  │  autostart: systemctl --user start livingroomos.target
                          ┌───────────────────────────────────────┴──────────────────────────┐
                          ▼                                                                   ▼
        livingroomos-backend.service                                              livingroomos-shell.service
        Uvicorn + FastAPI  127.0.0.1:8750                                     Google Chrome --kiosk  →  http://127.0.0.1:8750/
        ┌─────────────────────────────┐                                                      │
        │ api/       REST /api/v1/*   │◄────────── fetch (JSON, X-LivingroomOS) ─────────────────┘
        │ services/  app_launcher     │                                       Frontend: HTML/CSS/Vanilla-JS
        │            process_manager  │                                       remote.js → navigation.js → app.js
        │            settings_store   │
        └──────────────┬──────────────┘
                       │ asyncio.create_subprocess_exec (no shell, separate process group)
                       ▼
        External application: google-chrome-stable --app=… --user-data-dir=<separate profile> (only one at a time)
```

Remote-control buttons do **not** communicate through the backend. They reach the focused window as keyboard events through the compositor. Only the Home button is a compositor shortcut that calls `livingroomosctl home` (see Section 6).

## 3. Project Structure and Responsibilities

Each task has exactly one designated location. Dependencies point downward only: `api → services`. The services know nothing about FastAPI or the frontend.

### 3.1 Backend (`backend/`)

| Module | Responsibility | Explicitly not responsible for |
|---|---|---|
| `main.py` | Application factory, lifecycle (acquiring the lock, stopping applications), host validation, CSRF header, security headers, error format, serving the frontend | Business logic |
| `version.py` | Single source of the version number | |
| `api/apps.py` | REST router for applications: list, status, start, stop; translates exceptions into HTTP status codes | Processes, filesystem |
| `api/system.py` | `health`, `system/status`, and allowlisted restart/shutdown actions | Arbitrary system commands |
| `api/settings.py` | Read and modify interface settings (input validation with Pydantic) | Other configuration sections |
| `services/app_launcher.py` | Converts an app ID into a validated launch command; checks configuration, executable path, ownership, permissions, profile directory, and environment; provides the return command | Process monitoring |
| `services/process_manager.py` | Starts, monitors, and stops exactly one application; prevents duplicate starts, detects crashes, manages process groups, finds remaining child processes, stores state, and locks the backend | Building the command line |
| `services/settings_store.py` | Loads and writes `settings.json` atomically and thread-safely; only the `ui` section is writable | Application validation |
| `config/settings.json` | Server settings, UI settings, and application definitions | Runtime state |
| `tests/` | Unit, integration, and consistency tests (Section 9) | |

### 3.2 Frontend (`frontend/`)

| File | Responsibility |
|---|---|
| `index.html` | Structure: header, views, dialog, toast notifications |
| `css/main.css` | Design tokens, colors, typography, focus states, dialog |
| `css/layout.css` | Grid, spacing (including overscan), 16:9 scaling |
| `js/app.js` | State and rendering: tiles, settings, dialogs, status polling, crash handling |
| `js/api.js` | `fetch` wrapper with consistent error handling (`ApiError`) |
| `js/navigation.js` | Standalone spatial focus navigation, focus restoration, protection against duplicate activation |
| `js/remote.js` | Standalone keyboard and remote-control input handling, debouncing, repeat protection |
| `dev/` | Navigation demo and keyboard test; works without the backend and is not part of normal operation |

`app.js` is the only module that brings `navigation.js`, `remote.js`, and `api.js` together. The two navigation modules do not know about each other or the application.

### 3.3 Session Configuration (`system/`, files only)

| File | Purpose |
|---|---|
| `greetd/config.toml` | Automatic login for user `livingroomos` into `livingroomos-session`, with text login as a fallback |
| `bin/livingroomos-session` | Starts labwc and restarts it after crashes (up to 5 crashes within 60 seconds) |
| `labwc/autostart`, `labwc/rc.xml` | Imports `WAYLAND_DISPLAY`, starts `livingroomos.target`, configures kiosk mode without default keyboard shortcuts, and defines the Home shortcut |
| `systemd/user/*` | `livingroomos-backend.service`, `livingroomos-shell.service`, `livingroomos.target` |
| `chrome/livingroomos.json` | Google Chrome policies (developer tools disabled, password manager disabled, synchronization disabled) |
| `bin/livingroomosctl` | Small utility that communicates with the backend over HTTP only (`home`, `status`, `wait`) |

`tools/check_system.py` checks whether a system meets the requirements (architecture, Python, kernel, packages, and configuration).

## 4. Communication Between Frontend and Backend

The frontend communicates exclusively with `http://127.0.0.1:8750`. Commands use REST endpoints under `/api/v1`; status information is retrieved through polling.

| Method and path | Purpose | Special responses |
|---|---|---|
| `GET /api/v1/health` | Readiness check (waits for the shell unit) | |
| `GET /api/v1/system/status` | Version, uptime, architecture, Python version, `config_problems`, application status | |
| `GET /api/v1/apps` | Application list (without commands) and status | |
| `GET /api/v1/apps/status` | `state`, `app_id`, `pid`, `last_exit` | |
| `POST /api/v1/apps/{id}/launch` | Start an application | 202; 404 unknown; 409 `busy`; 422 `not_installed` |
| `POST /api/v1/apps/stop` | Stop the active application | |
| `POST /api/v1/apps/{id}/stop` | Stop only the specified application | 409 `not_running` if it is not running |
| `POST /api/v1/system/power/restart`, `POST /api/v1/system/power/shutdown` | Request one of the two fixed system power actions | 202 accepted; unsupported actions return 404 |
| `GET /api/v1/settings`, `PATCH /api/v1/settings` | Read and update interface settings (`ui`) | 422 for unknown keys |

Rules:

- **Intent only:** The frontend sends an application ID. The executable, arguments, and environment come exclusively from `settings.json` and are never included in the response.
- **Idempotency:** Launching an application that is already running returns the same status. Launching a different application while one is running returns 409 with the current status; the user decides what to do in the dialog.
- **Write protection:** All write requests require the `X-LivingroomOS: 1` header (CSRF protection). `TrustedHostMiddleware` allows only `127.0.0.1` and `localhost` (DNS rebinding protection). Responses include a strict Content Security Policy.
- **Error format:** `{"error": {"code": "...", "message": "..."}}`. The `message` is intended for humans and does not reveal internal details.
- **Versioned paths** (`/api/v1`) allow a future network-based frontend (for example, a phone) to remain compatible.
- **Status polling:** Every 1.2 seconds while an application is starting or running, every 4 seconds while idle, at least every 6 seconds while the window is hidden, and every 3 seconds if the backend is unavailable. `last_exit.seq` ensures that each application exit is reported exactly once.

## 5. Process Management for External Applications

The `ProcessManager` state machine:

```text
 idle ──start()──► starting ──(startup grace period elapsed)──► running
   ▲                  │                                             │
   │                  └───── exits during grace period ─────────┐  │ stop() or exit
   │                                                             ▼  ▼
   └─────────────── cleanup, report exit (exactly once) ◄── stopping
```

A launch is only possible from `idle`. The state is **reserved before the first `await`**, so even simultaneous requests cannot trigger duplicate launches.

**Starting an application.** The `AppLauncher` builds a `LaunchSpec` (absolute, validated path; argument list; filtered environment; log file; instance identifier). The `ProcessManager` calls `asyncio.create_subprocess_exec`: never a shell, `stdin` is `/dev/null`, `start_new_session=True` (separate session and process group), `umask 0077`, and output is written to `logs/<id>.log` (0600, rotated at 1 MiB).

**Monitoring.** A watcher task waits for the process to exit. The exit is classified as follows:

| Reason | Meaning |
|---|---|
| `stopped` | Stopped by the user or backend |
| `ok` | Exit code 0 after the grace period |
| `crashed` | Exit code not equal to 0 or signal received after the grace period |
| `start_failed` | Exit during the grace period (for exit code 0, only if the application was expected to run continuously) |
| `ended` | Adopted application exited; cause unknown |

The crash dialog appears for `crashed` and `start_failed`. Whenever an application exits, the state returns to `idle`, the frontend displays the launcher again, and the optional `return_to_launcher_command` (for example, `wlrctl`) can restore focus.

**Stopping an application.** `stop()` sends SIGTERM to the application's **process group**, followed by SIGKILL after `stop_timeout_s`. Google Chrome renderer processes that have escaped the group are located using the exact argument value `--user-data-dir=<profile for this application>` (never by executable name alone) and terminated using `pidfd`. Other browser windows remain unaffected. Ownership and process start time are checked before every signal.

**Process identity.** A process is identified using `/proc/<pid>/stat` (start time) and `pidfd_open`. PID reuse therefore cannot cause an unrelated process to be terminated.

**Backend crash.** `state.json` (0600, stored in RAM under `$XDG_RUNTIME_DIR`) holds the PID and start time of the running application. A new backend can adopt it if the information is still valid. A lock file (`flock`) prevents two backend instances from running simultaneously. However, with the unit's default `KillMode=control-group`, the application exits together with the backend. Adoption is only relevant if the administrator selects `KillMode=process`(see `docs/SICHERHEIT.md`).

## 6. Boot and Startup Sequence

1. Firmware, bootloader, kernel, systemd.
2. `greetd` starts an `initial_session` for user `livingroomos` during boot. PAM creates a logind session, providing `XDG_RUNTIME_DIR` and a `systemd --user` manager.
3. `livingroomos-session` starts `labwc` in a loop. greetd runs the `initial_session` only once per boot, so the restart logic is implemented in the script. After 5 crashes within 60 seconds, the script exits and greetd displays the text login.
4. The labwc autostart imports `WAYLAND_DISPLAY` into the systemd user manager and starts `livingroomos.target`.
5. `livingroomos-backend.service` (Uvicorn) starts first, followed by `livingroomos-shell.service` (Google Chrome in kiosk mode; waits for `/api/v1/health` using `livingroomosctl wait`). Both use `Restart=on-failure`. The shell unit depends on the backend only through `After=`, so the launcher remains open during a backend restart and displays "Backend unavailable".

The remote control's **Home button** (`XF86HomePage`) is a labwc shortcut (`rc.xml`) that calls `livingroomosctl home`. This sends `POST /api/v1/apps/stop`. If the remote does not send a Home key, `Ctrl+Alt+Home` stops the application.

Target: launcher visible in under 15 seconds (NUC) or 25 seconds (Pi). These are assumptions and have not yet been measured.

## 7. Security (Summary)

The backend listens only on loopback and does not use authentication, because anyone with access to `127.0.0.1` already has access to the computer. Protection is intended against accidental misuse and websites running in the browser (CSRF, DNS rebinding), not against an attacker with physical access to the device.

The core measures are: predefined applications only, no shell, validated paths and permissions, filtered environment, separate browser profiles, prohibited browser switches, and targeted process termination.

For the complete security concept, see `docs/SICHERHEIT.md`.

## 8. Target Architecture

LivingroomOS supports only `amd64` / x86_64. ARM processors are rejected by `tools/check_system.py`.

## 9. Tests

| File | What it tests |
|---|---|
| `test_process_management.py` | Real processes: start, stop, SIGKILL, process groups, crash types, logs, duplicate-start prevention, permission checks, profile directories, finding remaining processes, backend lock, adoption, PID reuse |
| `test_settings_store.py` | Loading, error handling, atomic and concurrent writes |
| `test_livingroomosctl.py` | Utility tested against a test server |
| `test_project_consistency.py` | Shipped configuration, `requirements.txt`, Debian package documentation, x86_64 target architecture, no network installation commands, required documentation and references |
| `test_api.py` | HTTP interface: status codes, headers, error format (requires `fastapi` and `httpx`; otherwise skipped) |

During development, the interface was tested with Playwright and Google Chrome (navigation, dialogs, crashes, offline behavior). These scripts are not part of the project because they require Playwright.

## 10. Important Decisions and Rationale

| Decision | Rationale | Alternative |
|---|---|---|
| labwc instead of a desktop environment or Cage | Lightweight Wayland compositor with keyboard shortcuts and window rules; no desktop required | Cage (too restrictive for shortcuts) |
| greetd instead of GDM/SDDM | Lightweight automatic login without a graphical greeter | getty autologin plus profile script |
| Google Chrome as the only browser | All target services are websites; one browser with separate profiles | Firefox (a second profile model) |
| Python 3 + FastAPI + Uvicorn | Available as Debian packages, intended for x86_64, low overhead | Go binary (additional toolchain) |
| Frontend without a framework or build step | Less memory usage and attack surface; nothing to compile | Preact/Vite |
| Process management using only the standard library | No extra dependency; easy to test with real processes | `psutil` |
| One foreground application | Predictable focus and return behavior, lower RAM usage | Multiple windows |
| Loopback only, no network access | Smallest attack surface | LAN remote control (future) |
| JSON configuration | `json` is part of the standard library; required by the project specification (`settings.json`) | TOML |
| Debian packages instead of PyPI by default | One package source; security updates through `apt` | Virtual environment with pip (Option B) |
| Program code under `/opt` owned by root | The application cannot modify itself | Installation in the user's home directory |

## 11. Differences from the Original Design

The first design was a target architecture. The implementation is a prototype that approaches it incrementally. The differences and their reasons are documented below:

| Original design | Implementation | Reason |
|---|---|---|
| Applications as transient systemd units (`systemd-run`), `livingroomos-apps.slice`, `MemoryMax` | Direct launch with `create_subprocess_exec`, separate process group, termination using signals | Project requirement ("subprocess without `shell=True`", monitor PIDs, targeted termination); testable without systemd. `LaunchSpec` remains the interface, so a runner using `systemd-run` can replace it later. **Consequence:** no memory limit and no cgroup control over Google Chrome helper processes; mitigated by process groups and finding remaining processes. |
| SSE stream `/api/v1/events` with snapshot | Polling `/apps/status` (1.2 to 6 seconds) | SSE requires a persistent connection, event bus, and reconnection logic. For state that changes infrequently, polling is simpler and inexpensive at 4-second idle intervals. **Consequence:** up to 1.2 seconds of delay for state changes. Can be replaced without changing the API contract. |
| Package `livingroomos/` with `registry`, `supervisor`, `launchers`, `runner`, `compositor`, `events`, `platform`, `security`, `config` | Flat `api/` and `services/` modules using the filenames specified by the project requirements | The required filenames were specified by the project. Responsibilities are still separated (configuration validation and command construction in `AppLauncher`, process lifecycle in `ProcessManager`). |
| TOML configuration with Pydantic and layers (`/etc`, user) | One JSON file, used at runtime from `~/.config/livingroomos/settings.json` (`LIVINGROOMOS_CONFIG`) | The project specified `settings.json`. Validation is implemented in `parse_apps`. |
| Endpoints `/state`, `/home`, `/session/foreground/stop`, `/audio/volume`, `/system/power`, `/events` | `/apps/status`, `/apps/stop`, `/apps/{id}/stop`, `/system/status`, `/system/power/{restart,shutdown}`, `/settings` | Only the two fixed power actions (restart and shutdown) are implemented; audio and advanced power management are not. |
| RFC 9457 error format | `{"error": {"code", "message"}}` | Simpler for the frontend; conveys the same information. |
| Security middleware with Origin validation and JSON requirement | Host validation plus required `X-LivingroomOS` header | The custom header provides CSRF protection without Origin evaluation. |
| Separate compositor bridge module (`WlrctlBridge`) | Optional `server.return_to_launcher_command` | Focus usually returns automatically after the application window closes; the command is an additional measure. |
| Frontend `main.js`, `nav.js`, `events.js`, `store.js`, `views/`, `components/` | `app.js`, `navigation.js`, `remote.js`, `api.js` | Filenames were specified by the project requirements. |
| `platform/` profiles for architectures | None; architecture is only included in system status | There is currently nothing architecture-specific. Profiles can be added if measurements on the Pi require them. |

Unchanged from the original design: the single-foreground-application principle, the startup chain greetd → `livingroomos-session` → labwc → `livingroomos.target`, the two units, `livingroomosctl`, loopback-only access, versioned paths, idempotency, and HTTP 409 on conflicts.

## 12. Resources and Risks

| Topic | Assessment and mitigation |
|---|---|
| Memory usage | Google Chrome is the largest consumer (launcher and application together use several hundred MB). Only one foreground application is allowed; use `zram-tools` on the Pi. No hard memory limit is configured (see the difference regarding `MemoryMax`). |
| Idle CPU usage | The backend waits; polling occurs every 4 seconds; animations are short and CSS-only. |
| Widevine (streaming services) | Debian's Google Chrome package does not include Widevine. Playback by streaming services is **not guaranteed**; the project does not install Widevine. |
| Hardware video decoding | VA-API may be available on the NUC; it is not guaranteed on the Pi. Measure on the target hardware. |
| Recovery from misconfiguration | Kiosk labwc disables console switching. SSH is the recovery path and should be included in the installation. |
| Application and backend share a UID | A compromised application could affect the backend. Further isolation could use `systemd-run` with sandboxing (see future work). |
| Untested system files | `system/` (greetd, labwc, systemd) was written based on documentation but has not been tested on physical hardware. |

## 13. Future Work

- Run applications as transient systemd units with `MemoryMax` and sandboxing. Only the runner in `ProcessManager` needs to change.
- Use SSE for status events instead of polling.
- Add platform profiles (Google Chrome flags per device) after measurements on x86_64 PCs.
- Implement audio (volume control) as a separate, small service.
- Extend power management only if needed (for example, suspend); restart and shutdown are already implemented.
