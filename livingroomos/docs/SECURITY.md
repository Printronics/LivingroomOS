# LivingroomOS – Process Management Security

**Status:** 2026-11-07  
**Scope:** `backend/services/app_config_loader.py`,
`backend/services/settings_store.py`, `backend/services/app_launcher.py`,
and `backend/services/process_manager.py`.

The user guide for CFG files is available in
[App Configuration](APP_CONFIGURATION.md). This document describes security
boundaries and permissions, not the complete user workflow.

## 1. Security objectives

| ID | Objective |
| --- | --- |
| S1 | The backend starts only apps that the administrator has explicitly defined in `config/apps/*.cfg` or as legacy/debug entries in `config/settings.json`. |
| S2 | Neither the frontend, the network, nor a website can inject a command or argument. |
| S3 | The backend stops only processes it started itself (or can reliably identify after a crash). Other browser windows, including the user's own Google Chrome windows, remain untouched. |
| S4 | Each app receives its own browser profile and process group, as well as a filtered launch environment. This provides process and profile separation, but not complete security isolation: the backend and apps run under the same UID. |
| S5 | Failures (crashes, hangs, or backend restarts) always return the system to a defined state and the launcher. |
| S6 | Errors are logged in a traceable way without exposing secrets in the interface. |

## 2. Assumptions and threat model

**Trust boundaries**

```
Website inside an app ──╳──►  127.0.0.1:8750 (Backend)      Host validation, X-LivingroomOS header, no CORS
Launcher frontend ─────────►  Backend                       sends app IDs only
Backend (user livingroomos) ─► App process (same user)       same permissions: only partial isolation
settings.json and config/apps/*.cfg ◄── Administrator        trusted; CFG directory root-owned, service account read-only
```

**Threats this design is intended to prevent**

- External websites or scripts attempting to access the local API (CSRF, DNS rebinding).
- Manipulated API input (command injection, path or argument manipulation).
- Accidentally insecure configuration (for example, `--no-sandbox`, a shared browser profile, or writable executables).
- Invalid or manipulated app CFG entries: filenames/IDs, URLs, browser executables, colors, and categories are validated; arbitrary shell commands are not supported by the CFG format.
- Incorrectly terminating unrelated processes because of PID reuse or overly broad process searches.
- Orphaned processes after crashes or duplicate starts.

**Threats this design does not prevent (residual risks; see Section 7)**

- Code already running as the `livingroomos` user (for example, after a browser exploit escapes the Google Chrome sandbox).
- Attackers with physical access or root privileges.
- An administrator deliberately entering dangerous values in `settings.json` or an app CFG file (validation catches common mistakes, not malicious administrator input).

## 3. Security measures

