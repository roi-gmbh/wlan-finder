# WLAN Finder

Findet WLANs am Standort, bietet den Wechsel an und meldet sich bei Bedarf an der
Gastportal-Seite an. Gedacht für den Laptop im Bus, der schon über LAN am
LTE-Router hängt und zusätzlich das WLAN des Campingplatzes mitnehmen soll.

Bedient wird alles im Browser: Ein kleiner lokaler Dienst spricht mit dem
Betriebssystem, die Oberfläche läuft auf `http://127.0.0.1:8765`.

---

## Was hier KI macht — und was ausdrücklich nicht

Der Großteil dieses Projekts kommt ohne Sprachmodell aus, und das ist Absicht:

| Schritt | Umsetzung | Warum |
|---|---|---|
| WLANs am Standort suchen | `netsh wlan show networks` | Deterministischer Systemaufruf. Ein Modell wäre langsamer, teurer und unzuverlässiger. |
| Erkennen, ob Internet anliegt | HTTP-Prüfung gegen bekannte URLs | Dasselbe Verfahren, das Windows selbst nutzt. Feste Regel. |
| Wechsel anbieten | Regeln in `offer.py` | Nachvollziehbar und ohne Modell änderbar. |
| Verbinden | `netsh wlan connect` | Systemaufruf. |
| **Anmeldeseite bedienen** | **Claude mit Werkzeugen** | **Hier steckt das eigentliche Problem:** Jedes Portal sieht anders aus — mal AGB-Haken, mal Stellplatznummer, mal nur ein Knopf. Unstrukturierte, wechselnde Eingaben zu deuten ist genau das, wofür ein Modell taugt. |

Ein Agent lohnt sich punktuell, nicht überall.

### Warum kein Computer Use

Computer Use (Claude steuert Maus und Tastatur anhand von Screenshots) wäre der
naheliegende Griff, ist hier aber der falsche: Captive Portals sind schlichte
HTML-Formulare. Der Seiteninhalt als Text ist präziser, deutlich billiger und
funktioniert auch ohne sichtbaren Bildschirm. WLAN Finder liest die Seite
deshalb über das DOM (`portal/snapshot.py`) und gibt Claude gezielte Werkzeuge
(`fill`, `click`, `check`, …) statt eines Mauszeigers. Screenshots wären erst
nötig, wenn ein Portal etwas tut, das sich im DOM nicht abbildet.

---

## Der Punkt, an dem so etwas sonst scheitert

Im Bus liegt **schon Internet an** — über Kabel zum LTE-Router. Eine naive
Internet-Prüfung geht deshalb über das Kabel, meldet brav „online", und das
Captive Portal des Campingplatzes wird **nie** gesehen.

WLAN Finder bindet die Prüfung deshalb an die IP-Adresse des WLAN-Adapters
(`connectivity.check(..., local_address=...)`). Nur so misst man das WLAN und
nicht die bestehende Leitung.

Für den Browser, der die Portalseite öffnet, gilt dasselbe Problem, aber es
lässt sich dort nicht im Programm lösen: Chromium folgt der Routing-Tabelle des
Systems. Liegt die Metrik des LAN-Adapters niedriger, geht auch der Portal-Aufruf
über das Kabel und landet im echten Internet statt auf der Anmeldeseite.

**Abhilfe, solange du dich anmeldest** (Eingabeaufforderung als Administrator):

```
netsh interface ipv4 set interface "WLAN" metric=1
```

und danach zurück auf `metric=auto`. WLAN Finder tut das **nicht** von selbst —
das ist ein Eingriff in die Netzwerkkonfiguration des Rechners, den ein Programm
nicht unbemerkt vornehmen sollte.

---

## Sicherheitsgrenzen

Drei Sperren sind fest im Code verdrahtet, nicht bloß im Prompt formuliert.
Das ist der Unterschied: Einen Prompt kann die Portalseite überreden, eine
`if`-Abfrage nicht.

