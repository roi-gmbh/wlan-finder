"""Aufbereitung der Portalseite für das Modell."""

from wlanfinder.portal.snapshot import MAX_TEXT_CHARS, describe_element, render


def test_beschreibung_nennt_kennung_und_beschriftung():
    line = describe_element(
        {"ref": "e3", "tag": "input", "type": "text", "label": "Stellplatznummer", "required": True}
    )
    assert "[e3]" in line and "Stellplatznummer" in line and "Pflichtfeld" in line


def test_zustimmungshaken_wird_markiert():
    line = describe_element(
        {"ref": "e1", "tag": "input", "type": "checkbox", "label": "AGB akzeptieren", "checked": False}
    )
    assert "ZUSTIMMUNG" in line and "nicht angehakt" in line


def test_passwortwerte_tauchen_nicht_auf():
    line = describe_element({"ref": "e9", "tag": "input", "type": "password", "value": "geheim123"})
    assert "geheim123" not in line


def test_langer_text_wird_gekuerzt():
    output = render({"url": "http://x", "title": "t", "text": "a" * (MAX_TEXT_CHARS + 500), "elements": []})
    assert "gekürzt" in output
    assert len(output) < MAX_TEXT_CHARS + 400


def test_seite_ohne_bedienelemente():
    assert "(keine gefunden)" in render({"url": "http://x", "title": "", "text": "nur Text", "elements": []})
