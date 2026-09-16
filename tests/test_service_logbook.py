"""Zusammenspiel von Suche, Verbindung und Logbuch.

Der Ablauf, den diese Tests absichern, ist der im Bus übliche: ankommen,
suchen, sehen was da ist, eines der Netze nehmen. Am Ende soll pro Netz
genau eine Zeile stehen - und bei dem benutzten Netz das Passwort.
"""

import pytest

from wlanfinder.config import Config
from wlanfinder.logbook import NOT_CONNECTED
from wlanfinder.service import Service
from wlanfinder.wifi import FakeBackend

ADRESSE = "Seeweg 3, 23570 Lübeck"


@pytest.fixture
def service(tmp_path):
    config = Config()
    config.logbook.path = str(tmp_path / "log.csv")
    return Service(config, FakeBackend())


def rows(service):
    return service.state()["logbook"]


def test_ohne_standort_wird_nichts_protokolliert(service):
    service.refresh()
    assert rows(service) == []
    assert service.state()["logbook_needs_address"] is True


def test_suche_protokolliert_alle_sichtbaren_netze(service):
    service.set_address(ADRESSE)
    service.refresh()

    protokolliert = {row["ssid"] for row in rows(service)}
    sichtbar = {network.ssid for network in service.networks}
    assert protokolliert == sichtbar
    assert service.state()["logbook_needs_address"] is False


def test_standort_nachtragen_protokolliert_die_schon_gefundenen_netze(service):
    """Wer erst sucht und dann die Adresse einträgt, soll nicht erneut suchen
    müssen."""
    service.refresh()
    assert rows(service) == []

    service.set_address(ADRESSE)

    assert len(rows(service)) == len(service.networks)


def test_wiederholte_suche_verdoppelt_nichts(service):
    service.set_address(ADRESSE)
    service.refresh()
    vorher = len(rows(service))

    service.refresh()
    service.refresh()

    assert len(rows(service)) == vorher


def test_verbinden_ergaenzt_das_passwort_in_der_vorhandenen_zeile(service):
    service.set_address(ADRESSE)
    service.refresh()
    vorher = len(rows(service))

    service.connect("Stellplatz-WLAN", "sonne2026", ADRESSE)

    assert len(rows(service)) == vorher  # keine zweite Zeile
    eintrag = next(row for row in rows(service) if row["ssid"] == "Stellplatz-WLAN")
    assert eintrag["password"] == "sonne2026"


def test_das_verbundene_netz_steht_nicht_als_nicht_verbunden_da(service):
    """Nach dem Verbinden läuft ein neuer Suchlauf - der darf das Netz, an dem
    wir gerade hängen, nicht wieder als 'nicht verbunden' markieren."""
    service.set_address(ADRESSE)
    service.connect("Campingplatz-Gast", None, ADRESSE)

    eintrag = next(row for row in rows(service) if row["ssid"] == "Campingplatz-Gast")
    assert eintrag["password"] != NOT_CONNECTED


def test_abgeschaltetes_logbuch_schreibt_nichts(service):
    service.config.logbook.enabled = False
    service.set_address(ADRESSE)
    service.refresh()
    service.connect("Stellplatz-WLAN", "sonne2026", ADRESSE)

    assert rows(service) == []
