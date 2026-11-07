"""Tests for SettingsStore: loading, error messages, atomic and concurrent writes.

Run from backend/: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from services.settings_store import SettingsError, SettingsStore  # noqa: E402

SAMPLE = {
    "server": {"data_dir": "/tmp/x", "stop_timeout_s": 5.0},
    "ui": {"clock_24h": True, "tile_size": "normal"},
    "apps": [{"id": "demo", "title": "Demö", "command": ["{python}", "-c", "pass"]}],
}


class SettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "settings.json"
        self.path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_loads_all_sections(self) -> None:
        store = SettingsStore(self.path)
        self.assertEqual(store.server["stop_timeout_s"], 5.0)
        self.assertEqual(store.ui["tile_size"], "normal")
        self.assertEqual(store.apps[0]["id"], "demo")

    def test_cfg_apps_are_loaded_alongside_legacy_entries(self) -> None:
        app_dir = self.dir / "apps"
        app_dir.mkdir()
        (app_dir / "netflix.cfg").write_text(
            "[app]\nid = netflix\ntitle = Netflix\n"
            "[browser]\nurl = https://www.netflix.com/\n",
            encoding="utf-8",
        )
        store = SettingsStore(self.path, app_config_dir=app_dir)
        self.assertEqual([app["id"] for app in store.apps], ["netflix", "demo"])
        self.assertEqual(store.app_config_problems, [])

    def test_missing_file_is_a_clear_error(self) -> None:
        with self.assertRaises(SettingsError) as ctx:
            SettingsStore(self.dir / "gibt-es-nicht.json")
        self.assertIn("missing", str(ctx.exception))

    def test_invalid_json_reports_line(self) -> None:
        self.path.write_text('{\n  "ui": {\n    "a": }\n}\n', encoding="utf-8")
        with self.assertRaises(SettingsError) as ctx:
            SettingsStore(self.path)
        self.assertIn("Zeile 3", str(ctx.exception))

    def test_top_level_must_be_object(self) -> None:
        self.path.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(SettingsError):
            SettingsStore(self.path)

    def test_wrong_section_types_fall_back_to_empty(self) -> None:
        self.path.write_text(json.dumps({"server": [], "ui": "x", "apps": {}}), encoding="utf-8")
        store = SettingsStore(self.path)
        self.assertEqual((store.server, store.ui, store.apps), ({}, {}, []))

    def test_update_merges_ui_and_keeps_other_sections(self) -> None:
        store = SettingsStore(self.path)
        result = store.update_ui({"tile_size": "large", "show_clock": False})
        self.assertEqual(result, {"clock_24h": True, "tile_size": "large", "show_clock": False})
        on_disk = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["apps"], SAMPLE["apps"])
        self.assertEqual(on_disk["server"], SAMPLE["server"])
        self.assertEqual(on_disk["ui"]["tile_size"], "large")
        self.assertTrue(self.path.read_text(encoding="utf-8").endswith("\n"))
        self.assertIn("Demö", self.path.read_text(encoding="utf-8"))  # no Unicode escape for ö

    def test_failed_write_keeps_file_and_memory_and_leaves_no_temp_file(self) -> None:
        store = SettingsStore(self.path)
        before = self.path.read_bytes()
        with mock.patch("services.settings_store.os.replace", side_effect=OSError(5, "Input/output error")):
            with self.assertRaises(SettingsError):
                store.update_ui({"tile_size": "large"})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(store.ui["tile_size"], "normal")
        self.assertEqual([p.name for p in self.dir.iterdir()], ["settings.json"])

    def test_concurrent_updates_do_not_lose_values_or_corrupt_file(self) -> None:
        store = SettingsStore(self.path)
        threads = [threading.Thread(target=store.update_ui, args=({f"k{i}": i},)) for i in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        on_disk = json.loads(self.path.read_text(encoding="utf-8"))["ui"]
        self.assertEqual({k: v for k, v in on_disk.items() if k.startswith("k")}, {f"k{i}": i for i in range(24)})
        self.assertEqual([p.name for p in self.dir.iterdir()], ["settings.json"])

    def test_reload_picks_up_manual_edits(self) -> None:
        store = SettingsStore(self.path)
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["ui"]["tile_size"] = "large"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        store.load()
        self.assertEqual(store.ui["tile_size"], "large")


if __name__ == "__main__":
    unittest.main()
