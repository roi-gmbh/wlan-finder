"""Zusammenspiel der Teile: scannen, bewerten, verbinden, Portal lösen.

Hält den Zustand, den die Weboberfläche anzeigt. Bewusst ohne KI - hier
laufen nur feste Abläufe zusammen.
"""

from __future__ import annotations

import threading
from typing import Any

from . import connectivity
from .config import Config
from .models import Connectivity, LinkKind, Network, PortalResult, Verdict
from .offer import build_offers
from .wifi import WifiBackend, WifiError


class PortalJob:
    """Ein laufender oder abgeschlossener Portal-Durchlauf."""

    def __init__(self) -> None:
        self.running = False
        self.result: PortalResult | None = None
        self.steps: list[str] = []
        self.error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "result": self.result.to_dict() if self.result else None,
            "steps": self.steps,
            "error": self.error,
        }


class Service:
    def __init__(self, config: Config, backend: WifiBackend) -> None:
        self.config = config
        self.backend = backend
        self._lock = threading.Lock()
        self.networks: list[Network] = []
        self.link: LinkKind = LinkKind.NONE
        self.current_ssid: str | None = None
        self.connectivity: Connectivity | None = None
        self.portal_job = PortalJob()
        self.last_error: str | None = None

    # -- Zustand ------------------------------------------------------------

    def refresh(self) -> dict[str, Any]:
        """Neu scannen und Internet-Lage prüfen."""
        with self._lock:
            self.last_error = None
            try:
                self.link, self.current_ssid = self.backend.current_link()
                self.networks = self.backend.scan()
            except WifiError as exc:
                self.last_error = str(exc)
                self.networks = []

            # Der springende Punkt im Bus: Es liegt bereits Internet über
            # Kabel/LTE an. Würde hier ohne Bindung geprüft, meldete jede
            # Prüfung "online" und das Portal bliebe unsichtbar. Deshalb wird
            # die Prüfung an die IP des WLAN-Adapters gebunden.
            wlan_ip = None
            try:
                wlan_ip = self.backend.wlan_ipv4()
            except WifiError:
                pass
            if self.link is LinkKind.WIFI or wlan_ip:
                self.connectivity = connectivity.check(
                    self.config.portal.check_urls,
                    self.config.portal.timeout_seconds,
                    local_address=wlan_ip,
                )
            else:
                self.connectivity = None
        return self.state()

    def state(self) -> dict[str, Any]:
        offers = build_offers(self.networks, self.link, self.current_ssid, self.config.trusted_ssids)
        return {
            "link": self.link.value,
            "current_ssid": self.current_ssid,
            "networks": [n.to_dict() for n in self.networks],
            "offers": [o.to_dict() for o in offers],
            "connectivity": self.connectivity.to_dict() if self.connectivity else None,
            "portal_job": self.portal_job.to_dict(),
            "safety": {
                "dry_run": self.config.safety.dry_run,
                "accept_terms": self.config.safety.accept_terms,
                "max_agent_steps": self.config.safety.max_agent_steps,
            },
            "error": self.last_error,
        }

    # -- Aktionen -----------------------------------------------------------

    def connect(self, ssid: str, passphrase: str | None = None) -> dict[str, Any]:
        """Verbindet auf ausdrückliche Anweisung aus der Oberfläche.

        Es gibt bewusst keinen Pfad, der das von selbst tut.
        """
        try:
            self.backend.connect(ssid, passphrase)
        except WifiError as exc:
            self.last_error = str(exc)
            return self.state()
        return self.refresh()

    def start_portal_login(self, hints: dict[str, str] | None = None) -> dict[str, Any]:
        """Startet den Agenten auf der erkannten Portalseite - im Hintergrund,
        damit die Oberfläche währenddessen bedienbar bleibt."""
        if self.portal_job.running:
            return self.state()
        if not (self.connectivity and self.connectivity.captive_portal):
            self.last_error = "Es wurde kein Captive Portal erkannt."
            return self.state()

        self.portal_job = PortalJob()
        self.portal_job.running = True
        url = self.connectivity.portal_url or self.config.portal.check_urls[0]

        thread = threading.Thread(
            target=self._run_portal, args=(url, hints or {}), name="portal-agent", daemon=True
        )
        thread.start()
        return self.state()

    def _run_portal(self, url: str, hints: dict[str, str]) -> None:
        # Läuft in einem eigenen Thread: Playwright in der synchronen Variante
        # verträgt sich nicht mit einer laufenden asyncio-Schleife.
        from .portal import agent as portal_agent
        from .portal.browser import PortalBrowser

        job = self.portal_job
        try:
            with PortalBrowser(headful=self.config.portal.headful) as browser:
                job.result = portal_agent.run(
                    browser,
                    start_url=url,
                    hints=hints,
                    dry_run=self.config.safety.dry_run,
                    accept_terms=self.config.safety.accept_terms,
                    max_steps=self.config.safety.max_agent_steps,
                    model=self.config.agent.model,
                    max_tokens=self.config.agent.max_tokens,
                )
                job.steps = job.result.steps
        except Exception as exc:  # noqa: BLE001 - jede Störung gehört in die Oberfläche
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            job.running = False

        # Nach echten (nicht simulierten) Klicks nachsehen, ob es gewirkt hat.
        if job.result and job.result.verdict is not Verdict.DRY_RUN:
            self.refresh()
