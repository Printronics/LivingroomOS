"""LivingroomOS – Backend-Einstiegspunkt.

Start (aus dem Ordner backend/):
    python3 -m uvicorn main:app --host 127.0.0.1 --port 8750
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api import apps as apps_api
from api import settings as settings_api
from api import system as system_api
from services.app_launcher import AppLauncher
from services.process_manager import ProcessManager, default_runtime_dir
from services.settings_store import SettingsError, SettingsStore
from version import __version__

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
CONFIG_PATH = Path(os.environ.get("LIVINGROOMOS_CONFIG", BASE_DIR / "config" / "settings.json"))

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("livingroomos")


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = SettingsStore(CONFIG_PATH)  # SettingsError beendet den Start mit klarer Meldung
    data_dir = Path(str(store.server.get("data_dir", "~/.local/share/livingroomos"))).expanduser()
    manager = ProcessManager(
        startup_grace=float(store.server.get("startup_grace_s", 1.0)),
        stop_timeout=float(store.server.get("stop_timeout_s", 5.0)),
        runtime_dir=default_runtime_dir(data_dir),
    )
    launcher = AppLauncher(store, manager)
    await launcher.startup()  # Sperre holen, laufende App nach Absturz übernehmen (BackendLocked → Abbruch)
    app.state.store = store
    app.state.manager = manager
    app.state.launcher = launcher
    log.info("Konfiguration: %s", CONFIG_PATH)
    yield
    await launcher.shutdown()


app = FastAPI(title="LivingroomOS", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# Nur Loopback-Hostnamen: schützt vor DNS-Rebinding.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.middleware("http")
async def api_guard(request: Request, call_next):
    # Schreibende Aufrufe brauchen einen eigenen Header. Fremde Webseiten können ihn
    # ohne CORS-Freigabe nicht setzen (Preflight scheitert) → Schutz vor CSRF.
    if (
        request.url.path.startswith("/api/")
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.headers.get("x-livingroomos") != "1"
    ):
        return _error(403, "forbidden", "Fehlender Header X-LivingroomOS.")
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"  # Prototyp: immer frische Dateien
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return _error(exc.status_code, f"http_{exc.status_code}", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return _error(422, "invalid_request", f"Ungültige Eingabe ({where}): {first.get('msg', '')}")


@app.exception_handler(SettingsError)
async def settings_error(_: Request, exc: SettingsError):
    return _error(500, "settings_unavailable", str(exc))


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    log.exception("Unerwarteter Fehler")
    return _error(500, "internal_error", "Interner Fehler im Backend.")


app.include_router(system_api.router)
app.include_router(apps_api.router)
app.include_router(settings_api.router)

# Frontend zuletzt einhängen, damit /api/* Vorrang hat.
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    log.warning("Frontend-Ordner fehlt: %s (nur API verfügbar)", FRONTEND_DIR)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("LIVINGROOMOS_PORT", "8750")))