| Requirement | Measure | Location |
| --- | --- | --- |
| Predefined executables and arguments only | `app_config_loader.py` reads individual `config/apps/*.cfg` files. It validates required fields, filename-to-ID matching, HTTP(S) URLs without credentials, approved browsers, colors, and categories. The loader constructs the Chrome argument list itself; CFG files cannot define arbitrary commands. Optional legacy/debug entries may remain in `settings.json`. The API accepts only an app ID matching `^[a-z0-9][a-z0-9_-]{0,31}$`. The command line never leaves the backend. | `app_config_loader.py`, `settings_store.py`, `app_launcher.parse_apps`, `api/apps.py` |
| No shell | `asyncio.create_subprocess_exec` with an argument list; never `shell=True`. Only the `{python}` and `{profile_dir}` placeholders are allowed. Any other `{word}` inside an argument and NUL characters are rejected during loading. This is intentionally strict: arguments containing braces (for example, JSON) are not supported. | `process_manager.start`, `parse_apps` |
| Protected executable paths | Bare names are resolved only in `trusted_bin_dirs`, not in the user's `$PATH`. Relative paths are forbidden. The resolved path (`realpath`) must be inside a trusted directory. The file must be owned by root or the service user and must not be group- or world-writable; its parent directory must not be world-writable. | `AppLauncher._resolve_executable` |
| Dangerous flags | A list of prohibited flags (`--no-sandbox`, `--remote-debugging-*`, `--disable-web-security`, `--load-extension`, `--ignore-certificate-errors`, and others) is rejected during loading. | `FORBIDDEN_FLAGS` |
| Separate browser profiles | Browsers in the Google Chrome family and Firefox must receive a `{profile_dir}` argument; otherwise, the app is rejected. Profile path: `~/.local/share/livingroomos/profiles/<id>`, mode 0700. Symlinks and foreign ownership are rejected. | `parse_apps`, `ensure_private_dir` |
| Filtered environment | Apps start with a minimal environment: a fixed set of variables (`HOME`, `XDG_RUNTIME_DIR`, `WAYLAND_DISPLAY`, etc.) plus a trusted `PATH`. Additional app variables are allowed only if they match an approved pattern. `LD_*`, `PYTHON*`, `PATH`, `HOME`, and others are prohibited. | `AppLauncher._build_env` |
| Process IDs and status | Status includes the PID, state, and last exit. The runtime state file (mode 0600) contains the PID, process group, and start time from `/proc`. | `ProcessManager.status`, `_write_state` |
| Duplicate starts | State is reserved before the first `await`; a lock file (`flock`) prevents a second backend instance. Leftover processes using the same profile are stopped before launch. | `start`, `startup` |
| Crash detection | A watcher waits for process exit. Classification: `stopped`, `ok`, `crashed` (after the grace period), and `start_failed` (exit during the grace period, including exit code 0—typically when handing off to an already-running browser instance). The signal name is recorded when termination is caused by a signal. | `_finalize` |
| Targeted termination | Only the app's own process group is terminated (separate session via `start_new_session`). Send SIGTERM first, then SIGKILL after the timeout. `POST /apps/{id}/stop` stops the app only if that exact app is active. | `stop`, `_signal_tree` |
| Do not touch unrelated browser windows | Straggler processes (such as renderers that left the process group) are found using the **exact** argv entry `--user-data-dir=<this app's profile>`, never by executable name. Only the service UID is considered; signals are sent using `pidfd` (preventing PID reuse), and the command line is checked again immediately before signaling. | `_find_pids_with_arg`, `_signal_verified` |
| Error logging | Lifecycle events use `logging` (journald under systemd). App output is written to `~/.local/share/livingroomos/logs/<id>.log` (0600, rotated at 1 MiB). After a crash, the last lines are available in the log, not in the API. Security rejections are logged as WARNING with a reason. | `_open_log`, `_finalize`, `AppLauncher.launch` |
| Return to launcher | After every app exits, state changes to `idle`; the frontend displays the launcher again. An optional, fixed command (`return_to_launcher_command`, for example `wlrctl`) can restore focus, also without a shell and with a timeout. | `AppLauncher._on_exit` |
| Backend crash recovery | On startup, the backend reads the state file, verifies both the PID **and** process start time, and adopts a still-running app (state `running`). If the process is gone, leftovers are stopped using the profile identifier. | `_recover` |

## 4. Permissions

**Users and groups**

| Item | Requirement |
| --- | --- |
| Service user | Dedicated `livingroomos` account; **not** root, **no** sudo, and no capabilities. |
| Groups | Normally no additional groups: logind grants GPU and audio access per session (`uaccess`). Add `video`, `render`, or `audio` only if a test requires it. |
| Session | Start inside the greetd/logind session so that `XDG_RUNTIME_DIR` (`/run/user/<uid>`) and the Wayland socket exist. |

**Filesystem**

| Path | Access | Mode |
| --- | --- | --- |
| `/opt/livingroomos/backend/config/settings.json` | Read-only template; changes are not saved at runtime | root:root, 0644 |
| `/var/lib/livingroomos/.config/livingroomos/settings.json` | Read/write; the API may modify only the `ui` section | livingroomos:livingroomos, 0600 |
| `/opt/livingroomos/backend/config/apps/*.cfg` | Read-only; app definitions are maintained by the administrator; the service user has no write access | root:root, 0644 |
| `~/.local/share/livingroomos/profiles/<id>/` | Read/write | 0700 |
| `~/.local/share/livingroomos/logs/` | Write | 0700; files 0600 |
| `$XDG_RUNTIME_DIR/livingroomos/` (`backend.lock`, `state.json`) | Read/write | 0700; files 0600 |
| `/usr/bin`, `/usr/local/bin`, `/opt` (`trusted_bin_dirs`) | Read/execute only | Must be owned by root |
| `/proc/<pid>/{stat,cmdline}` | Read (own UID) | `hidepid` does not prevent access to the user's own processes |

**Signals:** The backend may signal only processes belonging to its own UID. Processes owned by other UIDs are never considered.

## 5. System dependencies

| Dependency | Purpose | Notes |
| --- | --- | --- |
| Linux kernel ≥ 5.3 | `pidfd_open`, `pidfd_send_signal`; Debian 13 provides 6.12 | Required by the supported x86_64 platform |
| Python ≥ 3.11 | Unified `TimeoutError`, `umask` parameter, `Path.is_relative_to` | Debian 13: 3.13 |
| `/proc` | Process start time and command line for identity checks | Linux-specific; not portable to other operating systems |
| `fcntl.flock` | Backend lock | Python standard library |
| External Python packages | Only `fastapi` and `uvicorn` (already required); process management itself uses **only the standard library** | |
| App executables | For example, Debian package `google-chrome-stable` for streaming websites and media libraries | Streaming providers require Widevine, which is not included in Debian's Google Chrome package |
| Optional | `wlrctl` to "return focus to launcher" | Check availability on Debian 13 before use; without it, closing the app window is sufficient |

