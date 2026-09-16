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
