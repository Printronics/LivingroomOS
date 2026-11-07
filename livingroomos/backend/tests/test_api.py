"""Tests for the HTTP interface (FastAPI) using real processes.

Requires fastapi and httpx (requirements-dev.txt; Debian: python3-fastapi, python3-httpx). If either is missing,
the tests are skipped. Run from backend/: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

try:
    import fastapi  # noqa: F401
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient

    HAVE_STACK = True
except ImportError:
    HAVE_STACK = False

WRITE = {"X-LivingroomOS": "1"}
SLEEP = ["{python}", "-c", "import time; time.sleep(60)"]


def app_entry(app_id: str, command: list[str]) -> dict:
    return {"id": app_id, "title": app_id.title(), "command": command}


@unittest.skipUnless(HAVE_STACK, "fastapi and httpx are missing (see requirements-dev.txt)")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls._tmp.name)
        cls.config_path = tmp / "settings.json"
        cls.config_path.write_text(
            json.dumps(
                {
                    "server": {"data_dir": str(tmp / "data"), "startup_grace_s": 0.3, "stop_timeout_s": 3.0},
                    "ui": {},
                    "apps": [
                        app_entry("alpha", SLEEP),
                        app_entry("beta", SLEEP),
                        app_entry("crash", ["{python}", "-c", "import sys, time; time.sleep(0.8); sys.exit(3)"]),
                        app_entry("missing", ["livingroomos-test-program-does-not-exist"]),
                    ],
                }
            ),
            encoding="utf-8",
        )
        cls._env = mock.patch.dict(os.environ, {"LIVINGROOMOS_CONFIG": str(cls.config_path), "XDG_RUNTIME_DIR": str(tmp / "run")})
        cls._env.start()
        sys.modules.pop("main", None)  # Configuration path is read during import
        cls.main = importlib.import_module("main")
        cls._client_cm = TestClient(cls.main.app, base_url="http://127.0.0.1:8750")
        cls.client = cls._client_cm.__enter__()  # runs the lifespan (lock, launcher)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)
        cls._env.stop()
        sys.modules.pop("main", None)
        cls._tmp.cleanup()

    def setUp(self) -> None:
        self.client.post("/api/v1/apps/stop", headers=WRITE)
        self.wait_for_state("idle")

    def wait_for_state(self, state: str, timeout: float = 6.0) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            status = self.client.get("/api/v1/apps/status").json()
            if status["state"] == state or time.monotonic() > deadline:
                return status
            time.sleep(0.05)

    def launch(self, app_id: str):
        return self.client.post(f"/api/v1/apps/{app_id}/launch", headers=WRITE)

    # --- Security -----------------------------------------------------------------------

    def test_health(self) -> None:
        self.assertEqual(self.client.get("/api/v1/health").json(), {"status": "ok"})

    def test_foreign_host_header_is_rejected(self) -> None:
        self.assertEqual(self.client.get("/api/v1/health", headers={"Host": "evil.example"}).status_code, 400)

    def test_write_without_header_is_forbidden_in_the_documented_error_format(self) -> None:
        response = self.client.post("/api/v1/apps/alpha/launch")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "forbidden")
        self.assertEqual(self.client.get("/api/v1/apps/status").json()["state"], "idle")

    def test_security_headers(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_api_documentation_endpoints_are_disabled(self) -> None:
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_app_list_never_exposes_commands(self) -> None:
        apps = self.client.get("/api/v1/apps").json()["apps"]
        self.assertEqual({a["id"] for a in apps}, {"alpha", "beta", "crash", "missing"})
        for entry in apps:
            self.assertEqual(set(entry), {"id", "title", "subtitle", "icon", "color", "available", "category"})
        self.assertNotIn("sleep", json.dumps(apps))

    # --- Launch, stop, status --------------------------------------------------------------

    def test_launch_stop_cycle(self) -> None:
        response = self.launch("alpha")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["app_id"], "alpha")
        self.assertIsInstance(response.json()["pid"], int)
        self.assertEqual(self.wait_for_state("running")["app_id"], "alpha")

        stopped = self.client.post("/api/v1/apps/stop", headers=WRITE).json()
        self.assertEqual(stopped["state"], "idle")
        self.assertEqual(stopped["last_exit"]["reason"], "stopped")

    def test_second_launch_of_same_app_is_idempotent(self) -> None:
        first = self.launch("alpha").json()
        second = self.launch("alpha")
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()["pid"], first["pid"])

    def test_launching_another_app_is_refused_with_409(self) -> None:
        self.launch("alpha")
        response = self.launch("beta")
        self.assertEqual(response.status_code, 409)
        error = response.json()["error"]
        self.assertEqual(error["code"], "busy")
        self.assertEqual(error["status"]["app_id"], "alpha")

    def test_unknown_and_malformed_app_ids(self) -> None:
        self.assertEqual(self.launch("unbekannt").status_code, 404)
        self.assertEqual(self.launch("unbekannt").json()["error"]["code"], "app_not_found")
        bad = self.launch("BAD")
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["error"]["code"], "invalid_request")

    def test_missing_program_is_reported_as_not_installed(self) -> None:
        response = self.launch("missing")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "not_installed")
        self.assertEqual(self.client.get("/api/v1/apps/status").json()["state"], "idle")

    def test_targeted_stop_only_affects_the_named_app(self) -> None:
        self.assertEqual(self.client.post("/api/v1/apps/alpha/stop", headers=WRITE).status_code, 409)  # nothing is running
        self.launch("beta")
        wrong = self.client.post("/api/v1/apps/alpha/stop", headers=WRITE)
        self.assertEqual(wrong.status_code, 409)
        self.assertEqual(wrong.json()["error"]["code"], "not_running")
        self.assertEqual(self.client.get("/api/v1/apps/status").json()["app_id"], "beta")
        right = self.client.post("/api/v1/apps/beta/stop", headers=WRITE)
        self.assertEqual(right.status_code, 200)
        self.assertEqual(right.json()["state"], "idle")

    def test_crash_is_detected_and_reported_once(self) -> None:
        self.launch("crash")
        status = self.wait_for_state("idle", timeout=8)
        self.assertEqual(status["last_exit"]["reason"], "crashed")
        self.assertEqual(status["last_exit"]["code"], 3)
        self.assertEqual(status["last_exit"]["app_id"], "crash")

    # --- Settings --------------------------------------------------------------------

    def test_settings_defaults_and_patch_are_persisted(self) -> None:
        self.assertEqual(set(self.client.get("/api/v1/settings").json()["ui"]), {"clock_24h", "show_clock", "tile_size", "reduce_motion", "confirm_power", "show_app_subtitles"})
        response = self.client.patch("/api/v1/settings", json={"ui": {"tile_size": "large"}}, headers=WRITE)
        self.assertEqual(response.json()["ui"]["tile_size"], "large")
        self.assertEqual(json.loads(self.config_path.read_text(encoding="utf-8"))["ui"]["tile_size"], "large")
        self.client.patch("/api/v1/settings", json={"ui": {"tile_size": "normal"}}, headers=WRITE)

    def test_settings_reject_unknown_keys_and_invalid_values(self) -> None:
        for body in ({"ui": {"unbekannt": 1}}, {"ui": {"tile_size": "riesig"}}, {"ui": {"clock_24h": "ja"}}, {"extra": 1}):
            with self.subTest(body=body):
                response = self.client.patch("/api/v1/settings", json=body, headers=WRITE)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "invalid_request")

    def test_settings_cannot_change_apps_or_server_sections(self) -> None:
        before = self.config_path.read_text(encoding="utf-8")
        self.client.patch("/api/v1/settings", json={"apps": []}, headers=WRITE)
        self.client.patch("/api/v1/settings", json={"server": {"data_dir": "/"}}, headers=WRITE)
        self.assertEqual(json.loads(self.config_path.read_text(encoding="utf-8"))["apps"], json.loads(before)["apps"])

    # --- System, frontend -----------------------------------------------------------------

    def test_system_status(self) -> None:
        from version import __version__

        data = self.client.get("/api/v1/system/status").json()
        self.assertEqual(data["version"], __version__)
        self.assertTrue(data["machine"])
        self.assertIsInstance(data["config_problems"], list)

    def test_frontend_is_served_and_traversal_is_blocked(self) -> None:
        index = self.client.get("/")
        self.assertEqual(index.status_code, 200)
        self.assertIn("LivingroomOS", index.text)
        self.assertEqual(self.client.get("/js/navigation.js").status_code, 200)
        for path in ("/..%2fbackend%2fmain.py", "/%2e%2e/backend/main.py", "/js/../../backend/main.py"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertNotIn("FastAPI(", response.text)


    def test_power_actions_are_allowlisted(self):
        with patch("api.system.subprocess.Popen") as popen:
            response = self.client.post("/api/v1/system/power/restart", headers={"X-LivingroomOS": "1"})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(popen.call_args.args[0], ["systemctl", "reboot"])
            response = self.client.post("/api/v1/system/power/shutdown", headers={"X-LivingroomOS": "1"})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(popen.call_args.args[0], ["systemctl", "poweroff"])
            response = self.client.post("/api/v1/system/power/anything", headers={"X-LivingroomOS": "1"})
            self.assertEqual(response.status_code, 404)
            self.assertEqual(popen.call_count, 2)



if __name__ == "__main__":
    unittest.main()
