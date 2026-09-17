"""Welche Netze überhaupt angeboten werden."""

from wlanfinder.models import LinkKind, Network, Security
from wlanfinder.offer import MIN_SIGNAL, build_offers


def net(ssid, signal=80, security=Security.OPEN, known=False):
    return Network(ssid, signal, security, known=known)


def test_schwache_netze_fallen_raus():
    offers = build_offers([net("Schwach", MIN_SIGNAL - 1)], LinkKind.ETHERNET, None)
    assert offers == []


def test_firmennetze_fallen_raus():
    offers = build_offers([net("Firma", 90, Security.WPA_ENTERPRISE)], LinkKind.ETHERNET, None)
    assert offers == []


def test_aktuelles_netz_wird_nicht_angeboten():
    offers = build_offers([net("Hier")], LinkKind.WIFI, "Hier")
    assert offers == []


def test_bekanntes_netz_steht_vor_staerkerem_unbekanntem():
    offers = build_offers(
        [net("Unbekannt", 95), net("Bekannt", 55, known=True)], LinkKind.ETHERNET, None
    )
    assert [o.network.ssid for o in offers] == ["Bekannt", "Unbekannt"]


def test_vertraute_ssid_aus_der_konfiguration_zaehlt():
    offers = build_offers([net("Stammplatz", 60)], LinkKind.ETHERNET, None, frozenset({"Stammplatz"}))
    assert offers[0].reason == "als vertraut markiert"


def test_offenes_netz_erwartet_anmeldeseite():
    offer = build_offers([net("Gast")], LinkKind.ETHERNET, None)[0]
    assert offer.needs_portal_login
    assert not offer.needs_passphrase


def test_verschluesseltes_unbekanntes_netz_braucht_passwort():
    offer = build_offers([net("Privat", 80, Security.WPA_PERSONAL)], LinkKind.ETHERNET, None)[0]
    assert offer.needs_passphrase


def test_bekanntes_verschluesseltes_netz_braucht_kein_passwort():
    """Windows hat das Passwort im Profil schon gespeichert."""
    offer = build_offers(
        [net("Privat", 80, Security.WPA_PERSONAL, known=True)], LinkKind.ETHERNET, None
    )[0]
    assert not offer.needs_passphrase


# -- Schwelle ---------------------------------------------------------------


def test_schwache_netze_ab_der_schwelle_werden_angeboten():
    """15 % ist die Voreinstellung: Auf einem Stellplatz ist ein schwaches
    Netz oft alles, was da ist."""
    offers = build_offers([net("Schwach", 20)], LinkKind.ETHERNET, None)
    assert [o.network.ssid for o in offers] == ["Schwach"]
    assert "schwaches Signal" in offers[0].reason


def test_eigene_schwelle_aus_der_konfiguration():
    netze = [net("Mittel", 50), net("Schwach", 20)]
    offers = build_offers(netze, LinkKind.ETHERNET, None, min_signal=40)
    assert [o.network.ssid for o in offers] == ["Mittel"]


def test_alle_netze_erscheinen_auch_die_nicht_angebotenen():
    """Eine gefilterte Liste darf nicht wie ein fehlgeschlagener Scan aussehen."""
    from wlanfinder.offer import build_rows

    netze = [net("Gut", 80), net("Winzig", 5), net("Firma", 90, Security.WPA_ENTERPRISE)]
    rows = build_rows(netze, LinkKind.ETHERNET, "Gut")

    assert len(rows) == 3
    nach_ssid = {row.network.ssid: row for row in rows}
    assert nach_ssid["Gut"].reason == "aktuell verbunden"
    assert not nach_ssid["Gut"].connectable
    assert "zu schwach" in nach_ssid["Winzig"].reason
    assert "Firmennetz" in nach_ssid["Firma"].reason
    assert not nach_ssid["Firma"].connectable
