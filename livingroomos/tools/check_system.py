#!/usr/bin/env python3
"""Prüft, ob dieses System LivingroomOS auf x86_64 tragen kann.

Nur Standardbibliothek, ändert nichts am System, lädt nichts aus dem Netz.

    python3 tools/check_system.py            # prüft alles
    python3 tools/check_system.py --config ~/.config/livingroomos/settings.json

Exit-Code 0: alle Pflichtprüfungen bestanden; 1: mindestens eine Pflichtprüfung fehlgeschlagen.
Hinweise (optional) beeinflussen den Exit-Code nicht.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_MACHINES = {"x86_64": "Intel/AMD 64 Bit"}
MIN_PYTHON = (3, 11)
MIN_KERNEL = (5, 3)

results: list[tuple[str, str, str]] = []  # (Status, Prüfung, Detail); Status: OK | FEHLT | HINWEIS


def record(ok: bool, name: str, detail: str = "", required: bool = True) -> None:
    results.append(("OK" if ok else ("FEHLT" if required else "HINWEIS"), name, detail))


def kernel_version() -> tuple[int, int]:
    match = re.match(r"(\d+)\.(\d+)", platform.release())
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


def is_supported_os(release: dict[str, str]) -> bool:
    """LivingroomOS currently supports Debian 13 Trixie only."""
    return (
        release.get("ID", "").lower() == "debian"
        and release.get("VERSION_ID", "") == "13"
        and release.get("VERSION_CODENAME", "").lower() == "trixie"
    )


def find_binary(name: str) -> str | None:
    # Gleiche Verzeichnisse wie trusted_bin_dirs im Backend, nicht der PATH des Benutzers.
    for directory in ("/usr/local/bin", "/usr/bin", "/usr/sbin", "/opt"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def check(config_path: Path) -> None:
    machine = platform.machine()
    record(machine in SUPPORTED_MACHINES, "Architektur", f"{machine} ({SUPPORTED_MACHINES.get(machine, 'nicht getestet')})")
    record(platform.system() == "Linux", "Betriebssystem", platform.system())
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        os_release = {}
    release_label = " ".join(
        value for value in (
            os_release.get("ID", ""),
            os_release.get("VERSION_ID", ""),
            os_release.get("VERSION_CODENAME", ""),
        ) if value
    ) or "unbekannt"
    record(is_supported_os(os_release), "Debian 13 (Trixie)", release_label)
    record(sys.version_info >= MIN_PYTHON, "Python ≥ 3.11", platform.python_version())
    kernel = kernel_version()
    record(kernel >= MIN_KERNEL, "Linux-Kernel ≥ 5.3 (pidfd)", platform.release())
    record(hasattr(os, "pidfd_open"), "os.pidfd_open verfügbar")
    record(Path("/proc/self/stat").exists(), "/proc eingehängt")
    try:
        import fcntl  # noqa: F401

        record(True, "fcntl.flock verfügbar")
    except ImportError:
        record(False, "fcntl.flock verfügbar")

    for module, package in (("fastapi", "python3-fastapi"), ("uvicorn", "python3-uvicorn")):
        found = importlib.util.find_spec(module) is not None
        record(found, f"Python-Modul {module}", "" if found else f"installieren: apt install {package}")
    record(importlib.util.find_spec("httpx") is not None, "Python-Modul httpx (nur für API-Tests)", "apt install python3-httpx", required=False)

    for binary, package, required in (
        ("google-chrome-stable", "Google Chrome (.deb)", True),
        ("labwc", "labwc", True),
        ("greetd", "greetd", True),
        ("wlrctl", "wlrctl", False),
        ("wlr-randr", "wlr-randr", False),
    ):
        path = find_binary(binary) or shutil.which(binary)
        record(path is not None, f"Programm {binary}", path or f"apt install {package}", required=required)

    record(Path("/run/systemd/system").exists(), "systemd läuft", required=False)
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    record(bool(runtime), "XDG_RUNTIME_DIR gesetzt", runtime or "nur in einer Anmeldesitzung vorhanden", required=False)
    record(bool(os.environ.get("WAYLAND_DISPLAY")), "WAYLAND_DISPLAY gesetzt", os.environ.get("WAYLAND_DISPLAY", "nur in der labwc-Sitzung vorhanden"), required=False)
    record(os.getuid() != 0, "läuft nicht als root", "LivingroomOS gehört unter den Benutzer livingroomos", required=False)

    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from services.app_launcher import AppLauncher  # noqa: PLC0415
        from services.process_manager import ProcessManager  # noqa: PLC0415
        from services.settings_store import SettingsError, SettingsStore  # noqa: PLC0415

        store = SettingsStore(config_path)
        launcher = AppLauncher(store, ProcessManager())
        record(not launcher.problems, "Konfiguration gültig", "; ".join(launcher.problems) or str(config_path))
        for app in launcher.list_apps():
            record(app["available"], f"App „{app['title']}“ startbereit", "" if app["available"] else "Programm nicht installiert", required=False)
    except SettingsError as exc:
        record(False, "Konfiguration lesbar", str(exc))
    except ImportError as exc:
        record(False, "Backend importierbar", str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("LIVINGROOMOS_CONFIG", ROOT / "backend" / "config" / "settings.json")))
    args = parser.parse_args()
    check(args.config)
    width = max(len(name) for _, name, _ in results)
    for status, name, detail in results:
        print(f"{status:<7} {name:<{width}}  {detail}".rstrip())
    failed = [name for status, name, _ in results if status == "FEHLT"]
    print(f"\n{'Alle Pflichtprüfungen bestanden.' if not failed else f'{len(failed)} Pflichtprüfung(en) fehlgeschlagen.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
