"""Lokale Weboberfläche.

Warum überhaupt ein Server: Ein reines Browser-Programm kann keine WLANs
scannen - dafür braucht es Zugriff aufs Betriebssystem. Also läuft hier ein
kleiner Dienst auf dem Laptop, der genau das tut, und der Browser ist nur die
Bedienoberfläche dafür.

Der Server hört absichtlich nur auf 127.0.0.1 - er ist vom Netz aus nicht
erreichbar und hat deshalb keine Anmeldung.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import Config
from .service import Service

_INDEX = Path(__file__).parent / "web" / "index.html"


class ConnectRequest(BaseModel):
    ssid: str
    passphrase: str | None = None


class PortalRequest(BaseModel):
    # Angaben, die der Agent in Formularfelder eintragen darf - z.B.
    # {"Stellplatznummer": "42", "Nachname": "Overkamp"}.
    hints: dict[str, str] = {}


def create_app(service: Service) -> FastAPI:
    app = FastAPI(title="WLAN Finder", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX.read_text(encoding="utf-8")

    @app.get("/api/state")
    def get_state() -> dict:
        return service.state()

    @app.post("/api/refresh")
    def refresh() -> dict:
        return service.refresh()

    @app.post("/api/connect")
    def connect(request: ConnectRequest) -> dict:
        return service.connect(request.ssid, request.passphrase)

    @app.post("/api/portal")
    def portal(request: PortalRequest) -> dict:
        return service.start_portal_login(request.hints)

    return app


def run(config: Config | None = None, backend=None) -> None:
    import uvicorn

    from .wifi import FakeBackend

    config = config or Config.load()
    if backend is None:
        backend = _default_backend()
    service = Service(config, backend)
    if isinstance(backend, FakeBackend):
        print("Hinweis: kein Windows erkannt - WLAN Finder läuft mit Beispieldaten.")
    print(f"WLAN Finder läuft auf http://{config.general.host}:{config.general.port}")
    uvicorn.run(create_app(service), host=config.general.host, port=config.general.port, log_level="warning")


def _default_backend():
    """Auf Windows die echte Hardware, sonst Beispieldaten."""
    import sys

    if sys.platform == "win32":
        from .netsh import NetshBackend

        return NetshBackend()
    from .wifi import FakeBackend

    return FakeBackend()
