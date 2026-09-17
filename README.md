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

**Jede Suche wird protokolliert — mit allen sichtbaren Netzen**, nicht nur mit
denen, die du benutzt hast. So steht später da, was es an einem Platz überhaupt
gab. Vier Spalten:

| Datum | WLAN | Passwort | Adresse |
|---|---|---|---|
| 2026-07-04 18:30 | Campingplatz-Gast | (nicht verbunden) | Seeweg 3, 23570 Lübeck |
| 2026-07-04 18:30 | Stellplatz-WLAN | sonne2026 | Seeweg 3, 23570 Lübeck |
| 2026-07-04 18:30 | FRITZ!Box 7590 | (nicht verbunden) | Seeweg 3, 23570 Lübeck |

Die Passwortspalte sagt damit zugleich, welches Netz du wirklich benutzt hast.

**Verbindest du dich später mit einem Netz, wird die vorhandene Zeile
ergänzt**, nicht eine zweite angelegt — sonst stünde dasselbe Netz zweimal da,
einmal mit und einmal ohne Passwort. Umgekehrt gilt: Ein einmal notiertes
Passwort wird von einem späteren Suchlauf nie wieder überschrieben.

**Was in der Passwortspalte landet:**

- was du beim Verbinden eingetippt hast, oder
- bei einem bekannten Netz das in Windows gespeicherte Passwort
  (`netsh wlan show profile ... key=clear`; verlangt erhöhte Rechte — ohne sie
  steht dort `(unbekannt)` statt eines falschen Werts), oder
- `(offenes Netz)` bei Netzen ohne Verschlüsselung, oder
- `(nicht verbunden)`, solange das Netz nur gesehen wurde.

**Ohne eingetragenen Standort wird nichts protokolliert.** Eine Liste von
Netznamen ohne Ort beantwortet später keine Frage, und würde die Adresse
nachgetragen, stünde alles ein zweites Mal da. Trägst du den Standort nach,
wird der bereits vorliegende Suchtreffer sofort damit protokolliert — du musst
nicht erneut suchen.

**Die Adresse wird eingetragen, nicht ermittelt.** Das ist Absicht: Die
öffentliche IP gehört dem LTE-Router und geolokalisiert irgendwohin, und eine
WLAN-basierte Ortung würde die BSSIDs deiner Umgebung an Google oder Mozilla
senden. Das Feld merkt sich den zuletzt benutzten Wert — der Bus steht meist
noch da, wo er gestern stand.

Mehrfaches Suchen am selben Ort und Tag ergibt einen Satz Zeilen, keine fünf.
Einen Platz von früher trägst du unter „Eintrag von Hand nachtragen" nach.

Die Datei ist CSV mit Semikolon und BOM — deutsches Excel öffnet sie mit
korrekten Umlauten per Doppelklick. In der Oberfläche gibt es einen
Download-Knopf, aber die Datei liegt ohnehin offen neben `config.toml`.

> **Sie enthält Passwörter im Klartext.** Deshalb steht sie in `.gitignore` und
> gehört nicht in eine Cloud-Synchronisation. Wer das anders haben will:
> `enabled = false` in `[logbook]` schaltet das Logbuch ab.

---

## Einrichten (Windows)

Voraussetzungen: Windows 10/11, Python 3.11 oder neuer, ein Anthropic-API-Key.

### Ortungsdienste einschalten — sonst findet nichts statt

Neuere Windows-Versionen behandeln Netzwerknamen als Standortdaten und geben
die WLAN-Liste nur mit eingeschalteten Ortungsdiensten heraus. Ohne sie liefert
`netsh wlan show networks` gar nichts, auch nicht als Administrator.

`Windows-Taste + R`, dann `ms-settings:privacy-location` eingeben. Dort **zwei**
Schalter auf „Ein":

1. **Ortungsdienste**
2. **Desktop-Apps den Zugriff auf Ihren Standort erlauben**

WLAN Finder erkennt diesen Fall und zeigt die Anleitung in der Oberfläche —
du musst sie nicht auswendig können. Dasselbe gilt für den zweiten Klassiker:
ausgeschalteter Funkadapter (Flugmodus, WLAN-Kachel, Hardwaretaste).

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

1. **Erneut suchen** — zeigt **alle** Netze in Reichweite. Netze, zu denen ein
   Wechsel nichts bringt, stehen blass darunter, mit dem Grund: „aktuell
   verbunden", „Firmennetz mit Nutzerkonto" oder „Signal zu schwach".
   Eine leere Liste heißt damit wirklich: nichts gefunden — und nicht:
   alles herausgefiltert.

   Die Schwelle liegt bei **15 %** und ist über `min_signal` in `config.toml`
   änderbar. Niedrig angesetzt, weil auf einem Stellplatz ein schwaches Netz
   oft alles ist, was da ist; zwischen 15 und 40 % steht am Netz dran, dass
   der Versuch lohnt, es aber kaum stabil wird.
2. **Verbinden** — nur auf Klick. Bei verschlüsselten, noch unbekannten Netzen
   fragt die Oberfläche nach dem Passwort.

   Trägt das Netz das Abzeichen **Passwort vorhanden**, entfällt die Frage:
   Das Passwort steht entweder im gespeicherten Windows-Profil oder im
   eigenen Logbuch vom letzten Besuch. Es bleibt dabei im lokalen Dienst und
   wird nicht an den Browser geschickt. Ist beides vorhanden, gewinnt das
   Windows-Profil — wurde das Passwort am Platz geändert, ist es der
   neuere Stand.
3. Alles Gefundene landet im **Logbuch** (s. o.) — Voraussetzung ist der
   Standort im Feld ganz oben.
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
  offer.py          Regeln: welche Netze angeboten werden und warum nicht
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

79 Tests, ohne Netzwerk- und ohne API-Zugriff. Abgedeckt sind die
netsh-Parser (deutsch und englisch), die Portal-Erkennung inklusive des
heimtückischen Falls „Status 200, aber es ist die Portalseite", die
Angebotsregeln, das Logbuch (Suchläufe, nachträgliches Ergänzen des
Passworts, Dublettenprüfung, Semikolons und Umlaute in den Werten) und vor
allem die Sperren des Agenten.

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
- **Auf Firmenlaptops kann die Gruppenrichtlinie die Ortungsdienste sperren.**
  Dann lässt sich der Schalter nicht umlegen und das Scannen bleibt blockiert —
  das ist eine Entscheidung der IT, an der das Programm nichts ändern kann.
- **Kein VPN, keine Verkehrsabsicherung.**
- Die Erkennung von Zustimmungshaken ist eine Schlagwort-Heuristik. Sie kann
  einen ungewöhnlich beschrifteten AGB-Haken übersehen. Deshalb ist sie eine
  Bremse und keine Freigabe.

## Kosten

Ein Portal-Durchlauf sind wenige API-Aufrufe mit kleinen Seitenbeschreibungen —
überschaubar, aber nicht kostenlos, und nur beim Anmelden, nicht im Leerlauf.
Modell und Preise stehen in `config.toml` bzw. der Anthropic-Preisliste.