## 6. Recommended systemd hardening (untested; verify before use)

The backend user unit can apply additional restrictions to itself. **Warning:** child processes inherit these restrictions, and Google Chrome needs user namespaces, networking (including `AF_NETLINK`), and GPU access. Enable each option individually and test Google Chrome.

```ini
[Service]
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=%h/.local/share/livingroomos %t/livingroomos %h/.config/livingroomos
ProtectKernelModules=yes
ProtectControlGroups=yes
LockPersonality=yes
# Do NOT enable these before testing Google Chrome:
# PrivateDevices, RestrictNamespaces, SystemCallFilter, RestrictAddressFamilies, MemoryDenyWriteExecute
```

The next clean step would be to start apps as **transient systemd user units**
(`systemd-run --user`): each app would have its own cgroup, `MemoryMax`, full
termination of child processes without searching `/proc`, and per-app
hardening independent of the backend. The `LaunchSpec` interface can remain
unchanged; only `ProcessManager` would need to be replaced.

## 7. Residual risks

| Risk | Severity | Mitigation / plan |
| --- | --- | --- |
| Apps and the backend run under the same UID. A compromised app could read backend files or terminate the backend. | Medium | Keep the Google Chrome sandbox enabled (never use `--no-sandbox`); later, use systemd units per app and possibly a separate UID per app. |
| Google Chrome processes that are neither in the process group nor carry the profile argument are not detected. | Low | The straggler search covers renderer/GPU/utility processes because Google Chrome inherits the argument. Cgroups (Section 6) would provide complete tracking. |
| An adopted app (after a backend crash) has an unknown exit code; a crash cannot be distinguished from a normal exit (reason `ended`). | Low | Acceptable; record a note in the log. |
| Returning window focus to the launcher depends on the compositor. | Low | Without `wlrctl`, the app window closes and the launcher underneath becomes visible. |
| Invalid app configuration in `settings.json` or a `.cfg` file. | Low | Validated during loading; invalid entries/files are skipped and reported as `config_problems` at `/api/v1/system/status`. Valid CFG files remain available. |
| Race between checking a straggler process and sending a signal. | Very low | `pidfd` pins the process; the command line is checked again immediately before signaling; only the service UID is considered. |

## 8. Pre-deployment checklist

- [ ] `settings.json` is owned by root (or `livingroomos`) and is not writable by others.
- [ ] App CFG files under `/opt/livingroomos/backend/config/apps/` are root-owned and not writable by the service user.
- [ ] All executables are located in `trusted_bin_dirs` and owned by root.
- [ ] Every browser app has `--user-data-dir={profile_dir}`; no prohibited flags are present.
- [ ] The backend runs as `livingroomos`, not as root.
- [ ] `GET /api/v1/system/status` reports `config_problems: []`.
- [ ] Test: start an app, run `kill -9` against it, verify that the launcher reappears and the crash notification is shown exactly once.
- [ ] Test: keep a separate Google Chrome window open; selecting "Stop app" must leave it untouched.
- [ ] Test: terminate the backend with `kill -9` and restart it; verify that the running app is adopted.

## 9. Restart and shutdown

The interface can request only `POST /api/v1/system/power/restart` or
`POST /api/v1/system/power/shutdown`. The backend maps these two values to
fixed argument lists (`systemctl reboot` and `systemctl poweroff`,
respectively). There is no free-form command, argument, or shell input.
Other action names are rejected with HTTP 404.

**Authorization boundary:** The repository includes
`system/polkit/50-livingroomos-power.rules`. This rule grants the
`livingroomos` user and `root` the permissions
`org.freedesktop.login1.reboot`,
`org.freedesktop.login1.reboot-multiple-sessions`,
`org.freedesktop.login1.power-off`, and
`org.freedesktop.login1.power-off-multiple-sessions`. All other
unprivileged users and other actions are not authorized by this rule and
remain subject to the system-wide Polkit policy.

During installation, the rule must be copied as a root-owned file to
`/etc/polkit-1/rules.d/50-livingroomos-power.rules`. It does not grant
general administrator privileges. However, because the backend and launched
applications use the same UID, any process executing code as `livingroomos`
can request a restart or shutdown. The service account must therefore remain
dedicated. This authorization boundary must be tested on Debian 13.
