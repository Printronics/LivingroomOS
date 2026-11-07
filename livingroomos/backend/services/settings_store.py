"""Lädt und speichert config/settings.json sowie einzelne App-CFG-Dateien.

Nur der Abschnitt "ui" ist über die API schreibbar. "server" und die
App-Konfigurationen ändert ausschließlich der Administrator per Dateibearbeitung.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .app_config_loader import load_app_configs


class SettingsError(Exception):
    """Konfiguration fehlt, ist ungültig oder nicht schreibbar."""


class SettingsStore:
    def __init__(self, path: Path, app_config_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.app_config_dir = Path(app_config_dir) if app_config_dir is not None else self.path.parent / "apps"
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._app_config_problems: list[str] = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SettingsError(f"Konfigurationsdatei fehlt: {self.path}") from exc
        except json.JSONDecodeError as exc:
            raise SettingsError(
                f"{self.path.name} ist kein gültiges JSON (Zeile {exc.lineno}): {exc.msg}"
            ) from exc
        except OSError as exc:
            raise SettingsError(f"{self.path} nicht lesbar: {exc.strerror}") from exc
        if not isinstance(raw, dict):
            raise SettingsError(f"{self.path.name}: Oberste Ebene muss ein Objekt sein.")
        with self._lock:
            self._data = raw

    @property
    def server(self) -> dict[str, Any]:
        section = self._data.get("server")
        return section if isinstance(section, dict) else {}

    @property
    def ui(self) -> dict[str, Any]:
        section = self._data.get("ui")
        return section if isinstance(section, dict) else {}

    @property
    def apps(self) -> list[Any]:
        """CFG-Web-Apps plus optionale Legacy-/Debug-Einträge aus settings.json."""
        configured, self._app_config_problems = load_app_configs(self.app_config_dir)
        legacy = self._data.get("apps")
        if not isinstance(legacy, list):
            legacy = []
        return [*configured, *legacy]

    @property
    def app_config_problems(self) -> list[str]:
        return list(self._app_config_problems)

    def update_ui(self, values: dict[str, Any]) -> dict[str, Any]:
        """Aktualisiert den Abschnitt "ui" und schreibt die Datei atomar."""
        with self._lock:
            new_data = {**self._data, "ui": {**self.ui, **values}}
            self._write_atomic(new_data)
            self._data = new_data
            return dict(new_data["ui"])

    def _write_atomic(self, data: dict[str, Any]) -> None:
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".settings-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_name, self.path)
        except OSError as exc:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise SettingsError(f"Einstellungen nicht speicherbar: {exc.strerror}") from exc