1. **Keine Zustimmung in deinem Namen.** Erkennt der Agent einen Haken mit
   AGB-, Datenschutz- oder Einwilligungsbezug, bricht er ab und übergibt an
   dich — solange `accept_terms = false` gesetzt ist (Voreinstellung). Ein
   solcher Haken ist eine Willenserklärung; ob sie trägt, wenn eine Software sie
   setzt, ist eine Rechtsfrage, die dieses Projekt nicht beantworten kann.
2. **Trockenlauf ist die Voreinstellung.** `dry_run = true` lässt den Agenten
   die Seite analysieren und protokollieren, was er tun *würde*, ohne zu klicken.
3. **Nie von selbst verbinden.** Es gibt keinen Codepfad, der ohne Klick in der
   Oberfläche das Netz wechselt. Automatisch in unbekannte WLANs zu wechseln ist
   grundsätzlich riskant (gefälschte Access Points, unverschlüsselter Verkehr).

Dazu: Der Agent trägt nur Werte ein, die du vorher in der Oberfläche hinterlegt
hast. Er erfindet keine Namen, Nummern oder Adressen. Passwortfelder werden nie
im Klartext an das Modell gegeben. Die Schrittzahl ist begrenzt.

Unabhängig davon gilt: In einem fremden WLAN gehört der Verkehr durch ein VPN.
Das leistet WLAN Finder nicht.

---

## Logbuch

Jede Verbindung wird in `wlan-logbuch.csv` festgehalten — vier Spalten:

| Datum | WLAN | Passwort | Adresse |
|---|---|---|---|
| 2026-07-04 18:30 | Campingplatz-Gast | (offenes Netz) | Seeweg 3, 23570 Lübeck |
| 2026-07-11 14:05 | Stellplatz-WLAN | sonne2026 | Am Deich 7, 25980 Sylt |

Damit steht beim nächsten Besuch schwarz auf weiß, wie das Netz hieß und was
es für ein Passwort hatte.

**Was in der Passwortspalte landet:**

- was du beim Verbinden eingetippt hast, oder
- bei einem bekannten Netz das in Windows gespeicherte Passwort
  (`netsh wlan show profile ... key=clear`; verlangt erhöhte Rechte — ohne sie
  steht dort `(unbekannt)` statt eines falschen Werts), oder
- `(offenes Netz)` bei Netzen ohne Verschlüsselung.

**Die Adresse wird eingetragen, nicht ermittelt.** Das ist Absicht: Die
öffentliche IP gehört dem LTE-Router und geolokalisiert irgendwohin, und eine
WLAN-basierte Ortung würde die BSSIDs deiner Umgebung an Google oder Mozilla
senden. Das Feld merkt sich den zuletzt benutzten Wert — der Bus steht meist
noch da, wo er gestern stand.

**Geschrieben wird beim Verbinden, nicht bei jedem Scan.** Eine Zeile für ein
Netz, mit dem du nie verbunden warst, hätte keine Passwortspalte und wäre nur
Rauschen. Mehrfaches Verbinden mit demselben Netz am selben Ort und Tag ergibt
einen Eintrag, keine fünf. Einen Platz von früher trägst du in der Oberfläche
unter „Eintrag von Hand nachtragen" nach.

Die Datei ist CSV mit Semikolon und BOM — deutsches Excel öffnet sie mit
korrekten Umlauten per Doppelklick. In der Oberfläche gibt es einen
Download-Knopf, aber die Datei liegt ohnehin offen neben `config.toml`.

> **Sie enthält Passwörter im Klartext.** Deshalb steht sie in `.gitignore` und
> gehört nicht in eine Cloud-Synchronisation. Wer das anders haben will:
> `enabled = false` in `[logbook]` schaltet das Logbuch ab.

---

## Einrichten (Windows)

Voraussetzungen: Windows 10/11, Python 3.11 oder neuer, ein Anthropic-API-Key.

```powershell
git clone <dieses-repo>
cd wlan-finder
py -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m playwright install chromium

copy config.example.toml config.toml
setx ANTHROPIC_API_KEY "sk-ant-..."
```

Starten:

```powershell
wlan-finder
```

Der Browser öffnet sich auf `http://127.0.0.1:8765`.

Ohne Windows (z. B. zum Ansehen der Oberfläche):

```
python -m wlanfinder --demo
```

---

## Bedienung

