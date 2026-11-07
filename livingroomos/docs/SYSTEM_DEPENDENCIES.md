# LivingroomOS – Debian System Dependencies

This document lists everything LivingroomOS needs outside Python packages.
Python libraries are listed in `requirements.txt`. The machine-readable
package lists are `debian-packages.txt` (required) and
`debian-packages-optional.txt` (optional). A test
(`backend/tests/test_project_consistency.py`) ensures that every package
listed there is also documented here.

Target system: **Debian 13 "Trixie" on `amd64` / x86_64 (Intel/AMD)**. ARM is
not supported.

## 1. Required packages

| Package | Purpose | Notes |
| --- | --- | --- |
| `python3` | Backend runtime | Debian 13 provides 3.13; at least 3.11 is required |
| `python3-fastapi` | Web framework (REST API, middleware) | Installs `python3-starlette` and `python3-pydantic` as dependencies |
| `python3-uvicorn` | ASGI server on 127.0.0.1 | The standard Python implementation is sufficient; `uvloop` is not required |
| Google Chrome | Launcher window and web apps | Official Google `.deb`, installed separately; not included in the Debian archive |
| `labwc` | Wayland compositor | Install with `--no-install-recommends` to avoid installing Xwayland |
| `greetd` | Automatic login to the labwc session | Includes `agreety` as a fallback login |
| `systemd` | Services (user units) | Included with Debian |
| `dbus-user-session` | Starts `systemd --user` for each session | User units will not run without this package |
| `libpam-systemd` | logind session | Grants the user session access to the GPU and input devices |
| `polkitd` | Authorization for restart and shutdown | Loads the supplied rule `system/polkit/50-livingroomos-power.rules` from `/etc/polkit-1/rules.d/` |
| `pipewire` | Audio | |
| `pipewire-pulse` | Audio compatibility | Google Chrome uses PulseAudio |
| `wireplumber` | PipeWire session manager | |
| `libgl1-mesa-dri` | Graphics drivers | Intel/AMD graphics |
| `fonts-noto-core` | Fonts | Interface and websites |
| `fonts-noto-color-emoji` | Emoji | |

## 2. Optional packages

| Package | Purpose |
| --- | --- |
| `unzip` | Only needed to extract the `livingroomos.zip` project archive |
| `wlrctl` | Explicitly return focus to the launcher after an app exits (`server.return_to_launcher_command`). Before use, check whether the package is available on Debian 13 and whether labwc supports the required protocol with `apt-cache policy wlrctl`. Without this package, focus returns to the launcher automatically when the app window closes. |
| `wlr-randr` | Set the resolution and refresh rate in the labwc autostart file (for example, 1920×1080 for a TV) |
| `python3-venv` | Only needed for the pip-based installation path (`INSTALL.md`, option B) |
| `python3-httpx` | Only needed for API tests; those tests are skipped if this package is missing |
| `intel-media-va-driver` | Hardware video decoding (VA-API) on Intel NUCs |
| `mesa-va-drivers` | VA-API for AMD graphics |
| `vainfo` | Diagnostic tool for checking which codecs are hardware-accelerated by the GPU |
| `unattended-upgrades` | Automatic security updates, especially for Google Chrome |
| `zram-tools` | Compressed swap in memory; optional on low-memory x86_64 devices |

## 3. Kernel, Python, and filesystem

| Requirement | Reason |
| --- | --- |
| Linux ≥ 5.3 | `pidfd_open` and `pidfd_send_signal` identify processes without PID-reuse ambiguity. Debian 13 provides kernel 6.12. |
| Python ≥ 3.11 | `TimeoutError` behavior in `asyncio.wait_for`, the `umask=` parameter in `create_subprocess_exec`, and `Path.is_relative_to` |
| `/proc` mounted | Process start time and arguments are needed for identity checks |
| `fcntl.flock` | Lock file ensures that only one backend manages the processes |
| Unix-permission-aware filesystem | Supports modes 0700/0600 for profiles, logs, and the state file |

`tools/check_system.py` checks these requirements and reports missing items.

## 4. Users, permissions, and directories

| Item | Configuration |
| --- | --- |
| Operating-system user | `livingroomos`, a regular account without `sudo` or special capabilities |
| Additional groups | Normally none; logind grants GPU and audio access per session. Add `video`, `render`, or `audio` only if a test on the target system requires it |
| `/opt/livingroomos` | Owned by `root`, readable by everyone, not writable by `livingroomos` (application code cannot modify itself) |
| `~/.config/livingroomos/settings.json` | Owned by `livingroomos`, mode 0600; the backend writes back only the `ui` section |
| `~/.local/share/livingroomos/profiles/<id>/` | Browser profiles, mode 0700 |
| `~/.local/share/livingroomos/logs/<id>.log` | App output, mode 0600, rotated at 1 MiB |
| `$XDG_RUNTIME_DIR/livingroomos/` | `backend.lock` and `state.json`, mode 0700 (stored in RAM) |
| `/var/lib/livingroomos/.config/systemd/user/livingroomos*.{service,target}` | User units for the dedicated `livingroomos` account; owned by that user |
| `/etc/greetd/config.toml` | Automatic-login configuration, owned by `root` |
| `/etc/polkit-1/rules.d/50-livingroomos-power.rules` | Restricted power actions for `livingroomos`, owned by `root` |
| `/etc/opt/chrome/policies/managed/livingroomos.json` | Google Chrome policies, owned by `root` |

Network: The backend listens **only** on `127.0.0.1:8750`. No inbound port is
exposed to the network. Apps require outbound connections (HTTPS).

## 5. Target architecture

Only `amd64` / x86_64 is supported. The system checker rejects ARM processors.

## 6. Installation sources

Debian system packages come from the official Debian archive through `apt`.
Google Chrome is installed separately as the manufacturer's official 64-bit
`.deb` package. The project does not download scripts from the internet, use
`curl | sh`, or add third-party repositories. The optional pip-based path
(`requirements.txt`) downloads `fastapi` and `uvicorn` from PyPI and is
therefore the second choice.
