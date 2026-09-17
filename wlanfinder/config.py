"""Konfiguration laden - aus config.toml, mit den Werten aus config.example.toml
als Voreinstellung."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GeneralConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    scan_interval_seconds: int = 60


@dataclass
class SafetyConfig:
    accept_terms: bool = False
    dry_run: bool = True
    max_agent_steps: int = 20


@dataclass
class PortalConfig:
    check_urls: list[str] = field(
        default_factory=lambda: [
            "http://www.msftconnecttest.com/connecttest.txt",
            "http://connectivitycheck.gstatic.com/generate_204",
        ]
    )
    timeout_seconds: float = 5.0
    headful: bool = True


@dataclass
class AgentConfig:
    model: str = "claude-opus-5"
    max_tokens: int = 16000

    @property
    def api_key(self) -> str | None:
        """Der Key kommt aus der Umgebung, nie aus der Konfigurationsdatei."""
        return os.environ.get("ANTHROPIC_API_KEY")


@dataclass
class LogbookConfig:
    # Relativ zur config.toml bzw. zum Arbeitsverzeichnis.
    path: str = "wlan-logbuch.csv"
    enabled: bool = True


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    portal: PortalConfig = field(default_factory=PortalConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    logbook: LogbookConfig = field(default_factory=LogbookConfig)
    trusted_ssids: frozenset[str] = frozenset()
    # Ab welcher Signalstärke ein Netz überhaupt angeboten wird.
    min_signal: int = 15

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Liest config.toml, falls vorhanden. Fehlt sie, gelten die Voreinstellungen."""
        cfg = cls()
        if path is None:
            path = Path.cwd() / "config.toml"
        if not path.exists():
            return cfg

        with path.open("rb") as fh:
            raw: dict[str, Any] = tomllib.load(fh)

        cfg.general = _fill(GeneralConfig, raw.get("general", {}))
        cfg.safety = _fill(SafetyConfig, raw.get("safety", {}))
        cfg.portal = _fill(PortalConfig, raw.get("portal", {}))
        cfg.agent = _fill(AgentConfig, raw.get("agent", {}))
        cfg.logbook = _fill(LogbookConfig, raw.get("logbook", {}))

        networks = raw.get("networks", {})
        cfg.min_signal = int(networks.get("min_signal", cfg.min_signal))
        known = networks.get("known", [])
        cfg.trusted_ssids = frozenset(
            entry["ssid"] for entry in known if entry.get("trusted") and entry.get("ssid")
        )
        return cfg


def _fill(cls: type, values: dict[str, Any]):
    """Baut eine Dataclass aus einem TOML-Abschnitt und ignoriert unbekannte Schlüssel,
    damit eine neuere Konfigurationsdatei eine ältere Version nicht zum Absturz bringt."""
    known_fields = {f for f in cls.__dataclass_fields__}
    return cls(**{k: v for k, v in values.items() if k in known_fields})
