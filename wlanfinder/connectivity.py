"""Erkennen, ob echtes Internet anliegt oder ein Captive Portal dazwischenhängt.

Das Verfahren ist dasselbe, das Windows und Android selbst benutzen: eine
URL abrufen, deren Antwort exakt bekannt ist. Kommt etwas anderes zurück -
eine Umleitung oder eine fremde Seite -, sitzt ein Portal dazwischen.
"""

from __future__ import annotations

import httpx

from .models import Connectivity

# Erwartete Antworten der Prüf-URLs.
_EXPECTED: dict[str, tuple[int, str | None]] = {
    "http://www.msftconnecttest.com/connecttest.txt": (200, "Microsoft Connect Test"),
    "http://connectivitycheck.gstatic.com/generate_204": (204, None),
    "http://captive.apple.com/hotspot-detect.html": (200, "Success"),
}


def check(urls: list[str], timeout: float = 5.0, local_address: str | None = None) -> Connectivity:
    """Prüft der Reihe nach, bis eine URL eine eindeutige Antwort gibt.

    `local_address` ist hier entscheidend, nicht optional-nice-to-have: Im Bus
    hängt der Laptop bereits per Kabel am LTE-Router. Ohne Bindung an die
    IP-Adresse des WLAN-Adapters lauft die Prüfung über das Kabel, meldet
    brav "online" - und das Captive Portal des Campingplatzes wird nie gesehen.
    """
    last_detail = "keine Prüf-URL erreichbar"
    for url in urls:
        result = _check_one(url, timeout, local_address)
        if result is not None:
            return result
        last_detail = f"{url} nicht erreichbar"
    # Keine der URLs hat geantwortet: dann ist schlicht kein Netz da. Ein Portal
    # würde antworten - es will ja, dass man seine Loginseite sieht.
    return Connectivity(online=False, captive_portal=False, detail=last_detail)


def _check_one(url: str, timeout: float, local_address: str | None) -> Connectivity | None:
    """None heisst: Diese URL konnte nichts aussagen, nächste probieren."""
    expected_status, expected_body = _EXPECTED.get(url, (204, None))
    transport = httpx.HTTPTransport(local_address=local_address) if local_address else None
    try:
        # follow_redirects=False ist der Kern der Sache: Die Umleitung selbst
        # ist das Signal, und ihr Ziel ist die Portalseite.
        with httpx.Client(timeout=timeout, transport=transport, follow_redirects=False) as client:
            response = client.get(url)
    except httpx.HTTPError:
        return None

    if response.is_redirect:
        return Connectivity(
            online=False,
            captive_portal=True,
            portal_url=str(response.headers.get("location") or url),
            checked_url=url,
            detail=f"Umleitung mit Status {response.status_code}",
        )

    body_ok = expected_body is None or expected_body in response.text
    if response.status_code == expected_status and body_ok:
        return Connectivity(online=True, captive_portal=False, checked_url=url, detail="Antwort wie erwartet")

    # Status 200 mit fremdem Inhalt: ein Portal, das ohne Umleitung antwortet.
    return Connectivity(
        online=False,
        captive_portal=True,
        portal_url=url,
        checked_url=url,
        detail=f"unerwartete Antwort (Status {response.status_code})",
    )
