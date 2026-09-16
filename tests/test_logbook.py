"""Das Logbuch: vier Spalten, dublettenfrei, in Excel lesbar."""

from datetime import datetime

from wlanfinder.logbook import COLUMNS, DELIMITER, ENCODING, OPEN_NETWORK, Logbook


def test_legt_datei_mit_kopfzeile_an(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    book.add("Campingplatz-Gast", "sommer2026", "Seeweg 3, 23570 Lübeck")

    lines = book.path.read_text(encoding=ENCODING).splitlines()
    assert lines[0].split(DELIMITER) == COLUMNS
    assert len(lines) == 2


def test_eintrag_hat_genau_vier_spalten(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    entry = book.add("Netz", "geheim", "Hauptstraße 1")
    assert len(entry.to_row()) == 4


def test_datum_wird_gesetzt(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    entry = book.add("Netz", "x", "Ort", when=datetime(2026, 7, 4, 18, 30))
    assert entry.date == "2026-07-04 18:30"


def test_neueste_zuerst(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    book.add("Erstes", "a", "Ort A", when=datetime(2026, 7, 1, 9, 0))
    book.add("Zweites", "b", "Ort B", when=datetime(2026, 7, 2, 9, 0))
    assert [e.ssid for e in book.entries()] == ["Zweites", "Erstes"]


def test_gleicher_halt_wird_nicht_doppelt_geschrieben(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    assert book.add("Netz", "a", "Seeweg 3", when=datetime(2026, 7, 1, 9, 0)) is not None
    assert book.add("Netz", "a", "Seeweg 3", when=datetime(2026, 7, 1, 17, 0)) is None
    assert len(book.entries()) == 1


def test_gleiches_netz_an_anderem_ort_ist_ein_neuer_eintrag(tmp_path):
    """Ketten wie 'Telekom_FON' heißen überall gleich - der Ort unterscheidet."""
    book = Logbook(tmp_path / "log.csv")
    book.add("Telekom_FON", "a", "Lübeck", when=datetime(2026, 7, 1, 9, 0))
    assert book.add("Telekom_FON", "a", "Kiel", when=datetime(2026, 7, 1, 10, 0)) is not None
    assert len(book.entries()) == 2


def test_gleiches_netz_an_anderem_tag_ist_ein_neuer_eintrag(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    book.add("Netz", "a", "Ort", when=datetime(2026, 7, 1, 9, 0))
    assert book.add("Netz", "a", "Ort", when=datetime(2026, 8, 1, 9, 0)) is not None


def test_offenes_netz_bekommt_platzhalter_statt_leerer_zelle(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    entry = book.add("Gast", OPEN_NETWORK, "Ort")
    assert entry.password == OPEN_NETWORK


def test_semikolon_und_umlaute_im_wert_zerlegen_die_datei_nicht(tmp_path):
    """Adressen enthalten Kommas, Passwörter können alles enthalten."""
    book = Logbook(tmp_path / "log.csv")
    book.add('Café "Süd"', "pass;wort", "Straße 1; 12345 Köln")

    entries = book.entries()
    assert len(entries) == 1
    assert entries[0].ssid == 'Café "Süd"'
    assert entries[0].password == "pass;wort"
    assert entries[0].address == "Straße 1; 12345 Köln"


def test_leeres_logbuch_ist_kein_fehler(tmp_path):
    assert Logbook(tmp_path / "gibtsnicht.csv").entries() == []


# -- Suchlauf protokollieren -------------------------------------------------

from wlanfinder.logbook import NOT_CONNECTED


def test_suchlauf_schreibt_alle_gefundenen_netze(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    gefunden = [("Campingplatz-Gast", NOT_CONNECTED), ("Stellplatz-WLAN", NOT_CONNECTED)]

    book.add_many(gefunden, "Seeweg 3, 23570 Lübeck")

    assert {e.ssid for e in book.entries()} == {"Campingplatz-Gast", "Stellplatz-WLAN"}
    assert all(e.password == NOT_CONNECTED for e in book.entries())


def test_zweiter_suchlauf_am_selben_ort_verdoppelt_nichts(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    gefunden = [("Gast", NOT_CONNECTED), ("Privat", NOT_CONNECTED)]

    book.add_many(gefunden, "Seeweg 3", when=datetime(2026, 7, 1, 9, 0))
    neu = book.add_many(gefunden, "Seeweg 3", when=datetime(2026, 7, 1, 9, 30))

    assert neu == []
    assert len(book.entries()) == 2


def test_spaetere_verbindung_ergaenzt_die_vorhandene_zeile(tmp_path):
    """Der wichtigste Fall: Das Netz stand vom Suchlauf schon da. Jetzt ist das
    Passwort bekannt - es gehört in dieselbe Zeile, nicht in eine zweite."""
    book = Logbook(tmp_path / "log.csv")
    book.add_many([("Gast", NOT_CONNECTED)], "Seeweg 3", when=datetime(2026, 7, 1, 9, 0))

    ergaenzt = book.add("Gast", "sommer2026", "Seeweg 3", when=datetime(2026, 7, 1, 14, 0))

    assert ergaenzt is not None
    assert len(book.entries()) == 1
    eintrag = book.entries()[0]
    assert eintrag.password == "sommer2026"
    # Das Datum bleibt das der ersten Sichtung.
    assert eintrag.date == "2026-07-01 09:00"


def test_ein_echtes_passwort_wird_nicht_wieder_ueberschrieben(tmp_path):
    """Ein späterer Suchlauf darf das gemerkte Passwort nicht plattmachen."""
    book = Logbook(tmp_path / "log.csv")
    book.add("Gast", "sommer2026", "Seeweg 3", when=datetime(2026, 7, 1, 9, 0))

    assert book.add_many([("Gast", NOT_CONNECTED)], "Seeweg 3", when=datetime(2026, 7, 1, 18, 0)) == []
    assert book.entries()[0].password == "sommer2026"


def test_offenes_netz_verdraengt_den_platzhalter(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    book.add_many([("Gast", NOT_CONNECTED)], "Seeweg 3", when=datetime(2026, 7, 1, 9, 0))

    book.add("Gast", OPEN_NETWORK, "Seeweg 3", when=datetime(2026, 7, 1, 10, 0))

    assert book.entries()[0].password == OPEN_NETWORK


def test_gleiches_netz_an_zwei_orten_bleibt_getrennt(tmp_path):
    book = Logbook(tmp_path / "log.csv")
    book.add_many([("Telekom_FON", NOT_CONNECTED)], "Lübeck", when=datetime(2026, 7, 1, 9, 0))
    book.add_many([("Telekom_FON", NOT_CONNECTED)], "Kiel", when=datetime(2026, 7, 1, 15, 0))

    assert len(book.entries()) == 2
