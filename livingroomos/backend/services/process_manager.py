"""Sicheres Prozessmanagement für genau ein Vordergrundprogramm.

Konzept: docs/SICHERHEIT.md. Kernpunkte:

* subprocess ohne Shell. Die fertig geprüfte Befehlszeile kommt als LaunchSpec vom AppLauncher.
* Jede App läuft in eigener Sitzung/Prozessgruppe; Signale gehen nur an diese Gruppe.
* Nachzügler (z. B. Browser-Renderer, die die Gruppe verlassen) werden über einen EXAKTEN
  argv-Eintrag gefunden (--user-data-dir=<Profil dieser App>), nie über Programmnamen.
  Fremde Browserfenster bleiben dadurch unberührt.
* Identität wird über die /proc-Startzeit und pidfd geprüft (kein PID-Recycling).
* Sperrdatei verhindert zwei Backends; Zustandsdatei erlaubt die Übernahme nach einem Absturz.

Nur Standardbibliothek. Linux-spezifisch (/proc, pidfd, Kernel >= 5.3).
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import signal
import stat
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

log = logging.getLogger("livingroomos.process")

MAX_LOG_BYTES = 1_048_576  # Log einer App wird ab 1 MiB beim nächsten Start rotiert
LOG_TAIL_LINES = 20


class State(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


class ProcessBusy(Exception):
    """Es läuft bereits eine Anwendung."""

    def __init__(self, app_id: str) -> None:
        super().__init__(f"Es läuft bereits eine Anwendung: {app_id}")
        self.app_id = app_id


class LaunchFailed(Exception):
    """Start nicht möglich. Die Meldung ist für die Oberfläche bestimmt (keine Interna)."""


class BackendLocked(RuntimeError):
    """Ein anderes Backend verwaltet bereits die Prozesse."""


@dataclass(frozen=True)
class LaunchSpec:
    """Vollständig vorbereiteter, bereits geprüfter Start. Der Manager vertraut darauf."""

    app_id: str
    argv: tuple[str, ...]              # argv[0] ist ein absoluter, geprüfter Pfad
    env: Mapping[str, str]             # komplette Umgebung des Prozesses
    log_path: Path | None = None
    identity_arg: str | None = None    # exakter argv-Eintrag, der nur zu DIESER Instanz gehört
    long_running: bool = True          # sofortiges Ende (auch Exit 0) gilt als Fehlstart


@dataclass(frozen=True)
class ExitInfo:
    seq: int                # fortlaufend; das Frontend zeigt jedes Ende nur einmal
    app_id: str
    reason: str             # "ok" | "stopped" | "crashed" | "start_failed" | "ended"
    code: int | None
    signal: str | None
    runtime_s: float


# ----------------------------------------------------------------------------
# Hilfsfunktionen für Dateisystem und /proc
# ----------------------------------------------------------------------------

def ensure_private_dir(path: Path) -> Path:
    """Legt ein Verzeichnis mit Modus 0700 an. Symlinks und fremder Besitz werden abgelehnt."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        log.error("Verzeichnis nicht vertrauenswürdig (Symlink, kein Verzeichnis oder fremder Besitzer): %s", path)
        raise LaunchFailed("Ein benötigtes Verzeichnis ist nicht sicher angelegt.")
    if stat.S_IMODE(st.st_mode) != 0o700:
        os.chmod(path, 0o700)
    return path


def default_runtime_dir(data_dir: Path) -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR")
    return (Path(base) if base else Path(data_dir) / "run") / "livingroomos"