1. **Erneut suchen** — zeigt die Netze in Reichweite. Zu schwache (unter 40 %)
   und Firmennetze mit Nutzerkonto werden ausgeblendet.
2. **Verbinden** — nur auf Klick. Bei verschlüsselten, noch unbekannten Netzen
   fragt die Oberfläche nach dem Passwort.
3. Jede Verbindung landet im **Logbuch** (s. o.). Trag den Standort vorher
   oben ein, dann steht er in der Zeile.
4. Erkennt WLAN Finder danach eine Anmeldeseite, erscheint der Abschnitt
   **Anmeldeseite erkannt**. Dort trägst du ein, was das Portal erfahren darf
   (Stellplatznummer, Nachname, …), und startest den Agenten.
5. Die Schritte des Agenten laufen live mit. Im Trockenlauf steht vor jedem
   Schritt `TROCKENLAUF:` — dann wurde nichts geklickt.

Scharf schalten: In `config.toml` `dry_run = false` setzen.

---

## Aufbau

```
wlanfinder/
  netsh.py          netsh-Aufrufe und Parser (spracheunabhängig, s. u.)
  logbook.py        CSV-Logbuch: Datum, WLAN, Passwort, Adresse
  wifi.py           Schnittstelle zur Hardware + Fake-Backend für Tests
  connectivity.py   Portal-Erkennung, an den WLAN-Adapter gebunden
  offer.py          Regeln: welcher Wechsel lohnt sich
  service.py        Ablauf und Zustand
  server.py         FastAPI + JSON-Schnittstelle
  web/index.html    Oberfläche (eine Datei, keine Abhängigkeiten, offlinefähig)
  portal/
    snapshot.py     Seite → Beschreibung für das Modell (reine Funktionen)
    browser.py      Playwright-Hülle
    agent.py        Claude mit Werkzeugen + die eingebauten Sperren
```

`netsh` gibt seine Ausgabe in der Systemsprache aus — auf deutschem Windows
heißt der Schlüssel `Authentifizierung`, auf englischem `Authentication`.
Der Parser wertet deshalb die **Form der Werte** aus (Signal ist das, was auf
`%` endet) statt der Schlüsselnamen. Beide Sprachvarianten sind in
`tests/test_netsh_parse.py` abgedeckt.

---

## Tests

```
pip install -e ".[dev]"
pytest
```

52 Tests, ohne Netzwerk- und ohne API-Zugriff. Abgedeckt sind die
netsh-Parser (deutsch und englisch), die Portal-Erkennung inklusive des
heimtückischen Falls „Status 200, aber es ist die Portalseite", die
Angebotsregeln, das Logbuch (Dublettenprüfung, Semikolons und Umlaute in
den Werten) und vor allem die Sperren des Agenten.

---

## Stand und Grenzen

Ehrlich benannt, damit niemand davon überrascht wird:

- **Die Windows-Teile sind ungetestet auf echter Hardware.** Entwickelt und
  getestet wurde unter Linux gegen aufgezeichnete `netsh`-Ausgaben und ein
  Fake-Backend. Die Parser sind abgedeckt, das Zusammenspiel mit echtem
  `netsh` und echten Adaptern nicht. Erster Praxislauf gehört auf den Laptop.
- **Kein Agentenlauf gegen ein echtes Portal.** Die Sperren sind getestet, das
  Verhalten des Modells auf einer echten Campingplatzseite nicht.
- **WPA-Enterprise wird nicht unterstützt** (Firmennetze mit Nutzerkonto).
- **Kein VPN, keine Verkehrsabsicherung.**
- Die Erkennung von Zustimmungshaken ist eine Schlagwort-Heuristik. Sie kann
  einen ungewöhnlich beschrifteten AGB-Haken übersehen. Deshalb ist sie eine
  Bremse und keine Freigabe.

## Kosten

Ein Portal-Durchlauf sind wenige API-Aufrufe mit kleinen Seitenbeschreibungen —
überschaubar, aber nicht kostenlos, und nur beim Anmelden, nicht im Leerlauf.
Modell und Preise stehen in `config.toml` bzw. der Anthropic-Preisliste.
