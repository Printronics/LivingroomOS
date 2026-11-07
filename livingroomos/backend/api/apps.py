"""Endpunkte zum Auflisten, Starten und Beenden von Anwendungen."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request

from services.app_launcher import AppNotFound, NotInstalled
from services.process_manager import LaunchFailed, ProcessBusy

router = APIRouter(prefix="/api/v1/apps", tags=["apps"])

# Nur IDs aus der Konfiguration sind gültig; das Format wird zusätzlich geprüft.
AppId = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")]


@router.get("")
async def list_apps(request: Request) -> dict:
    launcher = request.app.state.launcher
    return {"apps": launcher.list_apps(), "status": launcher.status()}


@router.get("/status")
async def app_status(request: Request) -> dict:
    return request.app.state.launcher.status()


@router.post("/stop")
async def stop_app(request: Request) -> dict:
    return await request.app.state.launcher.stop()


@router.post("/{app_id}/stop")
async def stop_one_app(app_id: AppId, request: Request) -> dict:
    """Beendet nur die genannte App. Läuft eine andere oder keine, passiert nichts (409)."""
    launcher = request.app.state.launcher
    if launcher.status()["app_id"] != app_id:
        raise HTTPException(
            409,
            detail={
                "code": "not_running",
                "message": f"{launcher.title(app_id)} läuft nicht.",
                "status": launcher.status(),
            },
        )
    return await launcher.stop(app_id)


@router.post("/{app_id}/launch", status_code=202)
async def launch_app(app_id: AppId, request: Request) -> dict:
    launcher = request.app.state.launcher
    try:
        return await launcher.launch(app_id)
    except AppNotFound:
        raise HTTPException(404, detail={"code": "app_not_found", "message": f"Unbekannte App: {app_id}"})
    except NotInstalled as exc:
        raise HTTPException(
            422,
            detail={
                "code": "not_installed",
                "message": f"„{exc.executable}“ wurde nicht gefunden. Bitte installieren oder die passende Datei unter config/apps/ prüfen.",
            },
        )
    except ProcessBusy as exc:
        raise HTTPException(
            409,
            detail={
                "code": "busy",
                "message": f"Es läuft bereits {launcher.title(exc.app_id)}.",
                "status": launcher.status(),
            },
        )
    except LaunchFailed as exc:
        raise HTTPException(500, detail={"code": "launch_failed", "message": str(exc)})