def _proc_starttime(pid: int) -> int | None:
    """Startzeit (Ticks seit Boot) eines lebenden Prozesses. None, wenn weg oder Zombie."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            data = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    fields = data.rsplit(")", 1)[-1].split()  # Feld 2 (comm) kann Leerzeichen enthalten
    if len(fields) < 20 or fields[0] in ("Z", "X"):
        return None
    try:
        return int(fields[19])  # Feld 22 der Gesamtliste
    except ValueError:
        return None


def _cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def _find_pids_with_arg(arg: str) -> list[int]:
    """Eigene Prozesse (gleiche UID), deren argv einen Eintrag EXAKT gleich `arg` enthält."""
    me, uid = os.getpid(), os.getuid()
    found: list[int] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid != uid:
                continue
        except OSError:
            continue
        if arg in _cmdline(int(entry)):
            found.append(int(entry))
    return found


def _signal_verified(pid: int, sig: int, arg: str) -> bool:
    """Signal nur, wenn der Prozess noch derselbe ist: pidfd fixiert ihn, dann Gegenprüfung."""
    fd: int | None
    try:
        fd = os.pidfd_open(pid)
    except (AttributeError, OSError):
        fd = None
    try:
        if arg not in _cmdline(pid) or os.stat(f"/proc/{pid}").st_uid != os.getuid():
            return False
        if fd is not None:
            signal.pidfd_send_signal(fd, sig)
        else:  # alter Kernel: etwas weniger sicher, aber gleiche Prüfungen
            os.kill(pid, sig)
        return True
    except (ProcessLookupError, FileNotFoundError):
        return False
    except OSError as exc:
        log.warning("Signal an Prozess %s fehlgeschlagen: %s", pid, exc)
        return False
    finally:
        if fd is not None:
            os.close(fd)


def _log_tail(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 8192))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-LOG_TAIL_LINES:])


# ----------------------------------------------------------------------------
# Manager
# ----------------------------------------------------------------------------

class ProcessManager:
    def __init__(
        self,
        startup_grace: float = 1.0,
        stop_timeout: float = 5.0,
        runtime_dir: Path | None = None,
    ) -> None:
        self.startup_grace = startup_grace
        self.stop_timeout = stop_timeout
        self.on_exit: Callable[[ExitInfo], Awaitable[None]] | None = None
        self._runtime_dir = Path(runtime_dir) if runtime_dir else None
        self._lock_fd: int | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._watcher: asyncio.Task[None] | None = None
        self._seq = 0
        self._last_exit: ExitInfo | None = None
        self._reset()

    def _reset(self) -> None:
        self._state = State.IDLE
        self._app_id: str | None = None
        self._pid: int | None = None
        self._pgid: int | None = None
        self._starttime: int | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._identity_arg: str | None = None
        self._long_running = True
        self._log_path: Path | None = None
        self._stop_requested = False

    # ------------------------------------------------------------------ Status

    def status(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "app_id": self._app_id,
            "pid": self._pid,
            "last_exit": asdict(self._last_exit) if self._last_exit else None,
        }

    # --------------------------------------------------- Lebenszyklus des Dienstes

    async def startup(self) -> None:
        """Sperre holen und eine nach einem Absturz noch laufende App übernehmen."""
        if self._runtime_dir is None:
            return
        ensure_private_dir(self._runtime_dir)
        fd = os.open(self._runtime_dir / "backend.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise BackendLocked("Ein anderes LivingroomOS-Backend läuft bereits.") from None
        self._lock_fd = fd
        await self._recover()

    async def shutdown(self, terminate: bool = True) -> None:
        """terminate=False lässt die App weiterlaufen; das nächste Backend übernimmt sie."""
        if terminate:
            await self.stop()
        elif self._watcher is not None:
            self._watcher.cancel()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    # ------------------------------------------------------------------- Start

    async def start(self, spec: LaunchSpec) -> None:
        if self._state is not State.IDLE:
            raise ProcessBusy(self._app_id or "?")
        # Zustand reservieren, bevor wir awaiten: verhindert Doppelstarts.
        self._reset()
        self._state = State.STARTING
        self._app_id = spec.app_id
        self._identity_arg = spec.identity_arg
        self._long_running = spec.long_running
        self._log_path = spec.log_path
        try:
            if spec.identity_arg and _find_pids_with_arg(spec.identity_arg):
                log.warning("%s: Reste einer früheren Instanz gefunden, beende sie", spec.app_id)
                await self._reap_strays(spec.identity_arg)
            log_fd = self._open_log(spec.log_path)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *spec.argv,
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=log_fd if log_fd is not None else asyncio.subprocess.DEVNULL,
                    stderr=log_fd if log_fd is not None else asyncio.subprocess.DEVNULL,
                    env=dict(spec.env),
                    start_new_session=True,  # eigene Sitzung und Prozessgruppe
                    umask=0o077,             # Dateien der App sind privat
                )
            finally:
                if log_fd is not None:
                    os.close(log_fd)
        except OSError as exc:
            log.error("%s: Start fehlgeschlagen: %s", spec.app_id, exc)
            self._reset()
            raise LaunchFailed(f"Start fehlgeschlagen: {exc.strerror or 'Systemfehler'}") from exc
        except BaseException:
            self._reset()
            raise

        self._proc = proc
        self._pid = proc.pid
        self._pgid = proc.pid  # start_new_session: Gruppen-ID == PID
        self._starttime = _proc_starttime(proc.pid)
        self._write_state()
        self._watcher = asyncio.create_task(self._watch(proc, spec.app_id), name=f"watch-{spec.app_id}")
        log.info("%s gestartet (pid %s)", spec.app_id, proc.pid)

    def _open_log(self, path: Path | None) -> int | None:
        if path is None:
            return None
        try:
            if path.stat().st_size > MAX_LOG_BYTES:
                os.replace(path, path.with_name(path.name + ".1"))
        except FileNotFoundError:
            pass
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        os.write(fd, f"\n=== Start {datetime.now().astimezone().isoformat(timespec='seconds')} ===\n".encode())
        return fd

    # ---------------------------------------------------------------- Beobachter

    async def _watch(self, proc: asyncio.subprocess.Process, app_id: str) -> None:
        started = time.monotonic()
        cancelled = False
        try:
            try:
                await asyncio.wait_for(proc.wait(), timeout=self.startup_grace)
            except TimeoutError:
                # Nach der Karenzzeit noch am Leben: Start gilt als gelungen.
                if self._proc is proc and self._state is State.STARTING:
                    self._state = State.RUNNING
                await proc.wait()
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            log.exception("Überwachung von %s fehlgeschlagen", app_id)
        finally:
            if not cancelled and proc.returncode is not None:
                await self._finalize(app_id, proc.returncode, time.monotonic() - started)

    async def _watch_adopted(self, pid: int, starttime: int, app_id: str) -> None:
        """Beobachtet eine übernommene App, die nicht unser Kindprozess ist (Exit-Code unbekannt)."""
        started = time.monotonic()
        while _proc_starttime(pid) == starttime:
            await asyncio.sleep(0.5)
        await self._finalize(app_id, None, time.monotonic() - started)

    async def _finalize(self, app_id: str, code: int | None, runtime: float) -> None:
        """Räumt nach dem Ende der App auf und meldet es genau einmal."""
        log_path, arg = self._log_path, self._identity_arg
        if self._state is not State.IDLE:
            self._state = State.STOPPING  # während des Aufräumens kein neuer Start
        if arg:
            await self._reap_strays(arg)

        sig_name = None
        if code is not None and code < 0:
            try:
                sig_name = signal.Signals(-code).name
            except ValueError:
                sig_name = f"SIG{-code}"

        if self._stop_requested:
            reason = "stopped"
        elif code is None:
            reason = "ended"  # übernommene App: Ende erkannt, Ursache unbekannt
        elif runtime < self.startup_grace and (code != 0 or self._long_running):
            reason = "start_failed"
        elif code == 0:
            reason = "ok"
        else:
            reason = "crashed"

        self._seq += 1
        info = ExitInfo(
            seq=self._seq,
            app_id=app_id,
            reason=reason,
            code=None if sig_name else code,
            signal=sig_name,
            runtime_s=round(runtime, 1),
        )
        self._last_exit = info
        level = logging.WARNING if reason in ("crashed", "start_failed") else logging.INFO
        log.log(level, "%s beendet: %s (code=%s, signal=%s, %.1f s)", app_id, reason, code, sig_name, runtime)
        if reason in ("crashed", "start_failed"):
            tail = _log_tail(log_path)
            if tail:
                log.warning("Letzte Ausgabe von %s:\n%s", app_id, tail)

        self._clear_state_file()
        self._reset()
        self._fire_exit_hook(info)

    def _fire_exit_hook(self, info: ExitInfo) -> None:
        hook = self.on_exit
        if hook is None:
            return

        async def run() -> None:
            try:
                await hook(info)
            except Exception:
                log.exception("Rückkehr-Hook fehlgeschlagen")

        task = asyncio.create_task(run(), name="exit-hook")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # -------------------------------------------------------------------- Stop

    async def stop(self) -> bool:
        """Beendet die laufende App: SIGTERM an ihre Gruppe, nach Frist SIGKILL."""
        watcher = self._watcher
        if self._state is State.IDLE or self._pgid is None or watcher is None:
            return False
        if self._state is not State.STOPPING:
            self._stop_requested = True
            self._state = State.STOPPING
            self._signal_tree(signal.SIGTERM)
        try:
            await asyncio.wait_for(asyncio.shield(watcher), timeout=self.stop_timeout)
        except TimeoutError:
            log.warning("SIGTERM wirkungslos, sende SIGKILL")
            self._signal_tree(signal.SIGKILL)
            try:
                await asyncio.wait_for(asyncio.shield(watcher), timeout=self.stop_timeout + 2)
            except TimeoutError:
                log.error("Prozess lässt sich nicht beenden (pid %s)", self._pid)
        return True

    def _signal_tree(self, sig: int) -> None:
        """Signal an die eigene Prozessgruppe, nur solange die Identität feststeht."""
        pgid = self._pgid
        if pgid is None:
            return
        if self._proc is not None:
            if self._proc.returncode is not None:
                return  # Anführer ist weg; Nachzügler erledigt _reap_strays
        elif _proc_starttime(self._pid or -1) != self._starttime:
            return  # übernommene App: PID gehört nicht mehr zu ihr
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            log.error("Signal an Gruppe %s nicht erlaubt: %s", pgid, exc)

    async def _reap_strays(self, arg: str) -> None:
        """Beendet Prozesse, die den exakten Instanz-Schalter tragen, aber die Gruppe verlassen haben."""
        for sig, wait in ((signal.SIGTERM, self.stop_timeout), (signal.SIGKILL, 2.0)):
            pids = _find_pids_with_arg(arg)
            if not pids:
                return
            log.info("beende %d Nachzügler (%s)", len(pids), signal.Signals(sig).name)
            for pid in pids:
                _signal_verified(pid, sig, arg)
            deadline = time.monotonic() + wait
            while time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                if not _find_pids_with_arg(arg):
                    return
        left = _find_pids_with_arg(arg)
        if left:
            log.error("Prozesse lassen sich nicht beenden: %s", left)

    # ------------------------------------------------- Zustandsdatei und Übernahme

    def _state_path(self) -> Path | None:
        return self._runtime_dir / "state.json" if self._runtime_dir else None

    def _write_state(self) -> None:
        path = self._state_path()
        if path is None:
            return
        data = {
            "app_id": self._app_id,
            "pid": self._pid,
            "pgid": self._pgid,
            "starttime": self._starttime,
            "identity_arg": self._identity_arg,
            "long_running": self._long_running,
            "log_path": str(self._log_path) if self._log_path else None,
        }
        try:
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, path)  # mkstemp legt mit 0600 an
        except OSError as exc:
            log.warning("Zustandsdatei nicht schreibbar: %s", exc)

    def _clear_state_file(self) -> None:
        path = self._state_path()
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                log.warning("Zustandsdatei nicht löschbar: %s", exc)

    async def _recover(self) -> None:
        path = self._state_path()
        if path is None:
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            app_id, pid, pgid = data["app_id"], data["pid"], data["pgid"]
            starttime, arg = data["starttime"], data.get("identity_arg")
            if not (isinstance(app_id, str) and isinstance(pid, int) and isinstance(pgid, int)
                    and isinstance(starttime, int) and (arg is None or isinstance(arg, str))):
                raise ValueError("unerwartete Typen")
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("Zustandsdatei unbrauchbar, wird verworfen: %s", exc)
            self._clear_state_file()
            return

        try:
            same_user = os.stat(f"/proc/{pid}").st_uid == os.getuid()
        except OSError:
            same_user = False
        if same_user and _proc_starttime(pid) == starttime:
            self._reset()
            self._state = State.RUNNING
            self._app_id, self._pid, self._pgid, self._starttime = app_id, pid, pgid, starttime
            self._identity_arg = arg
            self._long_running = bool(data.get("long_running", True))
            lp = data.get("log_path")
            self._log_path = Path(lp) if isinstance(lp, str) else None
            self._watcher = asyncio.create_task(self._watch_adopted(pid, starttime, app_id), name=f"adopt-{app_id}")
            log.info("%s übernommen (pid %s)", app_id, pid)
        else:
            log.info("Zustandsdatei ist veraltet (%s lief nicht mehr)", app_id)
            self._clear_state_file()
            if arg:
                await self._reap_strays(arg)
