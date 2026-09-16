"""Die Sperren des Portal-Agenten.

Diese Tests sind der Kern der Sicherheitszusage des Projekts: Der Agent darf
nicht in fremdem Namen AGB zustimmen, und im Trockenlauf darf er die Seite
nicht anfassen. Beides liegt absichtlich im Code und nicht nur im Prompt -
ein Prompt lässt sich von der Portalseite überreden, eine if-Abfrage nicht.
"""

import pytest

from wlanfinder.models import Verdict
from wlanfinder.portal.agent import _Session, build_tools
from wlanfinder.portal.snapshot import is_consent_element


class FakeBrowser:
    """Merkt sich, was mit der Seite passiert wäre."""

    def __init__(self, elements=None):
        self.elements = elements or []
        self.actions = []

    def state(self):
        return {"url": "http://portal.test/", "title": "Gast", "text": "Willkommen", "elements": self.elements}

    def fill(self, ref, text):
        self.actions.append(("fill", ref, text))

    def click(self, ref):
        self.actions.append(("click", ref))

    def check(self, ref, checked):
        self.actions.append(("check", ref, checked))

    def select(self, ref, value):
        self.actions.append(("select", ref, value))


AGB_CHECKBOX = {"ref": "e1", "tag": "input", "type": "checkbox", "label": "Ich akzeptiere die AGB", "checked": False}
NEWSLETTER_CHECKBOX = {"ref": "e2", "tag": "input", "type": "checkbox", "label": "Newsletter abonnieren", "checked": False}


def tools_for(browser, **kwargs):
    options = {"dry_run": False, "accept_terms": False, "max_steps": 20}
    options.update(kwargs)
    session = _Session(browser, **options)
    return session, {tool.name: tool for tool in build_tools(session)}


def test_erkennt_zustimmungshaken():
    assert is_consent_element(AGB_CHECKBOX)
    assert not is_consent_element(NEWSLETTER_CHECKBOX)
    assert not is_consent_element({"type": "text", "label": "AGB-Nummer"})


def test_agb_haken_wird_verweigert():
    browser = FakeBrowser([AGB_CHECKBOX])
    session, tools = tools_for(browser)
    tools["look"]()  # damit der Agent die Elemente kennt

    answer = tools["check"]("e1", True)

    assert "ABGELEHNT" in answer
    assert session.verdict is Verdict.NEEDS_HUMAN
    # Entscheidend: Die Seite wurde nicht angefasst.
    assert ("check", "e1", True) not in browser.actions


def test_agb_haken_ist_erlaubt_wenn_der_nutzer_es_freigibt():
    browser = FakeBrowser([AGB_CHECKBOX])
    session, tools = tools_for(browser, accept_terms=True)
    tools["look"]()

    tools["check"]("e1", True)

    assert ("check", "e1", True) in browser.actions
    assert session.verdict is None


def test_harmloser_haken_bleibt_erlaubt():
    browser = FakeBrowser([NEWSLETTER_CHECKBOX])
    _, tools = tools_for(browser)
    tools["look"]()

    tools["check"]("e2", True)

    assert ("check", "e2", True) in browser.actions


def test_haken_entfernen_ist_immer_erlaubt():
    """Einen Haken wegzunehmen ist keine Willenserklärung."""
    browser = FakeBrowser([AGB_CHECKBOX])
    session, tools = tools_for(browser)
    tools["look"]()

    tools["check"]("e1", False)

    assert ("check", "e1", False) in browser.actions
    assert session.verdict is None


@pytest.mark.parametrize(
    "name,args",
    [("fill", ("e1", "42")), ("click", ("e1",)), ("check", ("e1", True)), ("select", ("e1", "x"))],
)
def test_trockenlauf_fasst_nichts_an(name, args):
    browser = FakeBrowser([{"ref": "e1", "tag": "input", "type": "text", "label": "Stellplatz"}])
    _, tools = tools_for(browser, dry_run=True)
    tools["look"]()

    answer = tools[name](*args)

    assert "TROCKENLAUF" in answer
    assert browser.actions == []


def test_schrittgrenze_stoppt_weitere_aktionen():
    browser = FakeBrowser()
    session, tools = tools_for(browser, max_steps=2)
    session.steps.extend(["schritt 1", "schritt 2"])

    answer = tools["fill"]("e1", "x")

    assert "Schrittgrenze" in answer
    assert browser.actions == []


def test_finish_und_stop_setzen_das_ergebnis():
    _, tools = tools_for(FakeBrowser())
    tools["finish"](True, "Portal bestätigt")
    session, tools2 = tools_for(FakeBrowser())
    tools2["stop"]("Kreditkarte verlangt")
    assert session.verdict is Verdict.NEEDS_HUMAN
    assert session.reason == "Kreditkarte verlangt"
