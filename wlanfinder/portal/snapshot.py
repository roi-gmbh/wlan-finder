"""Eine Portalseite in eine Beschreibung übersetzen, mit der ein Sprachmodell
arbeiten kann.

Bewusst kein Computer Use mit Screenshots: Captive Portals sind schlichte
HTML-Formulare. Der Seiteninhalt als Text ist präziser, billiger und läuft
auch ohne sichtbaren Bildschirm. Screenshots wären erst nötig, wenn ein
Portal etwas macht, das sich im DOM nicht abbildet.

Diese Datei enthält nur reine Funktionen - kein Browser -, damit sie sich
ohne Playwright testen lässt.
"""

from __future__ import annotations

from typing import Any

# Woran eine Zustimmungs-Checkbox erkannt wird. Eine Heuristik, kein Beweis:
# sie kann ein AGB-Haken übersehen, der ungewöhnlich beschriftet ist.
# Deshalb ist sie eine Bremse und keine Freigabe - im Zweifel hält der Agent an.
CONSENT_WORDS = (
    "agb", "terms", "bedingungen", "nutzungsbedingungen", "datenschutz",
    "privacy", "einverstanden", "akzeptier", "accept", "consent",
    "zustimm", "haftung", "disclaimer", "einwillig",
)

MAX_TEXT_CHARS = 2000
MAX_ELEMENTS = 40


def is_consent_element(element: dict[str, Any]) -> bool:
    """Ist das ein Haken, mit dem man rechtlich etwas zustimmt?"""
    if element.get("type") != "checkbox":
        return False
    haystack = " ".join(
        str(element.get(key, "")) for key in ("label", "name", "id", "text", "title")
    ).lower()
    return any(word in haystack for word in CONSENT_WORDS)


def describe_element(element: dict[str, Any]) -> str:
    """Eine Zeile pro Bedienelement."""
    ref = element.get("ref", "?")
    tag = element.get("tag", "?")
    kind = element.get("type") or tag
    label = element.get("label") or element.get("text") or element.get("placeholder") or ""

    parts = [f"[{ref}] {kind}"]
    if label:
        parts.append(f'Beschriftung: "{label.strip()[:120]}"')
    if element.get("name"):
        parts.append(f'name={element["name"]}')
    if element.get("value") and kind not in {"password"}:
        parts.append(f'Wert: "{str(element["value"])[:60]}"')
    if kind == "checkbox":
        parts.append("angehakt" if element.get("checked") else "nicht angehakt")
        if is_consent_element(element):
            parts.append("ZUSTIMMUNG")
    if element.get("options"):
        options = ", ".join(str(o)[:30] for o in element["options"][:10])
        parts.append(f"Auswahl: {options}")
    if element.get("required"):
        parts.append("Pflichtfeld")
    return " | ".join(parts)


def render(page_state: dict[str, Any]) -> str:
    """Den Seitenzustand als Text für das Modell aufbereiten."""
    text = (page_state.get("text") or "").strip()
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n[... gekürzt ...]"

    elements = page_state.get("elements", [])[:MAX_ELEMENTS]
    lines = [
        f"URL: {page_state.get('url', '?')}",
        f"Titel: {page_state.get('title', '')}",
        "",
        "Sichtbarer Text:",
        text or "(kein Text)",
        "",
        f"Bedienelemente ({len(elements)}):",
    ]
    lines.extend(describe_element(el) for el in elements)
    if not elements:
        lines.append("(keine gefunden)")
    return "\n".join(lines)
