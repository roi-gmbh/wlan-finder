"""Datentypen, die zwischen OS-Schicht, Agent und Weboberfläche wandern."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Security(str, Enum):
    OPEN = "open"
    WEP = "wep"
    WPA_PERSONAL = "wpa-personal"
    WPA_ENTERPRISE = "wpa-enterprise"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Network:
    """Ein am Standort sichtbares WLAN."""

    ssid: str
    signal: int  # 0-100, wie Windows es meldet
    security: Security = Security.UNKNOWN
    known: bool = False  # Windows hat ein gespeichertes Profil dafür
    trusted: bool = False  # in der Konfiguration als vertraut markiert

    @property
    def is_open(self) -> bool:
        return self.security is Security.OPEN

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["security"] = self.security.value
        data["is_open"] = self.is_open
        return data


class LinkKind(str, Enum):
    """Wie der Rechner gerade ins Netz geht."""

    ETHERNET = "ethernet"  # LAN-Kabel, z.B. zum LTE-Router im Bus
    WIFI = "wifi"
    NONE = "none"


@dataclass(frozen=True)
class Connectivity:
    """Ergebnis der Internet-Prüfung."""

    online: bool
    captive_portal: bool
    portal_url: str | None = None
    checked_url: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Verdict(str, Enum):
    """Wie ein Portal-Durchlauf ausgegangen ist."""

    ONLINE = "online"  # Internet steht
    NEEDS_HUMAN = "needs_human"  # Agent stoppt bewusst, z.B. AGB-Haken
    FAILED = "failed"
    DRY_RUN = "dry_run"  # nur protokolliert, nichts geklickt


@dataclass
class PortalResult:
    verdict: Verdict
    reason: str = ""
    steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict.value, "reason": self.reason, "steps": self.steps}
