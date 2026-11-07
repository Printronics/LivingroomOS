"""Tests for process management and launch validation. Real processes, standard library only.

Run from backend/: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from services import process_manager as pm_mod  # noqa: E402
from services.app_launcher import AppLauncher, LaunchRefused, NotInstalled, parse_apps  # noqa: E402
from services.process_manager import BackendLocked, LaunchFailed, ProcessBusy, ProcessManager  # noqa: E402
from services.settings_store import SettingsStore  # noqa: E402

SLEEP = "import time; time.sleep(60)"
PY = "{python}"


def app(app_id: str, *command: str, **extra) -> dict:
    return {"id": app_id, "title": app_id.title(), "command": list(command), **extra}


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        (self.tmp / "bin").mkdir()
        self.data = self.tmp / "data"
        self.run_dir = self.tmp / "run"
        self.managers: list[ProcessManager] = []
        self.procs: list[subprocess.Popen] = []

    async def asyncTearDown(self) -> None:
        for m in self.managers:
            await m.shutdown()
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
        self._tmp.cleanup()
        logging.disable(logging.NOTSET)

    def build(self, apps: list[dict], server: dict | None = None, grace: float = 0.4, stop_timeout: float = 1.5) -> AppLauncher:
        cfg = {
            "server": {
                "data_dir": str(self.data),
                "trusted_bin_dirs": ["/usr/local/bin", "/usr/bin", "/opt", str(self.tmp / "bin")],
                **(server or {}),
            },
            "apps": apps,
        }
        path = self.tmp / "settings.json"
        path.write_text(json.dumps(cfg))
        manager = ProcessManager(grace, stop_timeout, self.run_dir)
        self.managers.append(manager)
        return AppLauncher(SettingsStore(path), manager)

    async def until(self, cond, timeout: float = 5.0) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return
            await asyncio.sleep(0.05)
        self.fail("Condition was not met in time")

    def bystander(self, *extra: str) -> subprocess.Popen:
        p = subprocess.Popen([sys.executable, "-c", SLEEP, *extra], start_new_session=True)
        self.procs.append(p)
        return p

    @staticmethod
    def alive(pid: int) -> bool:
        return pm_mod._proc_starttime(pid) is not None


class TestKonfiguration(Base):
    def test_ungueltige_eintraege_werden_abgelehnt(self) -> None:
        apps, problems = parse_apps([
            app("a", PY, "{shell}"),                                         # unbekannter Platzhalter
            app("b", "google-chrome-stable", "--app=https://x"),                         # browser without a profile
            app("c", "google-chrome-stable", "--no-sandbox", "--user-data-dir={profile_dir}"),
            app("d", "google-chrome-stable", "--remote-debugging-port=9222", "--user-data-dir={profile_dir}"),
            app("e", PY, env={"LD_PRELOAD": "/x"}),
            app("f", PY, env={"PATH": "/tmp"}),
            app("g", PY, "a\0b"),
            app("../x", PY),
            {"id": "h", "title": "H", "command": "rm -rf /"},               # kein Listenformat
            app("ok", PY, "-c", "pass", env={"MY_VAR": "1"}),
        ])
        self.assertEqual(list(apps), ["ok"])
        self.assertEqual(len(problems), 9, problems)

    def test_doppelte_id(self) -> None:
        apps, problems = parse_apps([app("x", PY), app("x", PY)])
        self.assertEqual(len(apps), 1)
        self.assertEqual(len(problems), 1)

    def test_ausfuehrbare_datei_pruefungen(self) -> None:
        launcher = self.build([])
        tool = self.tmp / "bin" / "tool"
        tool.write_text("#!/bin/sh\nsleep 60\n")
        tool.chmod(0o755)
        self.assertEqual(launcher._resolve_executable("tool"), tool.resolve())

        tool.chmod(0o775)  # group-writable
        with self.assertRaises(LaunchRefused):
            launcher._resolve_executable("tool")
        tool.chmod(0o755)

        self.tmp.chmod(0o775)  # a writable parent directory is also unsafe
        with self.assertRaises(LaunchRefused):
            launcher._resolve_executable("tool")
        self.tmp.chmod(0o700)

        outside = self.tmp / "other" / "tool"
        outside.parent.mkdir()
        outside.write_text("#!/bin/sh\n")
        outside.chmod(0o755)
        with self.assertRaises(LaunchRefused):  # absolute path outside trusted directories
            launcher._resolve_executable(str(outside))
        link = self.tmp / "bin" / "linked"
        link.symlink_to(outside)
        with self.assertRaises(LaunchRefused):  # symlink from a trusted directory to an external path
            launcher._resolve_executable("linked")
        with self.assertRaises(LaunchRefused):
            launcher._resolve_executable("./tool")
        with self.assertRaises(LaunchRefused):
            launcher._resolve_executable("bin/tool")
        with self.assertRaises(NotInstalled):
            launcher._resolve_executable("does-not-exist")

    def test_liste_enthaelt_keine_befehle(self) -> None:
        launcher = self.build([app("x", PY, "-c", "SECRET")])
        self.assertNotIn("SECRET", json.dumps(launcher.list_apps()))


class TestLebenszyklus(Base):
    async def test_start_status_stop(self) -> None:
        launcher = self.build([app("a", PY, "-c", SLEEP)])
        st = await launcher.launch("a")
        self.assertEqual((st["state"], st["app_id"]), ("starting", "a"))
        self.assertTrue(self.alive(st["pid"]))
        await self.until(lambda: launcher.status()["state"] == "running")

        pid = launcher.status()["pid"]
        st = await launcher.stop()
        self.assertEqual(st["state"], "idle")
        self.assertIsNone(st["pid"])
        self.assertEqual(st["last_exit"]["reason"], "stopped")
        self.assertEqual(st["last_exit"]["signal"], "SIGTERM")
        self.assertFalse(self.alive(pid))
        self.assertFalse((self.run_dir / "state.json").exists())

    async def test_doppelstart(self) -> None:
        launcher = self.build([app("a", PY, "-c", SLEEP), app("b", PY, "-c", SLEEP)])
        r = await asyncio.gather(launcher.launch("a"), launcher.launch("b"), return_exceptions=True)
        self.assertEqual(sum(isinstance(x, ProcessBusy) for x in r), 1, r)
        again = await launcher.launch("a")  # dieselbe App: idempotent
        self.assertEqual(again["app_id"], "a")
        with self.assertRaises(ProcessBusy):
            await launcher.launch("b")

    async def test_gezieltes_beenden(self) -> None:
        launcher = self.build([app("a", PY, "-c", SLEEP)])
        await launcher.launch("a")
        st = await launcher.stop("anderes")  # falsche App: nichts passiert
        self.assertEqual(st["app_id"], "a")
        self.assertTrue(self.alive(st["pid"]))
        st = await launcher.stop("a")
        self.assertEqual(st["state"], "idle")

    async def test_sigkill_bei_hartnaeckigem_prozess(self) -> None:
        code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"
        launcher = self.build([app("a", PY, "-c", code)])
        await launcher.launch("a")
        await self.until(lambda: launcher.status()["state"] == "running")
        t0 = time.monotonic()
        st = await launcher.stop()
        self.assertGreater(time.monotonic() - t0, 1.2)
        self.assertEqual(st["last_exit"]["signal"], "SIGKILL")

    async def test_kindprozesse_der_gruppe_werden_beendet(self) -> None:
        code = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); time.sleep(60)"
        launcher = self.build([app("a", PY, "-c", code)])
        await launcher.launch("a")
        pgid = launcher.status()["pid"]
        await self.until(lambda: len(self._group_members(pgid)) >= 2)
        await launcher.stop()
        self.assertEqual(self._group_members(pgid), [])

    @staticmethod
    def _group_members(pgid: int) -> list[int]:
        found = []
        for entry in os.listdir("/proc"):
            if entry.isdigit() and pm_mod._proc_starttime(int(entry)) is not None:
                try:
                    if os.getpgid(int(entry)) == pgid:
                        found.append(int(entry))
                except OSError:
                    pass
        return found


class TestAbstuerze(Base):
    async def exit_of(self, launcher: AppLauncher, app_id: str) -> dict:
        await launcher.launch(app_id)
        await self.until(lambda: launcher.status()["state"] == "idle", 6)
        return launcher.status()["last_exit"]

    async def test_klassifikation(self) -> None:
        launcher = self.build([
            app("crash", PY, "-c", "import sys,time; time.sleep(0.8); sys.exit(3)"),
            app("quick", PY, "-c", "import sys; sys.exit(7)"),
            app("quick0", PY, "-c", "pass"),
            app("quick0b", PY, "-c", "pass", long_running=False),
            app("fine", PY, "-c", "import time; time.sleep(0.8)"),
            app("killed", PY, "-c", "import os,signal,time; time.sleep(0.8); os.kill(os.getpid(), signal.SIGKILL)"),
        ])
        got = {k: await self.exit_of(launcher, k) for k in ("crash", "quick", "quick0", "quick0b", "fine", "killed")}
        self.assertEqual((got["crash"]["reason"], got["crash"]["code"]), ("crashed", 3))
        self.assertEqual((got["quick"]["reason"], got["quick"]["code"]), ("start_failed", 7))
        self.assertEqual(got["quick0"]["reason"], "start_failed")  # immediate exit 0 = handoff to an external instance
        self.assertEqual(got["quick0b"]["reason"], "ok")
        self.assertEqual(got["fine"]["reason"], "ok")
        self.assertEqual((got["killed"]["reason"], got["killed"]["signal"]), ("crashed", "SIGKILL"))
        self.assertEqual([got[k]["seq"] for k in got], [1, 2, 3, 4, 5, 6])  # jedes Ende einmal, fortlaufend

    async def test_log_datei_und_absturzausgabe(self) -> None:
        code = "import sys,time; print('boom-stdout'); sys.stdout.flush(); sys.stderr.write('boom-stderr\\n'); time.sleep(0.8); sys.exit(2)"
        launcher = self.build([app("a", PY, "-c", code)])
        logging.disable(logging.NOTSET)
        with self.assertLogs("livingroomos.process", level="WARNING") as cm:
            await self.exit_of(launcher, "a")
        logging.disable(logging.CRITICAL)
        text = (self.data / "logs" / "a.log").read_text()
        self.assertIn("boom-stdout", text)
        self.assertIn("boom-stderr", text)
        self.assertEqual(stat.S_IMODE((self.data / "logs" / "a.log").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.data / "logs").stat().st_mode), 0o700)
        self.assertTrue(any("Last output" in line and "boom-stderr" in line for line in cm.output), cm.output)

    async def test_log_rotation(self) -> None:
        logs = self.data / "logs"
        logs.mkdir(parents=True)
        (logs / "a.log").write_bytes(b"x" * (pm_mod.MAX_LOG_BYTES + 10))
        launcher = self.build([app("a", PY, "-c", SLEEP)])
        await launcher.launch("a")
        self.assertTrue((logs / "a.log.1").exists())
        self.assertLess((logs / "a.log").stat().st_size, 200)

    async def test_rueckkehr_hook_genau_einmal(self) -> None:
        marker = self.tmp / "marker"
        launcher = self.build(
            [app("a", PY, "-c", "import time; time.sleep(0.6)")],
            server={"return_to_launcher_command": [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x')"]},
        )
        await self.exit_of(launcher, "a")
        await self.until(lambda: marker.exists() and marker.read_text() == "x")
        await asyncio.sleep(0.5)
        self.assertEqual(marker.read_text(), "x")

    def test_return_to_launcher_command_is_validated(self) -> None:
        launcher = self.build([], server={"return_to_launcher_command": ["wlrctl", "--no-sandbox"]})
        self.assertIsNone(launcher._return_cmd)
        self.assertTrue(any("return_to_launcher_command" in p for p in launcher.problems))


class TestIsolation(Base):
    async def test_environment_is_filtered(self) -> None:
        os.environ["LD_PRELOAD"] = "/do-not-load.so"
        os.environ["SECRET_TOKEN"] = "secret"
        self.addCleanup(os.environ.pop, "LD_PRELOAD", None)
        self.addCleanup(os.environ.pop, "SECRET_TOKEN", None)
        # No braces in the argument: {name} would be an (unknown) placeholder and is rejected.
        code = "import os,time; print('\\n'.join(k + '=' + v for k, v in os.environ.items()), flush=True); time.sleep(60)"
        launcher = self.build([app("a", PY, "-c", code, env={"MY_VAR": "42"})])
        await launcher.launch("a")
        log_file = self.data / "logs" / "a.log"
        await self.until(lambda: log_file.exists() and "MY_VAR" in log_file.read_text())
        text = log_file.read_text()
        self.assertIn("MY_VAR=42", text)
        self.assertNotIn("LD_PRELOAD", text)
        self.assertNotIn("SECRET_TOKEN", text)
        self.assertIn("PATH=/usr/local/bin:/usr/bin:/opt:" + str(self.tmp / "bin"), text)

    async def test_profilordner_privat_und_symlink_abgelehnt(self) -> None:
        launcher = self.build([app("a", PY, "-c", SLEEP, "--user-data-dir={profile_dir}")])
        await launcher.launch("a")
        prof = self.data / "profiles" / "a"
        self.assertEqual(stat.S_IMODE(prof.stat().st_mode), 0o700)
        await launcher.stop()

        evil = self.tmp / "evil"
        evil.mkdir()
        prof.rmdir()
        prof.symlink_to(evil)
        with self.assertRaises(LaunchFailed):
            await launcher.launch("a")
        self.assertEqual(launcher.status()["state"], "idle")

    async def test_nachzuegler_nur_mit_exaktem_profil_argument(self) -> None:
        leader = (
            "import subprocess,sys,time\n"
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)',sys.argv[1]], start_new_session=True)\n"
            "time.sleep(60)\n"
        )
        launcher = self.build([app("a", PY, "-c", leader, "--user-data-dir={profile_dir}")])
        other = self.bystander("--user-data-dir=" + str(self.data / "profiles" / "anderes"))  # anderes Profil
        plain = self.bystander()                                                              # same executable, no profile argument
        await launcher.launch("a")
        arg = "--user-data-dir=" + str(self.data / "profiles" / "a")
        await self.until(lambda: len(pm_mod._find_pids_with_arg(arg)) >= 2)  # leader + escaped child process
        await launcher.stop()
        self.assertEqual(pm_mod._find_pids_with_arg(arg), [])
        self.assertIsNone(other.poll(), "foreign profile must not be terminated")
        self.assertIsNone(plain.poll(), "same-named executable must not be terminated")

    async def test_reste_frueherer_instanz_werden_vor_dem_start_beendet(self) -> None:
        arg = "--user-data-dir=" + str(self.data / "profiles" / "a")
        orphan = self.bystander(arg)
        launcher = self.build([app("a", PY, "-c", SLEEP, "--user-data-dir={profile_dir}")])
        await launcher.launch("a")
        await self.until(lambda: orphan.poll() is not None)
        self.assertNotEqual(launcher.status()["pid"], orphan.pid)


class TestSperreUndUebernahme(Base):
    async def test_zweites_backend_wird_ausgesperrt(self) -> None:
        a = self.build([])
        await a.startup()
        b = self.build([])
        with self.assertRaises(BackendLocked):
            await b.startup()
        await a.shutdown()
        await b.startup()  # allowed after releasing the lock

    async def test_app_wird_nach_backend_absturz_uebernommen(self) -> None:
        launcher = self.build([app("a", PY, "-c", SLEEP, "--user-data-dir={profile_dir}"), app("b", PY, "-c", SLEEP)])
        helper = (
            "import asyncio, os, sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from pathlib import Path\n"
            "from services.settings_store import SettingsStore\n"
            "from services.process_manager import ProcessManager\n"
            "from services.app_launcher import AppLauncher\n"
            "async def main():\n"
            "    l = AppLauncher(SettingsStore(Path(sys.argv[2])), ProcessManager(0.4, 1.5, Path(sys.argv[3])))\n"
            "    await l.startup(); st = await l.launch('a'); print(st['pid'], flush=True)\n"
            "asyncio.run(main()); os._exit(0)  # 'crash': no shutdown, app keeps running\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", helper, str(BACKEND), str(self.tmp / "settings.json"), str(self.run_dir)],
            capture_output=True, text=True, timeout=20, check=True,
        )
        pid = int(out.stdout.strip())
        self.assertTrue(self.alive(pid))
        self.assertTrue((self.run_dir / "state.json").exists())

        await launcher.startup()  # neues Backend
        st = launcher.status()
        self.assertEqual((st["state"], st["app_id"], st["pid"]), ("running", "a", pid))
        with self.assertRaises(ProcessBusy):  # adopted app blocks further launches
            await launcher.launch("b")
        st = await launcher.stop()
        self.assertEqual(st["state"], "idle")
        self.assertEqual(st["last_exit"]["reason"], "stopped")
        self.assertFalse(self.alive(pid))
        self.assertFalse((self.run_dir / "state.json").exists())

    async def test_veraltete_zustandsdatei_wird_verworfen(self) -> None:
        launcher = self.build([])
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "state.json").write_text(json.dumps({
            "app_id": "a", "pid": 2**22 - 3, "pgid": 2**22 - 3, "starttime": 1, "identity_arg": None,
        }))
        await launcher.startup()
        self.assertEqual(launcher.status()["state"], "idle")
        self.assertFalse((self.run_dir / "state.json").exists())

    async def test_pid_recycling_wird_erkannt(self) -> None:
        """Same PID, different start time: the backend must NOT adopt the foreign process."""
        victim = self.bystander()
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "state.json").write_text(json.dumps({
            "app_id": "a", "pid": victim.pid, "pgid": victim.pid,
            "starttime": pm_mod._proc_starttime(victim.pid) + 1, "identity_arg": None,
        }))
        launcher = self.build([app("a", PY, "-c", SLEEP)])
        await launcher.startup()
        self.assertEqual(launcher.status()["state"], "idle")
        self.assertIsNone(victim.poll(), "foreign process must not be touched")


if __name__ == "__main__":
    unittest.main()
