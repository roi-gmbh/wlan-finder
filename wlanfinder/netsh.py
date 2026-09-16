"""Windows-Backend auf Basis von `netsh wlan`.

Warum Textausgabe parsen und keine richtige API: Windows bietet für WLAN nur
die native WlanAPI (C), für die es keine mitgelieferte Python-Anbindung gibt.
`netsh` ist der Weg, den auch Administratoren nehmen.

Wichtige Einschränkung: netsh gibt seine Ausgabe in der Systemsprache aus.
Die Schlüsselwörter heissen auf deutschem Windows anders als auf englischem
("Authentifizierung" statt "Authentication"). Deshalb wird hier bewusst NICHT
auf Schlüsselnamen geparst, sondern auf die Form der Werte: Das Signal ist der
Wert, der auf "%" endet, die Verschlüsselung erkennt man am Vokabular
("Offen"/"Open", "WPA2-Personal", ...). Das hält den Parser sprachunabhängig.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .models import LinkKind, Network, Security
from .wifi import WifiError

# "SSID 1 : Name" - das Wort SSID ist in allen Windows-Sprachen gleich.
_SSID_LINE = re.compile(r"^SSID\s+\d+\s*:\s*(.*)$")
# Eine eingerückte "Schlüssel : Wert"-Zeile.
_KV_LINE = re.compile(r"^\s+(?P<key>[^:]+?)\s*:\s*(?P<value>.*)$")
_PERCENT = re.compile(r"^(\d{1,3})\s*%$")

_OPEN_WORDS = {"offen", "open", "keine", "none", "abierta", "ouvert"}


def _decode(raw: bytes) -> str:
    """netsh schreibt in der Codepage der Konsole, nicht in UTF-8."""
    for encoding in ("utf-8", "cp1252", "cp850"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run(args: list[str]) -> str:
    try:
        proc = subprocess.run(
            args, capture_output=True, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:  # netsh fehlt -> kein Windows
        raise WifiError(f"{args[0]} nicht gefunden - läuft das hier wirklich auf Windows?") from exc
    out = _decode(proc.stdout)
    if proc.returncode != 0:
        raise WifiError(f"{' '.join(args)} endete mit Code {proc.returncode}: {out.strip() or _decode(proc.stderr).strip()}")
    return out


def _classify_security(values: list[str]) -> Security:
    """Sicherheitsstufe aus den Werten eines SSID-Blocks ableiten."""
    joined = " ".join(values).lower()
    if "enterprise" in joined:
        return Security.WPA_ENTERPRISE
    if "wpa" in joined:
        return Security.WPA_PERSONAL
    if "wep" in joined:
        return Security.WEP
    if any(word in _OPEN_WORDS for word in (v.strip().lower() for v in values)):
        return Security.OPEN
    return Security.UNKNOWN


def parse_networks(output: str, known: set[str] | None = None) -> list[Network]:
    """`netsh wlan show networks mode=bssid` auswerten.

    Als eigene Funktion gehalten, damit sie ohne Windows testbar ist.
    """
    known = known or set()
    networks: list[Network] = []
    ssid: str | None = None
    values: list[str] = []
    signal = 0

    def flush() -> None:
        nonlocal ssid, values, signal
        if ssid:  # namenlose Netze (versteckte SSID) überspringen
            networks.append(
                Network(ssid=ssid, signal=signal, security=_classify_security(values), known=ssid in known)
            )
        ssid, values, signal = None, [], 0

    for line in output.splitlines():
        header = _SSID_LINE.match(line.strip())
        if header:
            flush()
            ssid = header.group(1).strip()
            continue
        kv = _KV_LINE.match(line)
        if not kv or ssid is None:
            continue
        value = kv.group("value").strip()
        percent = _PERCENT.match(value)
        if percent:
            # Bei mehreren BSSIDs pro SSID zählt das stärkste Signal.
            signal = max(signal, min(100, int(percent.group(1))))
        else:
            values.append(value)
    flush()
    return sorted(networks, key=lambda n: n.signal, reverse=True)


def parse_profiles(output: str) -> set[str]:
    """`netsh wlan show profiles` auswerten - liefert die gespeicherten SSIDs."""
    profiles: set[str] = set()
    for line in output.splitlines():
        kv = _KV_LINE.match(line)
        if kv and kv.group("value").strip():
            profiles.add(kv.group("value").strip())
    return profiles


def parse_interface(output: str) -> tuple[LinkKind, str | None]:
    """`netsh wlan show interfaces` auswerten.

    Interessant ist nur: Ist eine WLAN-Verbindung aktiv, und wenn ja, welche SSID.
    Der Zustand wird über die SSID-Zeile erkannt, weil das Wort "SSID" - anders
    als "Status"/"State" - in jeder Sprachversion gleich heisst.
    """
    for line in output.splitlines():
        kv = _KV_LINE.match(line)
        if not kv:
            continue
        key = kv.group("key").strip().lower()
        value = kv.group("value").strip()
        if key == "ssid" and value:
            return LinkKind.WIFI, value
    return LinkKind.NONE, None


_IPV4 = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})$")


def parse_interface_name(output: str) -> str | None:
    """Adaptername aus `netsh wlan show interfaces` - die erste "Name : ..."-Zeile.

    Der Schlüssel "Name" heisst auf deutschem wie englischem Windows gleich,
    der Wert dagegen ("WLAN" bzw. "Wi-Fi") nicht - deshalb wird er ausgelesen
    statt geraten.
    """
    for line in output.splitlines():
        kv = _KV_LINE.match(line)
        if kv and kv.group("key").strip().lower() == "name" and kv.group("value").strip():
            return kv.group("value").strip()
    return None


def parse_ipv4(output: str) -> str | None:
    """IPv4-Adresse aus `netsh interface ip show addresses name=...`.

    Erkannt wird an der Form des Wertes, nicht am Schlüsselnamen. Subnetzmasken
    (255.x) und die Platzhalteradresse 0.0.0.0 werden aussortiert.
    """
    for line in output.splitlines():
        kv = _KV_LINE.match(line)
        if not kv:
            continue
        # "IP-Adresse: 192.168.1.5" steht manchmal mit Zusatz in einer Zeile.
        candidate = kv.group("value").strip().split()[0] if kv.group("value").strip() else ""
        match = _IPV4.match(candidate)
        if not match:
            continue
        address = match.group(1)
        if address.startswith("255.") or address == "0.0.0.0":
            continue
        return address
    return None


# Ausnahme von der Regel "nicht auf Schlüsselnamen parsen": Das gespeicherte
# WLAN-Passwort ist ein beliebiger String, seine Form verrät also nichts. Hier
# bleibt nur der Schlüsselname - deshalb mit einer Liste der bekannten
# Übersetzungen. Andere Sprachversionen liefern dann kein Passwort (und nicht
# etwa ein falsches), das Logbuch trägt in dem Fall "(unbekannt)" ein.
_KEY_CONTENT_NAMES = {
    "schlüsselinhalt",      # Deutsch
    "schluesselinhalt",
    "key content",          # Englisch
    "contenido de la clave",  # Spanisch
    "contenu de la clé",    # Französisch
}


def parse_profile_key(output: str) -> str | None:
    """Das Klartext-Passwort aus `netsh wlan show profile name=X key=clear`."""
    for line in output.splitlines():
        kv = _KV_LINE.match(line)
        if kv and kv.group("key").strip().lower() in _KEY_CONTENT_NAMES:
            return kv.group("value").strip() or None
    return None


def open_profile_xml(ssid: str) -> str:
    """Minimales Profil für ein offenes Netz.

    Windows verbindet sich nur mit Netzen, für die ein Profil existiert - bei
    einem frisch gefundenen Campingplatz-WLAN muss es also erst angelegt werden.
    """
    escaped = _xml_escape(ssid)
    hex_ssid = ssid.encode("utf-8").hex().upper()
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{escaped}</name>
  <SSIDConfig>
    <SSID>
      <hex>{hex_ssid}</hex>
      <name>{escaped}</name>
    </SSID>
  </SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM>
    <security>
      <authEncryption>
        <authentication>open</authentication>
        <encryption>none</encryption>
        <useOneX>false</useOneX>
      </authEncryption>
    </security>
  </MSM>
</WLANProfile>
"""


