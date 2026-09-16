"""Logbuch der gefundenen WLANs.

Vier Spalten, wie abgesprochen: Datum, WLAN-Name, WLAN-Passwort, Adresse.
Der Zweck ist das Wiederfinden: Steht der Bus nächstes Jahr wieder auf
demselben Platz, steht hier, welche Netze es dort gab, wie sie hießen und
welches davon mit welchem Passwort funktioniert hat.

Protokolliert wird jede Suche mit allen sichtbaren Netzen. Verbindest du dich
später mit einem davon, wird die **vorhandene Zeile ergänzt** statt eine
zweite anzulegen - sonst stünde dasselbe Netz zweimal da, einmal mit und
einmal ohne Passwort.

Format ist CSV, damit sich die Datei in Excel, LibreOffice oder jedem
Texteditor öffnen lässt und niemand auf dieses Programm angewiesen ist, um
an seine eigenen Daten zu kommen.

ACHTUNG: In dieser Datei stehen WLAN-Passwörter im Klartext. Sie gehört
nicht in ein Repository und nicht in eine Cloud-Synchronisation.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Deutsches Excel erwartet Semikolon als Trennzeichen, und ohne BOM zeigt es
# Umlaute als Kauderwelsch. Beides hier einmal richtig eingestellt.
DELIMITER = ";"
ENCODING = "utf-8-sig"

COLUMNS = ["Datum", "WLAN", "Passwort", "Adresse"]

DEFAULT_FILENAME = "wlan-logbuch.csv"

# Platzhalter statt leerer Zellen - eine leere Zelle lässt offen, ob das
# Passwort fehlt oder das Netz keines hat.
OPEN_NETWORK = "(offenes Netz)"
UNKNOWN_PASSWORD = "(unbekannt)"
NOT_CONNECTED = "(nicht verbunden)"

# Diese Werte sind Lückenfüller: Sobald etwas Besseres bekannt wird, darf die
# Zeile überschrieben werden. Ein echtes Passwort oder "(offenes Netz)" ist
# dagegen eine Tatsache und wird nie von einem Platzhalter verdrängt.
PLACEHOLDERS = frozenset({UNKNOWN_PASSWORD, NOT_CONNECTED})


@dataclass(frozen=True)
class Entry:
    date: str
    ssid: str
    password: str
    address: str

    def to_row(self) -> list[str]:
        return [self.date, self.ssid, self.password, self.address]

    def to_dict(self) -> dict[str, str]:
        return {"date": self.date, "ssid": self.ssid, "password": self.password, "address": self.address}

    @classmethod
    def from_row(cls, row: list[str]) -> "Entry":
        padded = (row + ["", "", "", ""])[:4]
        return cls(*padded)


class Logbook:
    def __init__(self, path: Path) -> None:
        self.path = path

    def entries(self) -> list[Entry]:
        """Alle Einträge, neueste zuerst."""
        return self._read()[::-1]

    def add(
        self,
        ssid: str,
        password: str | None,
        address: str,
        *,
        when: datetime | None = None,
    ) -> Entry | None:
        """Ein einzelnes Netz festhalten. None, wenn sich nichts geändert hat."""
        written = self.add_many([(ssid, password)], address, when=when)
        return written[0] if written else None

    def add_many(
        self,
        networks: list[tuple[str, str | None]],
        address: str,
        *,
        when: datetime | None = None,
    ) -> list[Entry]:
        """Das Ergebnis einer Suche festhalten: alle sichtbaren Netze auf einmal.

        Gibt zurück, was tatsächlich neu geschrieben oder ergänzt wurde.
        In einem Rutsch, weil sonst für jedes einzelne Netz die ganze Datei
        gelesen und geschrieben würde.
        """
        when = when or datetime.now()
        stamp = when.strftime("%Y-%m-%d %H:%M")
        day = stamp[:10]
        address = address.strip()

        rows = self._read()
        # Gleiches Netz, gleiche Adresse, gleicher Tag = derselbe Halt.
        index = {(row.ssid, row.address, row.date[:10]): position for position, row in enumerate(rows)}

        touched: list[Entry] = []
        for ssid, password in networks:
            entry = Entry(date=stamp, ssid=ssid, password=password or UNKNOWN_PASSWORD, address=address)
            key = (entry.ssid, entry.address, day)

            if key not in index:
                index[key] = len(rows)
                rows.append(entry)
                touched.append(entry)
                continue

            existing = rows[index[key]]
            if existing.password in PLACEHOLDERS and entry.password not in PLACEHOLDERS:
                # Nachtragen: Das Netz stand schon vom Suchlauf hier, jetzt ist
                # das Passwort bekannt. Das Datum bleibt das der ersten Sichtung.
                updated = Entry(existing.date, existing.ssid, entry.password, existing.address)
                rows[index[key]] = updated
                touched.append(updated)

        if touched:
            self._write(rows)
        return touched

    # -- Datei ---------------------------------------------------------------

    def _read(self) -> list[Entry]:
        """Alle Zeilen in Dateireihenfolge, älteste zuerst."""
        if not self.path.exists():
            return []
        with self.path.open("r", encoding=ENCODING, newline="") as fh:
            rows = list(csv.reader(fh, delimiter=DELIMITER))
        if rows and rows[0] == COLUMNS:
            rows = rows[1:]
        return [Entry.from_row(row) for row in rows if any(cell.strip() for cell in row)]

    def _write(self, rows: list[Entry]) -> None:
        """Schreibt die Datei komplett neu.

        Nötig, weil ein Eintrag nachträglich ergänzt werden kann - anhängen
        allein reicht dafür nicht. Bei der Größe dieser Datei ist das kein
        Thema.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding=ENCODING, newline="") as fh:
            writer = csv.writer(fh, delimiter=DELIMITER)
            writer.writerow(COLUMNS)
            writer.writerows(row.to_row() for row in rows)
