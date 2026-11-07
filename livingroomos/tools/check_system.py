#!/usr/bin/env python3
"""Checks whether this system can run LivingroomOS on x86_64.

Standard library only; does not modify the system or download anything.

    python3 tools/check_system.py            # check everything
    python3 tools/check_system.py --config ~/.config/livingroomos/settings.json

Exit code 0: all required checks passed; 1: at least one required check failed.
Optional notices do not affect the exit code.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import re
import shutil
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_MACHINES = {"x86_64": "Intel/AMD 64 Bit"}
MIN_PYTHON = (3, 11)
MIN_KERNEL = (5, 3)

results: list[tuple[str, str, str]] = []  # (status, check, detail); status: OK | MISSING | INFO


def record(ok: bool, name: str, detail: str = "", required: bool = True) -> None:
    results.append(("OK" if ok else ("MISSING" if required else "INFO"), name, detail))


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
    # Same directories as trusted_bin_dirs in the backend, not the user's PATH.
    for directory in ("/usr/local/bin", "/usr/bin", "/usr/sbin", "/opt"):
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def check(config_path: Path) -> None:
    machine = platform.machine()
    record(machine in SUPPORTED_MACHINES, "Architecture", f"{machine} ({SUPPORTED_MACHINES.get(machine, 'not tested')})")
    record(platform.system() == "Linux", "Operating system", platform.system())
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
    record(hasattr(os, "pidfd_open"), "os.pidfd_open available")
    record(hasattr(signal, "pidfd_send_signal"), "signal.pidfd_send_signal available")
    record(Path("/proc/self/stat").exists(), "/proc mounted")
    try:
        import fcntl  # noqa: F401

        record(True, "fcntl.flock available")
    except ImportError:
        record(False, "fcntl.flock available")

    for module, package in (("fastapi", "python3-fastapi"), ("uvicorn", "python3-uvicorn")):
        found = importlib.util.find_spec(module) is not None
        record(found, f"Python-Modul {module}", "" if found else f"installieren: apt install {package}")
    record(importlib.util.find_spec("httpx") is not None, "Python module httpx (API tests only)", "apt install python3-httpx", required=False)

    for binary, package, required in (
        ("google-chrome-stable", "Google Chrome (.deb)", True),
        ("labwc", "labwc", True),
        ("greetd", "greetd", True),
        ("wlrctl", "wlrctl", False),
        ("wlr-randr", "wlr-randr", False),
    ):
        path = find_binary(binary) or shutil.which(binary)
        record(path is not None, f"Executable {binary}", path or f"apt install {package}", required=required)

    record(Path("/run/systemd/system").exists(), "systemd is running")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    record(bool(runtime), "XDG_RUNTIME_DIR is set", runtime or "only available inside a login session", required=False)
    record(bool(os.environ.get("WAYLAND_DISPLAY")), "WAYLAND_DISPLAY is set", os.environ.get("WAYLAND_DISPLAY", "only available inside the labwc session"), required=False)
    record(os.getuid() != 0, "not running as root", "LivingroomOS should run as the livingroomos user", required=False)

    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from services.app_launcher import AppLauncher  # noqa: PLC0415
        from services.process_manager import ProcessManager  # noqa: PLC0415
        from services.settings_store import SettingsError, SettingsStore  # noqa: PLC0415

        store = SettingsStore(config_path)
        launcher = AppLauncher(store, ProcessManager())
        record(not launcher.problems, "Configuration is valid", "; ".join(launcher.problems) or str(config_path))
        for app in launcher.list_apps():
            record(app["available"], f"App “{app['title']}” ready to launch", "" if app["available"] else "Executable is not installed", required=False)
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
    failed = [name for status, name, _ in results if status == "MISSING"]
    print(f"\n{'All required checks passed.' if not failed else f'{len(failed)} required check(s) failed.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
