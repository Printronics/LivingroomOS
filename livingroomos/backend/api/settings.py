"""User-interface settings (the "ui" section only)."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

UI_DEFAULTS: dict[str, Any] = {
    "clock_24h": True,
    "show_clock": True,
    "tile_size": "normal",
    "reduce_motion": False,
    "confirm_power": True,
    "show_app_subtitles": True,
}


class UIPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown keys -> 422
    clock_24h: bool | None = None
    show_clock: bool | None = None
    tile_size: Literal["normal", "large"] | None = None
    reduce_motion: bool | None = None
    confirm_power: bool | None = None
    show_app_subtitles: bool | None = None


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ui: UIPatch


def _public_ui(store) -> dict[str, Any]:
    return {key: store.ui.get(key, default) for key, default in UI_DEFAULTS.items()}


@router.get("")
async def get_settings(request: Request) -> dict:
    return {"ui": _public_ui(request.app.state.store)}


@router.patch("")
async def patch_settings(patch: SettingsPatch, request: Request) -> dict:
    store = request.app.state.store
    values = patch.ui.model_dump(exclude_none=True)
    if values:
        await run_in_threadpool(store.update_ui, values)
    return {"ui": _public_ui(store)}
