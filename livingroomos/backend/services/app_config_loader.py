"""Loads individual app definitions from config/apps/*.cfg.

These files describe web apps only. Launch commands are generated here from
festgelegten Browser-Optionen erzeugt; Konfigurationsdateien enthalten keine
arbitrary shell commands.
"""
from __future__ import annotations

import configparser
import re
from pathlib import Path
from urllib.parse import urlsplit

APP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
BROWSER_NAMES = {"google-chrome-stable", "google-chrome", "chrome"}


def load_app_configs(directory: Path) -> tuple[list[dict], list[str]]:
    """Loads all CFG files in deterministic order; invalid files are skipped."""
    apps: list[dict] = []
    problems: list[str] = []
    directory = Path(directory)
    if not directory.exists():
        return apps, problems
    if not directory.is_dir():
        return apps, [f"App configuration path is not a directory: {directory}"]

    for path in sorted(directory.glob("*.cfg"), key=lambda item: item.name.casefold()):
        try:
            parser = configparser.ConfigParser(interpolation=None, strict=True)
            with path.open("r", encoding="utf-8") as stream:
                parser.read_file(stream)
            if not parser.has_section("app") or not parser.has_section("browser"):
                raise ValueError("Sections [app] and [browser] are required")

            app = parser["app"]
            browser = parser["browser"]
            app_id = app.get("id", "").strip()
            if not APP_ID_RE.fullmatch(app_id):
                raise ValueError("Missing ID or invalid ID format")
            if path.stem != app_id:
                raise ValueError("Filename must match the app ID exactly (for example, netflix.cfg)")
            title = app.get("title", "").strip()
            if not title:
                raise ValueError("Missing title")
            url = browser.get("url", "").strip()
            parsed = urlsplit(url)
            if (
                len(url) > 2048
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError("url must be a valid HTTP or HTTPS URL without credentials")

            executable = browser.get("executable", "google-chrome-stable").strip()
            if executable not in BROWSER_NAMES:
                raise ValueError("executable is not an approved supported browser")
            fullscreen = browser.getboolean("fullscreen", fallback=True)
            wayland = browser.getboolean("wayland", fallback=True)

            command = [
                executable,
                f"--app={url}",
                "--user-data-dir={profile_dir}",
            ]
            if wayland:
                command.append("--ozone-platform=wayland")
            if fullscreen:
                command.append("--start-fullscreen")

            color = app.get("color", "#3a4256").strip()
            if not COLOR_RE.fullmatch(color):
                raise ValueError("color must use the #RRGGBB format")
            category = app.get("category", "media").strip()
            if category not in {"media", "debug"}:
                raise ValueError("category must be media or debug")

            apps.append({
                "id": app_id,
                "title": title,
                "subtitle": app.get("subtitle", "").strip(),
                "icon": app.get("icon", title[0].upper()).strip()[:2] or title[0].upper(),
                "color": color,
                "command": command,
                "category": category,
                "long_running": browser.getboolean("long_running", fallback=True),
            })
        except (OSError, UnicodeError, configparser.Error, ValueError) as exc:
            message = f"{path.name}: {exc}"
            problems.append(message)
    return apps, problems
