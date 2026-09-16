"""Schnittstelle zur WLAN-Hardware.

Die eigentliche Windows-Umsetzung steht in netsh.py. Diese Datei definiert nur,
was ein Backend können muss, plus ein Fake-Backend für Tests und für die
Entwicklung auf Nicht-Windows-Rechnern.
"""

from __future__ import annotations

from typing import Protocol

from .models import LinkKind, Network, Security


class WifiBackend(Protocol):
    """Alles, was WLAN Finder vom Betriebssystem braucht."""

    def scan(self) -> list[Network]:
        """Sichtbare WLANs am Standort, stärkstes Signal zuerst."""
        ...

    def known_profiles(self) -> set[str]:
        """SSIDs, für die das System ein gespeichertes Profil hat."""
        ...

    def current_link(self) -> tuple[LinkKind, str | None]:
        """Wie der Rechner gerade hängt und - bei WLAN - an welcher SSID."""
        ...

    def connect(self, ssid: str, passphrase: str | None = None) -> None:
        """Mit einem WLAN verbinden. Wirft WifiError, wenn es nicht klappt."""
        ...

    def wlan_ipv4(self) -> str | None:
        """IP-Adresse des WLAN-Adapters, oder None wenn keine anliegt."""
        ...


class WifiError(RuntimeError):
    """Der Verbindungs- oder Scanbefehl des Betriebssystems ist fehlgeschlagen."""


class FakeBackend:
    """Backend ohne Hardware - für Tests und zum Ausprobieren der Oberfläche
    auf einem Rechner ohne Windows."""

    def __init__(
        self,
        networks: list[Network] | None = None,
        link: tuple[LinkKind, str | None] = (LinkKind.ETHERNET, None),
    ) -> None:
        self._networks = networks if networks is not None else _demo_networks()
        self._link = link
        self.connect_calls: list[tuple[str, str | None]] = []

    def scan(self) -> list[Network]:
        return sorted(self._networks, key=lambda n: n.signal, reverse=True)

    def known_profiles(self) -> set[str]:
        return {n.ssid for n in self._networks if n.known}

    def current_link(self) -> tuple[LinkKind, str | None]:
        return self._link

    def connect(self, ssid: str, passphrase: str | None = None) -> None:
        if ssid not in {n.ssid for n in self._networks}:
            raise WifiError(f"SSID {ssid!r} ist nicht in Reichweite")
        self.connect_calls.append((ssid, passphrase))
        self._link = (LinkKind.WIFI, ssid)

    def wlan_ipv4(self) -> str | None:
        return "192.0.2.10" if self._link[0] is LinkKind.WIFI else None


def _demo_networks() -> list[Network]:
    return [
        Network("Campingplatz-Gast", 82, Security.OPEN),
        Network("Stellplatz-WLAN", 61, Security.WPA_PERSONAL),
        Network("FRITZ!Box 7590", 45, Security.WPA_PERSONAL, known=True),
        Network("Telekom_FON", 30, Security.OPEN),
    ]
