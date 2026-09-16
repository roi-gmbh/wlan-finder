"""Der KI-Baustein: Claude bedient eine unbekannte Captive-Portal-Seite.

Das ist die einzige Stelle im Projekt, an der ein Sprachmodell nötig ist.
Scannen, Verbinden und die Frage "soll ich wechseln?" sind feste Regeln - aber
die Anmeldeseite eines Campingplatzes ist jedes Mal anders aufgebaut, mal mit
AGB-Haken, mal mit Stellplatznummer, mal nur mit einem Knopf. Genau dafür ist
ein Modell da: unstrukturierte, wechselnde Eingaben deuten.

Grenzen, die hier hart eingebaut sind und nicht im Prompt stehen:
- Der Agent darf keine Zustimmungshaken setzen, solange accept_terms aus ist.
  Ein AGB-Haken ist eine Willenserklärung im Namen des Nutzers.
- Im Trockenlauf wird nichts geklickt, nur protokolliert.
- Eingetragen werden darf nur, was der Nutzer vorher als Angabe hinterlegt hat.
  Der Agent erfindet keine Namen, Adressen oder Nummern.
"""

from __future__ import annotations

import anthropic
from anthropic import beta_tool

from ..models import PortalResult, Verdict
from .browser import PortalBrowser
from .snapshot import is_consent_element, render

SYSTEM_PROMPT = """Du bedienst die Anmeldeseite eines öffentlichen WLANs \
(Captive Portal), zum Beispiel auf einem Campingplatz oder Rastplatz. Ziel ist, \
den Internetzugang freizuschalten - mehr nicht.

So gehst du vor:
1. Sieh dir mit `look` die Seite an.
2. Fülle nur Felder aus, für die dir unten eine Angabe des Nutzers vorliegt.
   Erfinde nichts. Fehlt eine Pflichtangabe, beende mit `stop`.
3. Betätige den Knopf, der die Anmeldung abschickt.
4. Sieh mit `look` nach, ob es geklappt hat. Rufe dann `finish` auf.

Halte an und rufe `stop` auf, wenn die Seite
- Geld, Kreditkarten- oder Bankdaten verlangt,
- eine Registrierung mit persönlichen Daten verlangt, die nicht vorliegen,
- einen Gutschein- oder Zugangscode verlangt, der nicht vorliegt,
- oder wenn du nach mehreren Versuchen nicht weiterkommst.

Arbeite sparsam: wenige, gezielte Schritte. Nach jedem Klick lohnt ein `look`."""


class _Session:
    """Hält Zustand und Grenzen für einen Portal-Durchlauf zusammen."""

    def __init__(self, browser: PortalBrowser, *, dry_run: bool, accept_terms: bool, max_steps: int) -> None:
        self.browser = browser
        self.dry_run = dry_run
        self.accept_terms = accept_terms
        self.max_steps = max_steps
        self.steps: list[str] = []
        self.verdict: Verdict | None = None
        self.reason = ""
        self._refs: dict[str, dict] = {}

    def log(self, message: str) -> str:
        self.steps.append(message)
        return message

    def budget_left(self) -> bool:
        return len(self.steps) < self.max_steps

    def remember(self, state: dict) -> None:
        self._refs = {el["ref"]: el for el in state.get("elements", [])}

    def element(self, ref: str) -> dict:
        return self._refs.get(ref, {})


