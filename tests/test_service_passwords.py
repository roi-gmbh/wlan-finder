"""Passwörter, die schon vorliegen, sollen nicht erneut abgefragt werden.

Zwei Quellen, beide die eigenen: das in Windows gespeicherte Profil und das
Logbuch vom letzten Besuch. Reine Nachschlagearbeit - kein Sprachmodell.
"""

import pytest

from wlanfinder.config import Config
from wlanfinder.logbook import NOT_CONNECTED, OPEN_NETWORK
from wlanfinder.models import LinkKind, Network, Security
from wlanfinder.service import Service
from wlanfinder.wifi import FakeBackend

ADRESSE = "Seeweg 3, 23570 Lübeck"


@pytest.fixture
def service(tmp_path):
    config = Config()
    config.logbook.path = str(tmp_path / "log.csv")
    return Service(config, FakeBackend())


def row_for(service, ssid):
    return next(row for row in service.state()["rows"] if row["network"]["ssid"] == ssid)


def test_gespeichertes_windows_profil_wird_gefunden(service):
    service.refresh()
    # FRITZ!Box 7590 ist im Fake-Backend ein bekanntes Profil.
    assert service.known_passwords["FRITZ!Box 7590"] == "gespeichert123"
    assert row_for(service, "FRITZ!Box 7590")["has_password"] is True
    assert row_for(service, "FRITZ!Box 7590")["needs_passphrase"] is False


def test_passwort_aus_dem_logbuch_vom_letzten_besuch(service):
    """Der eigentliche Zweck des Logbuchs: Beim zweiten Besuch reicht ein Klick."""
    service.logbook.add("Stellplatz-WLAN", "sonne2026", "Irgendwo von letztem Jahr")
    service.refresh()

    assert service.known_passwords["Stellplatz-WLAN"] == "sonne2026"
    assert row_for(service, "Stellplatz-WLAN")["has_password"] is True


def test_verbinden_nutzt_das_bekannte_passwort_ohne_nachfrage(service):
    service.logbook.add("Stellplatz-WLAN", "sonne2026", "Letztes Jahr")
    service.refresh()

    service.connect("Stellplatz-WLAN", None, ADRESSE)

    assert ("Stellplatz-WLAN", "sonne2026") in service.backend.connect_calls


def test_eingetipptes_passwort_hat_vorrang(service):
    service.logbook.add("Stellplatz-WLAN", "altesPasswort", "Letztes Jahr")
    service.refresh()

    service.connect("Stellplatz-WLAN", "neuesPasswort", ADRESSE)

    assert ("Stellplatz-WLAN", "neuesPasswort") in service.backend.connect_calls


def test_platzhalter_gelten_nicht_als_passwort(service):
    """(nicht verbunden) und (offenes Netz) sind keine Passwörter."""
    service.logbook.add("Campingplatz-Gast", OPEN_NETWORK, "Ort A")
    service.logbook.add("Stellplatz-WLAN", NOT_CONNECTED, "Ort B")
    service.refresh()

    assert "Campingplatz-Gast" not in service.known_passwords
    assert "Stellplatz-WLAN" not in service.known_passwords


def test_offenes_netz_wird_ohne_passwort_verbunden(service):
    service.refresh()
    service.connect("Campingplatz-Gast", None, ADRESSE)

    assert ("Campingplatz-Gast", None) in service.backend.connect_calls


def test_windows_profil_sticht_einen_alten_logbucheintrag(service):
    """Wurde das Passwort am Platz geändert, ist das Profil der neuere Stand."""
    service.logbook.add("FRITZ!Box 7590", "vorletztesJahr", "Ort")
    service.refresh()

    assert service.known_passwords["FRITZ!Box 7590"] == "gespeichert123"


def test_unbekanntes_netz_verlangt_weiter_eine_eingabe(service):
    service.refresh()
    zeile = row_for(service, "Stellplatz-WLAN")
    assert zeile["has_password"] is False
    assert zeile["needs_passphrase"] is True
