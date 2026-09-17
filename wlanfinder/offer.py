"""Bewertung der gefundenen Netze.

Bewusst ohne KI - das sind feste Regeln, die jeder nachlesen und ändern kann.
WLAN Finder wechselt nie selbst; das Ergebnis ist nur die Frage, die in der
Oberfläche erscheint.

Wichtig für die Anzeige: Es werden **alle** gefundenen Netze zurückgegeben,
jedes mit der Angabe, ob ein Wechsel dorthin sinnvoll ist und warum nicht.
Sonst sieht eine leere Liste wie ein kaputter Scan aus, obwohl bloß alles
herausgefiltert wurde.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import LinkKind, Network, Security

# Unter diesem Signal lohnt sich der Wechsel erfahrungsgemäß nicht. Schwache
# Netze sind auf einem Stellplatz aber oft alles, was da ist - deshalb niedrig
# angesetzt und über config.toml änderbar ([networks] min_signal).
MIN_SIGNAL = 15


@dataclass(frozen=True)
class Row:
    """Ein gefundenes Netz samt Bewertung."""

    network: Network
    offered: bool
    reason: str
    needs_passphrase: bool = False
    needs_portal_login: bool = False
    connectable: bool = True

    def to_dict(self) -> dict:
        return {
            "network": self.network.to_dict(),
            "offered": self.offered,
            "reason": self.reason,
            "needs_passphrase": self.needs_passphrase,
            "needs_portal_login": self.needs_portal_login,
            "connectable": self.connectable,
        }


# Der Name Offer bleibt als Synonym erhalten: Ein angebotenes Netz ist eine
# Zeile mit offered=True.
Offer = Row


def build_rows(
    networks: list[Network],
    link: LinkKind,
    current_ssid: str | None,
    trusted_ssids: frozenset[str] = frozenset(),
    min_signal: int = MIN_SIGNAL,
) -> list[Row]:
    """Alle gefundenen Netze, bewertet und sortiert."""
    rows: list[Row] = []
    for net in networks:
        trusted = net.trusted or net.ssid in trusted_ssids

        if net.ssid == current_ssid:
            rows.append(Row(net, False, "aktuell verbunden", connectable=False))
            continue
        if net.security is Security.WPA_ENTERPRISE:
            # Firmennetze mit Nutzerkonto können wir nicht bedienen.
            rows.append(
                Row(net, False, "Firmennetz mit Nutzerkonto - wird nicht unterstützt", connectable=False)
            )
            continue
        if net.signal < min_signal:
            rows.append(
                Row(
                    net,
                    False,
                    f"Signal zu schwach ({net.signal} %) - unter {min_signal} % ist kaum etwas zu erwarten",
                    needs_passphrase=not net.is_open and not net.known,
                    needs_portal_login=net.is_open,
                )
            )
            continue

        rows.append(
            Row(
                net,
                True,
                _reason(net, link, trusted),
                # Bekannte Profile bringen ihr Passwort schon mit.
                needs_passphrase=not net.is_open and not net.known,
                # Offene Netze sind fast immer die mit Portal.
                needs_portal_login=net.is_open,
            )
        )

    # Angebotene zuerst, darin Bekanntes und Vertrautes, dann nach Signal.
    return sorted(
        rows,
        key=lambda row: (
            row.offered,
            row.network.known or row.network.ssid in trusted_ssids,
            row.network.signal,
        ),
        reverse=True,
    )


def build_offers(
    networks: list[Network],
    link: LinkKind,
    current_ssid: str | None,
    trusted_ssids: frozenset[str] = frozenset(),
    min_signal: int = MIN_SIGNAL,
) -> list[Row]:
    """Nur die Netze, die einen Wechsel wert sind."""
    rows = build_rows(networks, link, current_ssid, trusted_ssids, min_signal)
    return [row for row in rows if row.offered]


def _reason(net: Network, link: LinkKind, trusted: bool) -> str:
    if net.signal < 40:
        # Ehrlich benennen: Verbinden kann man, verlassen sollte man sich nicht.
        return f"schwaches Signal ({net.signal} %) - Versuch lohnt, stabil wird es kaum"
    if trusted:
        return "als vertraut markiert"
    if net.known:
        return "schon einmal benutzt"
    if link is LinkKind.ETHERNET:
        return "zusätzlich zum Kabel verfügbar - spart Mobilfunk-Datenvolumen"
    if net.is_open:
        return "offenes Netz, vermutlich mit Anmeldeseite"
    return "verschlüsselt, Passwort nötig"