def build_tools(session: _Session, hints: dict[str, str] | None = None) -> list:
    """Erzeugt die Werkzeuge, die Claude aufrufen darf.

    Bewusst eine eigene Funktion: So lassen sich die eingebauten Sperren
    (Zustimmung, Trockenlauf, Schrittgrenze) testen, ohne die API zu rufen.
    """
    hints = hints or {}

    # --- Werkzeuge, die Claude aufrufen darf -------------------------------

    @beta_tool
    def look() -> str:
        """Liest die aktuelle Seite: Adresse, Text und alle Bedienelemente mit ihrer Kennung."""
        state = session.browser.state()
        session.remember(state)
        session.log(f"angesehen: {state.get('url', '?')}")
        return render(state)

    @beta_tool
    def fill(ref: str, text: str) -> str:
        """Trägt Text in ein Eingabefeld ein.

        Args:
            ref: Kennung des Feldes, z.B. "e3".
            text: Der einzutragende Text.
        """
        if not session.budget_left():
            return _budget_message(session)
        if session.dry_run:
            return session.log(f"TROCKENLAUF: würde in {ref} eintragen: {text!r}")
        session.browser.fill(ref, text)
        return session.log(f"{ref} ausgefüllt")

    @beta_tool
    def click(ref: str) -> str:
        """Klickt einen Knopf oder Link an.

        Args:
            ref: Kennung des Elements, z.B. "e5".
        """
        if not session.budget_left():
            return _budget_message(session)
        if session.dry_run:
            return session.log(f"TROCKENLAUF: würde {ref} anklicken")
        session.browser.click(ref)
        return session.log(f"{ref} angeklickt - danach `look` aufrufen")

    @beta_tool
    def check(ref: str, checked: bool = True) -> str:
        """Setzt oder entfernt einen Haken in einer Checkbox.

        Args:
            ref: Kennung der Checkbox.
            checked: True setzt den Haken, False entfernt ihn.
        """
        if not session.budget_left():
            return _budget_message(session)
        element = session.element(ref)
        # Diese Sperre ist Absicht und liegt bewusst im Code, nicht im Prompt:
        # ein Prompt lässt sich von der Portalseite überreden, eine
        # if-Abfrage nicht.
        if checked and is_consent_element(element) and not session.accept_terms:
            session.verdict = Verdict.NEEDS_HUMAN
            session.reason = (
                f'Die Seite verlangt Zustimmung zu "{element.get("label", "")[:100]}". '
                "Das muss der Nutzer selbst bestätigen (accept_terms ist aus)."
            )
            return session.log("ABGELEHNT: Zustimmungshaken darf ich nicht setzen. Rufe `stop` auf.")
        if session.dry_run:
            return session.log(f"TROCKENLAUF: würde Haken bei {ref} {'setzen' if checked else 'entfernen'}")
        session.browser.check(ref, checked)
        return session.log(f"Haken bei {ref} {'gesetzt' if checked else 'entfernt'}")

    @beta_tool
    def select(ref: str, value: str) -> str:
        """Wählt einen Eintrag in einem Auswahlfeld.

        Args:
            ref: Kennung des Auswahlfeldes.
            value: Der auszuwählende Wert.
        """
        if not session.budget_left():
            return _budget_message(session)
        if session.dry_run:
            return session.log(f"TROCKENLAUF: würde in {ref} {value!r} auswählen")
        session.browser.select(ref, value)
        return session.log(f"{ref} auf {value!r} gesetzt")

    @beta_tool
    def finish(succeeded: bool, reason: str) -> str:
        """Beendet den Vorgang, wenn die Anmeldung durch ist.

        Args:
            succeeded: True, wenn die Anmeldung erfolgreich aussah.
            reason: Kurze Begründung.
        """
        session.verdict = Verdict.ONLINE if succeeded else Verdict.FAILED
        session.reason = reason
        return session.log(f"fertig: {reason}")

    @beta_tool
    def stop(reason: str) -> str:
        """Bricht ab und übergibt an den Nutzer.

        Args:
            reason: Warum hier ein Mensch übernehmen muss.
        """
        session.verdict = Verdict.NEEDS_HUMAN
        session.reason = reason
        return session.log(f"abgebrochen: {reason}")

    return [look, fill, click, check, select, finish, stop]


def run(
    browser: PortalBrowser,
    *,
    start_url: str,
    hints: dict[str, str] | None = None,
    dry_run: bool = True,
    accept_terms: bool = False,
    max_steps: int = 20,
    model: str = "claude-opus-5",
    max_tokens: int = 16000,
) -> PortalResult:
    """Lässt Claude die Portalseite bedienen und liefert das Ergebnis zurück."""
    session = _Session(browser, dry_run=dry_run, accept_terms=accept_terms, max_steps=max_steps)
    hints = hints or {}

    tools = build_tools(session, hints)

    # --- Durchlauf ---------------------------------------------------------

    browser.goto(start_url)
    client = anthropic.Anthropic()

    hint_text = (
        "\n".join(f"- {key}: {value}" for key, value in hints.items())
        if hints
        else "(keine - fülle keine Felder aus, die eine Angabe verlangen)"
    )
    opening = (
        f"Die Anmeldeseite ist geöffnet: {start_url}\n\n"
        f"Angaben des Nutzers, die du verwenden darfst:\n{hint_text}\n\n"
        f"{'TROCKENLAUF: Deine Aktionen werden nur protokolliert, nicht ausgeführt. Gehe trotzdem alle Schritte durch.' if dry_run else ''}"
    )

    try:
        runner = client.beta.messages.tool_runner(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            max_iterations=max_steps,
            messages=[{"role": "user", "content": opening}],
        )
        for _ in runner:
            if session.verdict is not None:
                break  # finish/stop wurde aufgerufen
    except anthropic.AuthenticationError:
        return PortalResult(Verdict.FAILED, "ANTHROPIC_API_KEY fehlt oder ist ungültig.", session.steps)
    except anthropic.RateLimitError:
        return PortalResult(Verdict.FAILED, "API-Ratenlimit erreicht - später erneut versuchen.", session.steps)
    except anthropic.APIConnectionError:
        return PortalResult(
            Verdict.FAILED,
            "Die Claude-API war nicht erreichbar. Läuft die Verbindung über LAN/LTE noch?",
            session.steps,
        )
    except anthropic.APIStatusError as exc:
        return PortalResult(Verdict.FAILED, f"API-Fehler {exc.status_code}: {exc.message}", session.steps)

    if dry_run:
        return PortalResult(Verdict.DRY_RUN, session.reason or "Trockenlauf beendet", session.steps)
    if session.verdict is None:
        return PortalResult(Verdict.FAILED, "Der Agent kam ohne Ergebnis zum Ende.", session.steps)
    return PortalResult(session.verdict, session.reason, session.steps)


def _budget_message(session: _Session) -> str:
    return (
        f"Schrittgrenze von {session.max_steps} erreicht. Keine weiteren Aktionen. "
        "Rufe `stop` mit einer Begründung auf."
    )