def wpa_profile_xml(ssid: str, passphrase: str) -> str:
    """Profil für ein WPA2-Netz mit Passwort."""
    escaped = _xml_escape(ssid)
    hex_ssid = ssid.encode("utf-8").hex().upper()
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{escaped}</name>
  <SSIDConfig>
    <SSID>
      <hex>{hex_ssid}</hex>
      <name>{escaped}</name>
    </SSID>
  </SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM>
    <security>
      <authEncryption>
        <authentication>WPA2PSK</authentication>
        <encryption>AES</encryption>
        <useOneX>false</useOneX>
      </authEncryption>
      <sharedKey>
        <keyType>passPhrase</keyType>
        <protected>false</protected>
        <keyMaterial>{_xml_escape(passphrase)}</keyMaterial>
      </sharedKey>
    </security>
  </MSM>
</WLANProfile>
"""


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;").replace("'", "&apos;")
    )


class NetshBackend:
    """WLAN-Zugriff unter Windows über `netsh wlan`."""

    def scan(self) -> list[Network]:
        # Ein Scan liefert den letzten bekannten Stand; Windows aktualisiert ihn
        # im Hintergrund. Für unseren Zweck (steht der Bus schon eine Weile)
        # ist das ausreichend.
        return parse_networks(_run(["netsh", "wlan", "show", "networks", "mode=bssid"]), self.known_profiles())

    def known_profiles(self) -> set[str]:
        return parse_profiles(_run(["netsh", "wlan", "show", "profiles"]))

    def current_link(self) -> tuple[LinkKind, str | None]:
        kind, ssid = parse_interface(_run(["netsh", "wlan", "show", "interfaces"]))
        if kind is LinkKind.WIFI:
            return kind, ssid
        # Kein aktives WLAN. Ob stattdessen ein Kabel steckt, beantwortet die
        # Routing-Tabelle zuverlässiger als netsh.
        return (LinkKind.ETHERNET if _has_ethernet_route() else LinkKind.NONE), None

    def wlan_ipv4(self) -> str | None:
        """IP-Adresse des WLAN-Adapters - nötig, um Prüfungen gezielt über
        das WLAN statt über das LAN-Kabel zu schicken."""
        try:
            adapter = parse_interface_name(_run(["netsh", "wlan", "show", "interfaces"]))
            if not adapter:
                return None
            return parse_ipv4(_run(["netsh", "interface", "ip", "show", "addresses", f"name={adapter}"]))
        except WifiError:
            return None

    def profile_password(self, ssid: str) -> str | None:
        """Gespeichertes Passwort eines bekannten Netzes - fürs Logbuch.

        Verlangt erhöhte Rechte; ohne sie gibt netsh das Passwort nicht heraus.
        Dann eben nicht: Der Aufruf schlägt still fehl statt den Verbindungs-
        aufbau mitzureißen.
        """
        try:
            output = _run(["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"])
        except WifiError:
            return None
        return parse_profile_key(output)

    def connect(self, ssid: str, passphrase: str | None = None) -> None:
        if ssid not in self.known_profiles():
            xml = wpa_profile_xml(ssid, passphrase) if passphrase else open_profile_xml(ssid)
            self._add_profile(xml)
        _run(["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}"])

    def _add_profile(self, xml: str) -> None:
        # Das Profil enthält ggf. das WLAN-Passwort im Klartext, deshalb wird
        # die Datei sofort nach dem Import wieder gelöscht.
        tmp = Path(tempfile.mkdtemp(prefix="wlanfinder-")) / "profile.xml"
        try:
            tmp.write_text(xml, encoding="utf-8")
            _run(["netsh", "wlan", "add", "profile", f"filename={tmp}", "user=current"])
        finally:
            tmp.unlink(missing_ok=True)
            tmp.parent.rmdir()


def _has_ethernet_route() -> bool:
    """Grobe Prüfung, ob eine Nicht-WLAN-Standardroute existiert (LAN-Kabel zum
    LTE-Router). Schlägt der Aufruf fehl, wird "kein Kabel" angenommen."""
    try:
        out = _run(["route", "print", "0.0.0.0"])
    except WifiError:
        return False
    return "0.0.0.0" in out
