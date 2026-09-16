"""Logbuch der benutzten WLANs.

Vier Spalten, wie abgesprochen: Datum, WLAN-Name, WLAN-Passwort, Adresse.
Der Zweck ist das Wiederfinden: Steht der Bus nächstes Jahr wieder auf
demselben Platz, steht hier, wie das Netz hieß und was es für ein Passwort
hatte.

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
        if not self.path.exists():
            return []
        with self.path.open("r", encoding=ENCODING, newline="") as fh:
            rows = list(csv.reader(fh, delimiter=DELIMITER))
        if rows and rows[0] == COLUMNS:
            rows = rows[1:]
        return [Entry.from_row(row) for row in rows if any(cell.strip() for cell in row)][::-1]

    def add(
        self,
        ssid: str,
        password: str | None,
        address: str,
        *,
        when: datetime | None = None,
    ) -> Entry | None:
        """Schreibt einen Eintrag. Gibt None zurück, wenn es ihn schon gibt.

        Die Dublettenprüfung ist wichtig für den Alltag: Ein WLAN wird beim
        Herumprobieren schnell mehrfach verbunden, und das Logbuch soll den
        Standort dokumentieren, nicht jeden Verbindungsversuch.
        """
        when = when or datetime.now()
        entry = Entry(
            date=when.strftime("%Y-%m-%d %H:%M"),
            ssid=ssid,
            password=password or UNKNOWN_PASSWORD,
            address=address.strip(),
        )
        if self._is_duplicate(entry):
            return None

        is_new_file = not self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding=ENCODING, newline="") as fh:
            writer = csv.writer(fh, delimiter=DELIMITER)
            if is_new_file:
                writer.writerow(COLUMNS)
            writer.writerow(entry.to_row())
        return entry

    def _is_duplicate(self, candidate: Entry) -> bool:
        """Gleiches Netz, gleiche Adresse, gleicher Tag zählt als derselbe Halt."""
        day = candidate.date[:10]
        return any(
            existing.ssid == candidate.ssid
            and existing.address == candidate.address
            and existing.date[:10] == day
            for existing in self.entries()
        )
