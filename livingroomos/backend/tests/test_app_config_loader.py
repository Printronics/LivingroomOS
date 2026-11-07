"""Tests für einzelne Web-App-Konfigurationen im INI-Format."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from services.app_config_loader import load_app_configs  # noqa: E402


VALID = """[app]
id = example
title = Example
subtitle = Testseite
icon = E
color = #123456
category = media

[browser]
executable = google-chrome-stable
url = https://example.com/
fullscreen = true
wayland = true
"""


class AppConfigLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, name: str, content: str = VALID) -> Path:
        path = self.directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_loads_cfg_and_builds_safe_chrome_command(self) -> None:
        self.write("example.cfg")
        apps, problems = load_app_configs(self.directory)
        self.assertEqual(problems, [])
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["id"], "example")
        self.assertEqual(apps[0]["icon"], "E")
        self.assertEqual(apps[0]["color"], "#123456")
        self.assertEqual(apps[0]["command"], [
            "google-chrome-stable",
            "--app=https://example.com/",
            "--user-data-dir={profile_dir}",
            "--ozone-platform=wayland",
            "--start-fullscreen",
        ])

    def test_rejects_filename_id_mismatch(self) -> None:
        self.write("another-name.cfg")
        apps, problems = load_app_configs(self.directory)
        self.assertEqual(apps, [])
        self.assertIn("Dateiname", problems[0])

    def test_rejects_non_http_url(self) -> None:
        self.write("example.cfg", VALID.replace("https://example.com/", "javascript:alert(1)"))
        apps, problems = load_app_configs(self.directory)
        self.assertEqual(apps, [])
        self.assertIn("HTTP- oder HTTPS-Adresse", problems[0])

    def test_rejects_browser_executable_outside_allowlist(self) -> None:
        self.write("example.cfg", VALID.replace("google-chrome-stable", "/tmp/evil"))
        apps, problems = load_app_configs(self.directory)
        self.assertEqual(apps, [])
        self.assertIn("Browser", problems[0])

    def test_rejects_invalid_color(self) -> None:
        self.write("example.cfg", VALID.replace("#123456", "red"))
        apps, problems = load_app_configs(self.directory)
        self.assertEqual(apps, [])
        self.assertIn("#RRGGBB", problems[0])

    def test_invalid_file_does_not_hide_valid_files(self) -> None:
        self.write("broken.cfg", "[app]\nid = broken\n")
        self.write("example.cfg")
        apps, problems = load_app_configs(self.directory)
        self.assertEqual([app["id"] for app in apps], ["example"])
        self.assertEqual(len(problems), 1)

    def test_missing_directory_is_an_empty_configuration(self) -> None:
        apps, problems = load_app_configs(self.directory / "missing")
        self.assertEqual(apps, [])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
