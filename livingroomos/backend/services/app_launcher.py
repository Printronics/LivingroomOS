"""Converts app IDs into validated launch commands.

Security model: docs/SECURITY.md. The frontend sends only an app ID. The executable, arguments, and
environment come from administrator-managed configuration files and are validated here several times:
when loading (format, flags, placeholders) and when launching (path, owner, permissions, profile directory).
No shell is used.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .process_manager import (
    ExitInfo,
    LaunchFailed,
    LaunchSpec,
    ProcessManager,
    default_runtime_dir,
    ensure_private_dir,
)
from .settings_store import SettingsStore

log = logging.getLogger("livingroomos.launcher")

APP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_]+)\}")
ALLOWED_PLACEHOLDERS = {"python", "profile_dir"}
MAX_ARG_LEN = 2048

# Environment variables passed through from the backend (everything else is discarded).
ENV_PASSTHROUGH = (
    "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TZ",
    "XDG_RUNTIME_DIR", "XDG_SESSION_TYPE", "XDG_SESSION_ID", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS",
    "WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "PIPEWIRE_RUNTIME_DIR",
)
# The configuration must not set these variables either (library/interpreter injection).
FORBIDDEN_ENV_RE = re.compile(r"^(PATH|HOME|SHELL|IFS|ENV|BASH_ENV|GCONV_PATH|LOCPATH|NLSPATH|LD_.*|PYTHON.*)$")

# Flags that disable browser security mechanisms or enable remote control.
FORBIDDEN_FLAGS = {
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-web-security",
    "--disable-site-isolation-trials", "--allow-running-insecure-content",
    "--ignore-certificate-errors", "--unsafely-treat-insecure-origin-as-secure",
    "--remote-debugging-port", "--remote-debugging-pipe", "--remote-debugging-address",
    "--remote-allow-origins", "--load-extension", "--enable-automation",
}
BROWSER_NAMES = {
    "google-chrome-stable", "google-chrome", "chrome",
    "brave-browser", "firefox", "firefox-esr",
}
DEFAULT_TRUSTED_DIRS = ("/usr/local/bin", "/usr/bin", "/opt")


class AppNotFound(Exception):
    pass


class NotInstalled(Exception):
    def __init__(self, executable: str) -> None:
        super().__init__(executable)
        self.executable = executable


class LaunchRefused(LaunchFailed):
    """Launch rejected for security reasons. The message gives the administrator the reason."""


@dataclass(frozen=True)
class AppDefinition:
    id: str
    title: str
    subtitle: str
    icon: str
    color: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    long_running: bool
    category: str

    @property
    def uses_profile(self) -> bool:
        return any("{profile_dir}" in part for part in self.command)


def _is_browser(command0: str) -> bool:
    return Path(command0).name in BROWSER_NAMES


def _check_args(command: list[str]) -> None:
    """Structural validation of a command line (also applies to the return-to-launcher command)."""
    for part in command:
        if "\0" in part or len(part) > MAX_ARG_LEN:
            raise ValueError("Argument contains NUL or is too long")
        unknown = {m for m in PLACEHOLDER_RE.findall(part) if m not in ALLOWED_PLACEHOLDERS}
        if unknown:
            raise ValueError(f"unbekannter Platzhalter: {{{sorted(unknown)[0]}}}")
        if part.split("=", 1)[0] in FORBIDDEN_FLAGS:
            raise ValueError(f"verbotener Schalter: {part.split('=', 1)[0]}")


def parse_apps(raw_apps: list[Any]) -> tuple[dict[str, AppDefinition], list[str]]:
    """Validates the app list. Invalid entries are skipped and are not fatal."""
    apps: dict[str, AppDefinition] = {}
    problems: list[str] = []
    for index, raw in enumerate(raw_apps):
        try:
            if not isinstance(raw, dict):
                raise ValueError("Entry is not an object")
            app_id = raw.get("id")
            if not isinstance(app_id, str) or not APP_ID_RE.match(app_id):
                raise ValueError("Missing ID or invalid ID format")
            if app_id in apps:
                raise ValueError("id doppelt vergeben")
            title = raw.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("Missing title")
            command = raw.get("command")
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(part, str) and part for part in command)
            ):
                raise ValueError("command must be a non-empty list of strings")
            _check_args(command)

            if _is_browser(command[0]) and not any("{profile_dir}" in part for part in command[1:]):
                raise ValueError("Browsers require a separate profile: {profile_dir} is missing from command")

            env_raw = raw.get("env", {})
            if not isinstance(env_raw, dict):
                raise ValueError("env must be an object")
            env: list[tuple[str, str]] = []
            for key, value in env_raw.items():
                if not ENV_KEY_RE.match(key) or FORBIDDEN_ENV_RE.match(key):
                    raise ValueError(f"Environment variable is not allowed: {key}")
                if not isinstance(value, str) or "\0" in value:
                    raise ValueError(f"Invalid value for {key}")
                env.append((key, value))

            color = raw.get("color", "#3a4256")
            category = raw.get("category", "media")
            if not isinstance(category, str) or category not in {"media", "debug"}:
                category = "media"
            apps[app_id] = AppDefinition(
                id=app_id,
                title=title.strip(),
                subtitle=str(raw.get("subtitle", "")),
                icon=str(raw.get("icon") or title.strip()[0].upper())[:2],
                color=color if isinstance(color, str) and COLOR_RE.match(color) else "#3a4256",
                command=tuple(command),
                env=tuple(env),
                long_running=bool(raw.get("long_running", True)),
                category=category,
            )
        except ValueError as exc:
            problems.append(f"apps[{index}]: {exc}")
            log.warning("Skipped app entry %d: %s", index, exc)
    return apps, problems


class AppLauncher:
    def __init__(self, store: SettingsStore, manager: ProcessManager) -> None:
        self._store = store
        self._manager = manager
        server = store.server
        self._data_dir = Path(str(server.get("data_dir", "~/.local/share/livingroomos"))).expanduser()
        dirs = server.get("trusted_bin_dirs", DEFAULT_TRUSTED_DIRS)
        if not isinstance(dirs, (list, tuple)):
            dirs = DEFAULT_TRUSTED_DIRS
        self._bin_dirs = [d for d in dirs if isinstance(d, str) and os.path.isabs(d)]
        self._trusted_real = [os.path.realpath(d) for d in self._bin_dirs if os.path.isdir(d)]
        self._apps: dict[str, AppDefinition] = {}
        self.problems: list[str] = []
        self._return_problems: list[str] = []
        self._return_cmd = self._parse_return_command(server.get("return_to_launcher_command"))
        self.reload()
        manager.on_exit = self._on_exit

    def reload(self) -> None:
        self._apps, extra = parse_apps(self._store.apps)
        self.problems = [*self._store.app_config_problems, *extra, *self._return_problems]

    async def startup(self) -> None:
        await self._manager.startup()

    async def shutdown(self) -> None:
        await self._manager.shutdown()

    # --------------------------------------------------------------- Abfragen

    def title(self, app_id: str | None) -> str:
        app = self._apps.get(app_id or "")
        return app.title if app else "Application"

    def list_apps(self) -> list[dict[str, Any]]:
        """Public representation: intentionally excludes the command line and paths."""
        return [
            {
                "id": a.id,
                "title": a.title,
                "subtitle": a.subtitle,
                "icon": a.icon,
                "color": a.color,
                "available": self._is_available(a),
                "category": a.category,
            }
            for a in self._apps.values()
        ]

    def status(self) -> dict[str, Any]:
        return self._manager.status()

    def _is_available(self, app: AppDefinition) -> bool:
        try:
            self._resolve_executable(app.command[0])
            return True
        except (NotInstalled, LaunchRefused, OSError):
            return False

    # ---------------------------------------------------------------- Aktionen

    async def launch(self, app_id: str) -> dict[str, Any]:
        app = self._apps.get(app_id)
        if app is None:
            raise AppNotFound(app_id)
        current = self._manager.status()
        if current["state"] in ("starting", "running") and current["app_id"] == app_id:
            return current  # idempotent: the same app is already running
        try:
            spec = self._prepare(app)
        except LaunchRefused as exc:
            log.warning("Launch of %s rejected: %s", app_id, exc)
            raise
        except OSError as exc:
            log.error("Launch of %s: filesystem error: %s", app_id, exc)
            raise LaunchFailed("Cannot launch: filesystem error.") from exc
        await self._manager.start(spec)  # ProcessBusy → API
        return self._manager.status()

    async def stop(self, app_id: str | None = None) -> dict[str, Any]:
        """Stops the active app. If app_id is provided, it stops the app only when that exact app is active."""
        current = self._manager.status()
        if app_id is not None and current["app_id"] != app_id:
            return current
        await self._manager.stop()
        return self._manager.status()

    # ------------------------------------------------------------------ Vorbereitung

    def _prepare(self, app: AppDefinition) -> LaunchSpec:
        exe = self._resolve_executable(app.command[0])
        ensure_private_dir(self._data_dir)
        profile_dir: Path | None = None
        if app.uses_profile:
            ensure_private_dir(self._data_dir / "profiles")
            profile_dir = ensure_private_dir(self._data_dir / "profiles" / app.id)
        log_path = ensure_private_dir(self._data_dir / "logs") / f"{app.id}.log"

        argv = [str(exe)]
        identity: str | None = None
        for part in app.command[1:]:
            expanded = part.replace("{python}", sys.executable)
            if profile_dir is not None:
                expanded = expanded.replace("{profile_dir}", str(profile_dir))
            argv.append(expanded)
            if identity is None and profile_dir is not None and str(profile_dir) in expanded:
                identity = expanded  # exakter Eintrag, z. B. --user-data-dir=/…/profiles/<app-id>
        return LaunchSpec(
            app_id=app.id,
            argv=tuple(argv),
            env=self._build_env(app),
            log_path=log_path,
            identity_arg=identity,
            long_running=app.long_running,
        )

    def _build_env(self, app: AppDefinition | None = None) -> dict[str, str]:
        env = {key: os.environ[key] for key in ENV_PASSTHROUGH if key in os.environ}
        env["PATH"] = ":".join(self._bin_dirs) or "/usr/bin:/bin"
        if app is not None:
            env.update(dict(app.env))

        # Chrome/Chromium starts a separate process, including Crashpad, for each app.
        # Eine isolierte, beschreibbare XDG-Umgebung verhindert, dass Kindprozesse
        # fall back to missing or foreign user paths. The paths
        # are stored centrally under data_dir and are independent of the backend launch context.
        config_home = ensure_private_dir(self._data_dir / "chrome-config")
        cache_home = ensure_private_dir(self._data_dir / "chrome-cache")
        env["XDG_CONFIG_HOME"] = str(config_home)
        env["XDG_CACHE_HOME"] = str(cache_home)
        return env

    def _resolve_executable(self, name: str) -> Path:
        """Returns the validated real path or raises NotInstalled or LaunchRefused."""
        is_python = name == "{python}"
        if is_python:
            candidate = Path(sys.executable)
        elif os.path.isabs(name):
            candidate = Path(name)
        elif "/" in name:
            raise LaunchRefused("Relative executable paths are not allowed.")
        else:  # search trusted directories only, never the user's PATH
            found = next(
                (Path(d) / name for d in self._bin_dirs if os.path.isfile(Path(d) / name) and os.access(Path(d) / name, os.X_OK)),
                None,
            )
            if found is None:
                raise NotInstalled(name)
            candidate = found

        real = Path(os.path.realpath(candidate))
        if not real.is_file() or not os.access(real, os.X_OK):
            raise NotInstalled(name)
        if not is_python and not any(real.is_relative_to(d) for d in self._trusted_real):
            raise LaunchRefused(f"{real} is not inside a trusted directory.")
        self._check_permissions(real)
        return real

    @staticmethod
    def _check_permissions(real: Path) -> None:
        uid = os.getuid()
        st = real.stat()
        if st.st_uid not in (0, uid):
            raise LaunchRefused(f"{real} is owned by a different user.")
        if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise LaunchRefused(f"{real} is writable by group or others.")
        parent = real.parent
        while True:
            parent_stat = parent.stat()
            if parent_stat.st_uid not in (0, uid):
                raise LaunchRefused(f"Directory {parent} is owned by a different user.")
            if parent_stat.st_mode & stat.S_IWGRP:
                raise LaunchRefused(f"Directory {parent} is group-writable.")
            if parent_stat.st_mode & stat.S_IWOTH and not parent_stat.st_mode & stat.S_ISVTX:
                raise LaunchRefused(f"Directory {parent} is writable by others.")
            if parent.parent == parent:
                break
            parent = parent.parent

    # ----------------------------------------------------- Return to launcher

    def _parse_return_command(self, raw: Any) -> list[str] | None:
        if raw in (None, [], ""):
            return None
        try:
            if not isinstance(raw, list) or not all(isinstance(p, str) and p for p in raw):
                raise ValueError("must be a list of strings")
            _check_args(raw)
            if any(PLACEHOLDER_RE.search(p) for p in raw):
                raise ValueError("Placeholders are not allowed here")
        except ValueError as exc:
            self._return_problems.append(f"server.return_to_launcher_command: {exc}")
            log.warning("return_to_launcher_command ignoriert: %s", exc)
            return None
        return list(raw)

    async def _on_exit(self, info: ExitInfo) -> None:
        """After each app exits: optionally return focus to the launcher (for example, using wlrctl)."""
        if not self._return_cmd:
            return
        try:
            exe = self._resolve_executable(self._return_cmd[0])
            proc = await asyncio.create_subprocess_exec(
                str(exe), *self._return_cmd[1:],
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=self._build_env(),
                start_new_session=True,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                log.warning("Return-to-launcher command timed out and was terminated")
        except (NotInstalled, LaunchRefused, OSError) as exc:
            log.warning("Cannot return focus to the launcher: %s", exc)
