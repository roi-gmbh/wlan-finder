"""Playwright-Hülle um die Portalseite.

Nur Mechanik: Seite öffnen, Zustand auslesen, Elemente bedienen. Was zu tun
ist, entscheidet agent.py.
"""

from __future__ import annotations

from typing import Any

# JavaScript, das im Kontext der Portalseite läuft und die sichtbaren
# Bedienelemente einsammelt. Jedes bekommt ein Attribut data-wlanfinder-ref,
# über das es später wieder eindeutig auffindbar ist - stabiler als
# CSS-Selektoren, die sich bei jedem Rendern ändern können.
_COLLECT_JS = """
() => {
  const selector = 'input, select, textarea, button, a[href]';
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const labelFor = (el) => {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.innerText.trim()) return lab.innerText.trim();
    }
    const parent = el.closest('label');
    if (parent && parent.innerText.trim()) return parent.innerText.trim();
    return el.getAttribute('aria-label') || el.getAttribute('title') || '';
  };
  const elements = [];
  let index = 0;
  for (const el of document.querySelectorAll(selector)) {
    if (el.type === 'hidden' || !visible(el)) continue;
    const ref = 'e' + (++index);
    el.setAttribute('data-wlanfinder-ref', ref);
    elements.push({
      ref,
      tag: el.tagName.toLowerCase(),
      type: (el.type || '').toLowerCase(),
      name: el.name || '',
      id: el.id || '',
      label: labelFor(el),
      placeholder: el.placeholder || '',
      // Passwortfelder nie im Klartext herausgeben.
      value: el.type === 'password' ? '' : (el.value || ''),
      checked: el.checked === true,
      required: el.required === true,
      text: (el.innerText || '').trim().slice(0, 120),
      title: el.getAttribute('title') || '',
      options: el.tagName.toLowerCase() === 'select'
        ? Array.from(el.options).map((o) => o.value || o.text)
        : undefined,
    });
  }
  return { url: location.href, title: document.title, text: document.body ? document.body.innerText : '', elements };
}
"""


class PortalBrowser:
    """Ein Browserfenster auf der Portalseite. Als Kontextmanager benutzen."""

    def __init__(self, headful: bool = True, timeout_ms: int = 15000) -> None:
        self._headful = headful
        self._timeout_ms = timeout_ms
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "PortalBrowser":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=not self._headful)
        context = self._browser.new_context(ignore_https_errors=True)
        self._page = context.new_page()
        self._page.set_default_timeout(self._timeout_ms)
        return self

    def __exit__(self, *exc: object) -> None:
        # Beim Aufräumen darf nichts mehr werfen - sonst verdeckt der
        # Aufräumfehler das eigentliche Problem.
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001
                pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass

    def goto(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded")

    def state(self) -> dict[str, Any]:
        """Aktueller Seitenzustand als einfaches dict."""
        return self._page.evaluate(_COLLECT_JS)

    def _locator(self, ref: str):
        return self._page.locator(f'[data-wlanfinder-ref="{ref}"]')

    def click(self, ref: str) -> None:
        self._locator(ref).click()
        self._settle()

    def fill(self, ref: str, text: str) -> None:
        self._locator(ref).fill(text)

    def check(self, ref: str, checked: bool) -> None:
        locator = self._locator(ref)
        locator.check() if checked else locator.uncheck()

    def select(self, ref: str, value: str) -> None:
        self._locator(ref).select_option(value)

    def _settle(self) -> None:
        """Nach einem Klick kurz warten - Portale leiten gern weiter."""
        try:
            self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:  # noqa: BLE001 - Zeitüberschreitung ist hier normal
            pass
