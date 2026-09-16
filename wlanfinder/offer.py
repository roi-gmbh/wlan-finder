"""Entscheidungslogik: Lohnt es sich überhaupt, einen Wechsel anzubieten?

Bewusst ohne KI - das sind feste Regeln, die jeder nachlesen und ändern kann.
WLAN Finder wechselt nie selbst; das Ergebnis dieser Funktion ist nur die
Frage, die in der Oberfläche erscheint.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import LinkKind, Network, Security

# Unter diesem Signal lohnt sich der Wechsel erfahrungsgemäß nicht.
MIN_SIGNAL = 40


@dataclass(frozen=True)
class Offer:
    network: Network
    reason: str
    needs_passphrase: bool
    needs_portal_login: bool

    def to_dict(self) -> dict:
        return {
            "network": self.network.to_dict(),
            "reason": self.reason,
            "needs_passphrase": self.needs_passphrase,
            "needs_portal_login": self.needs_portal_login,
        }


def build_offers(
    networks: list[Network],
    link: LinkKind,
    current_ssid: str | None,
    trusted_ssids: frozenset[str] = frozenset(),
) -> list[Offer]:
    """Sortierte Liste der Netze, die einen Wechsel wert sind."""
    offers: list[Offer] = []
    for net in networks:
        if net.ssid == current_ssid:
            continue  # damit hängen wir schon
        if net.signal < MIN_SIGNAL:
            continue
        if net.security is Security.WPA_ENTERPRISE:
            # Firmennetze mit Nutzerkonto können wir nicht bedienen.
            continue

        trusted = net.trusted or net.ssid in trusted_ssids
        offers.append(
            Offer(
                network=net,
                reason=_reason(net, link, trusted),
                # Bekannte Profile bringen ihr Passwort schon mit.
                needs_passphrase=not net.is_open and not net.known,
                # Offene Netze sind fast immer die mit Portal.
                needs_portal_login=net.is_open,
            )
        )

    # Bekanntes und vertrautes zuerst, dann nach Signal.
    return sorted(
        offers,
        key=lambda o: (
            o.network.known or o.network.ssid in trusted_ssids,
            o.network.signal,
        ),
        reverse=True,
    )


def _reason(net: Network, link: LinkKind, trusted: bool) -> str:
    if trusted:
        return "als vertraut markiert"
    if net.known:
        return "schon einmal benutzt"
    if link is LinkKind.ETHERNET:
        return "zusätzlich zum Kabel verfügbar - spart Mobilfunk-Datenvolumen"
    if net.is_open:
        return "offenes Netz, vermutlich mit Anmeldeseite"
    return "verschlüsselt, Passwort nötig"
