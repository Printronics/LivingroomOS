"""Health status and narrowly scoped local power actions."""
from __future__ import annotations

import platform
import subprocess
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1", tags=["system"])
_STARTED = time.monotonic()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/system/status")
async def system_status(request: Request) -> dict:
    return {
        "version": request.app.version,
        "uptime_s": int(time.monotonic() - _STARTED),
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "config_problems": request.app.state.launcher.problems,
        "app": request.app.state.launcher.status(),
    }


@router.post("/system/power/{action}", status_code=202)
async def system_power(action: str) -> dict:
    """Allows only restart or shutdown; arbitrary commands are never accepted."""
    commands = {
        "restart": ["systemctl", "reboot"],
        "shutdown": ["systemctl", "poweroff"],
    }
    command = commands.get(action)
    if command is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "unknown_power_action", "message": "Action not supported."},
        )
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "power_unavailable",
                "message": f"Could not start system action: {exc.strerror}",
            },
        ) from exc
    return {"status": "accepted", "action": action}
