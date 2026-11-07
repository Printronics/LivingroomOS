"""Tests for system/bin/livingroomosctl against a small test server (standard library only)."""
from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "system" / "bin" / "livingroomosctl"


def load_ctl():
    loader = importlib.machinery.SourceFileLoader("livingroomosctl", str(SCRIPT))
    spec = importlib.util.spec_from_loader("livingroomosctl", loader)
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # kein __pycache__ neben dem Skript
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class FakeBackend(BaseHTTPRequestHandler):
    seen: list = []
    health_ok = True

    def _reply(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self.seen.append(("GET", self.path, self.headers.get("X-LivingroomOS")))
        if self.path == "/api/v1/health":
            return self._reply(200 if self.health_ok else 503, {"status": "ok"})
        self._reply(200, {"state": "idle", "app_id": None})

    def do_POST(self) -> None:
        self.seen.append(("POST", self.path, self.headers.get("X-LivingroomOS")))
        self._reply(200, {"state": "idle", "app_id": None})

    def log_message(self, *args) -> None:  # Testausgabe ruhig halten
        pass


class CtlTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeBackend.seen = []
        FakeBackend.health_ok = True
        self.server = HTTPServer(("127.0.0.1", 0), FakeBackend)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = mock.patch.dict(os.environ, {"LIVINGROOMOS_PORT": str(self.server.server_port), "HTTP_PROXY": "http://127.0.0.1:9", "http_proxy": "http://127.0.0.1:9"})
        self.env.start()
        self.ctl = load_ctl()

    def tearDown(self) -> None:
        self.env.stop()
        self.server.shutdown()
        self.server.server_close()

    def run_ctl(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.ctl.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_home_posts_stop_with_required_header(self) -> None:
        code, out, _ = self.run_ctl("home")
        self.assertEqual(code, 0)
        self.assertEqual(FakeBackend.seen, [("POST", "/api/v1/apps/stop", "1")])
        self.assertEqual(json.loads(out)["state"], "idle")

    def test_status_is_a_read_only_get(self) -> None:
        code, out, _ = self.run_ctl("status")
        self.assertEqual(code, 0)
        self.assertEqual(FakeBackend.seen[0][:2], ("GET", "/api/v1/apps/status"))

    def test_wait_succeeds_when_backend_is_ready(self) -> None:
        self.assertEqual(self.run_ctl("wait", "3")[0], 0)

    def test_wait_times_out_when_backend_is_not_ready(self) -> None:
        FakeBackend.health_ok = False
        code, _, err = self.run_ctl("wait", "1")
        self.assertEqual(code, 1)
        self.assertIn("did not become ready in time", err)

    def test_unreachable_backend_is_exit_1_with_message(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        code, _, err = self.run_ctl("status")
        self.assertEqual(code, 1)
        self.assertIn("not reachable", err)
        self.server = HTTPServer(("127.0.0.1", 0), FakeBackend)  # tearDown requires a valid server
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def test_usage_errors_are_exit_2(self) -> None:
        for args in ([], ["unbekannt"], ["home", "x"], ["status", "x"], ["wait", "abc"]):
            with self.subTest(args=args):
                self.assertEqual(self.run_ctl(*args)[0], 2)
        self.assertEqual(FakeBackend.seen, [])

    def test_only_loopback_is_ever_contacted(self) -> None:
        with mock.patch.dict(os.environ, {"LIVINGROOMOS_PORT": "8123"}):
            self.assertEqual(self.ctl.base_url(), "http://127.0.0.1:8123")


if __name__ == "__main__":
    unittest.main()
