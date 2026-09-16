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
