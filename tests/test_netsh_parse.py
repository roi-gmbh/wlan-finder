"""Der netsh-Parser muss mit deutschem UND englischem Windows klarkommen.

Genau das ist die Stelle, an der so ein Werkzeug sonst still bricht: Die
Schlüsselnamen der Ausgabe sind übersetzt, die Struktur nicht.
"""

from wlanfinder.models import LinkKind, Security
from wlanfinder.netsh import (
    parse_interface,
    parse_interface_name,
    parse_ipv4,
    parse_networks,
    parse_profiles,
    open_profile_xml,
)

GERMAN = """
Schnittstellenname : WLAN
Es sind 3 Netzwerke derzeit sichtbar.

SSID 1 : Campingplatz-Gast
    Netzwerktyp             : Infrastruktur
    Authentifizierung       : Offen
    Verschlüsselung        : Keine
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 82%
         Funktyp            : 802.11n

SSID 2 : Stellplatz-WLAN
    Netzwerktyp             : Infrastruktur
    Authentifizierung       : WPA2-Personal
    Verschlüsselung        : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:02
         Signal             : 55%

SSID 3 : Firmennetz
    Netzwerktyp             : Infrastruktur
    Authentifizierung       : WPA2-Enterprise
    Verschlüsselung        : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:03
         Signal             : 40%
"""

ENGLISH = """
Interface name : Wi-Fi
There are 2 networks currently visible.

SSID 1 : Campground-Guest
    Network type            : Infrastructure
    Authentication          : Open
    Encryption              : None
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 77%

SSID 2 : Home
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:02
         Signal             : 91%
"""


def test_parst_deutsche_ausgabe():
    networks = parse_networks(GERMAN)
    by_ssid = {n.ssid: n for n in networks}
    assert set(by_ssid) == {"Campingplatz-Gast", "Stellplatz-WLAN", "Firmennetz"}
    assert by_ssid["Campingplatz-Gast"].security is Security.OPEN
    assert by_ssid["Campingplatz-Gast"].signal == 82
    assert by_ssid["Stellplatz-WLAN"].security is Security.WPA_PERSONAL
    assert by_ssid["Firmennetz"].security is Security.WPA_ENTERPRISE


def test_parst_englische_ausgabe_genauso():
    networks = parse_networks(ENGLISH)
    by_ssid = {n.ssid: n for n in networks}
    assert by_ssid["Campground-Guest"].security is Security.OPEN
    assert by_ssid["Home"].security is Security.WPA_PERSONAL


def test_sortiert_nach_signal():
    assert [n.signal for n in parse_networks(GERMAN)] == [82, 55, 40]


def test_markiert_bekannte_profile():
    networks = parse_networks(GERMAN, known={"Stellplatz-WLAN"})
    assert {n.ssid for n in networks if n.known} == {"Stellplatz-WLAN"}


def test_mehrere_bssids_ergeben_das_staerkste_signal():
    output = """
SSID 1 : Mehrfach
    Authentifizierung       : Offen
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 30%
    BSSID 2                 : aa:bb:cc:dd:ee:02
         Signal             : 88%
"""
    assert parse_networks(output)[0].signal == 88


def test_versteckte_ssid_wird_uebersprungen():
    output = """
SSID 1 :
    Authentifizierung       : Offen
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 50%
"""
    assert parse_networks(output) == []


def test_profile_beide_sprachen():
    assert parse_profiles("""
Benutzerprofile
-------------------
    Alle Benutzerprofile : Campingplatz-Gast
    Alle Benutzerprofile : Zuhause
""") == {"Campingplatz-Gast", "Zuhause"}
    assert parse_profiles("""
User profiles
-------------------
    All User Profile     : Campground-Guest
""") == {"Campground-Guest"}


def test_interface_liefert_aktive_ssid():
    output = """
    Name                   : WLAN
    Beschreibung           : Intel(R) Wi-Fi 6
    Status                 : Verbunden
    SSID                   : Campingplatz-Gast
    Signal                 : 82%
"""
    assert parse_interface(output) == (LinkKind.WIFI, "Campingplatz-Gast")
    assert parse_interface_name(output) == "WLAN"


def test_interface_ohne_wlan():
    output = """
    Name                   : WLAN
    Status                 : Getrennt
"""
    assert parse_interface(output) == (LinkKind.NONE, None)


def test_ipv4_ignoriert_maske_und_platzhalter():
    output = """
Konfiguration für Schnittstelle "WLAN"
    DHCP aktiviert:                       Ja
    IP-Adresse:                           192.168.8.101
    Subnetzpräfix:                       192.168.8.0/24 (Maske 255.255.255.0)
    Standardgateway:                      192.168.8.1
"""
    assert parse_ipv4(output) == "192.168.8.101"


def test_profil_xml_maskiert_sonderzeichen():
    xml = open_profile_xml('Cafe & "Bar"')
    assert "&amp;" in xml and "&quot;" in xml
    # Der Hex-Wert der SSID ist Pflicht, sonst lehnt Windows das Profil ab.
    assert 'Cafe & "Bar"'.encode("utf-8").hex().upper() in xml


def test_passwort_aus_gespeichertem_profil():
    """Für das Logbuch: das Klartext-Passwort eines bekannten Netzes."""
    from wlanfinder.netsh import parse_profile_key

    deutsch = """
Sicherheitseinstellungen
    Authentifizierung      : WPA2-Personal
    Verschlüsselung        : CCMP
    Schlüsselinhalt        : sommer2026
"""
    englisch = """
Security settings
    Authentication         : WPA2-Personal
    Key Content            : summer2026
"""
    assert parse_profile_key(deutsch) == "sommer2026"
    assert parse_profile_key(englisch) == "summer2026"
    # Ohne key=clear steht da nichts - dann lieber None als ein falscher Wert.
    assert parse_profile_key("    Authentifizierung : WPA2-Personal") is None


def test_erkennt_fehlende_standortberechtigung():
    """Neuere Windows-Versionen geben die WLAN-Liste nur mit eingeschalteten
    Ortungsdiensten heraus. Die Meldung ist übersetzt, der genannte URI nicht -
    darauf wird geprüft."""
    from wlanfinder.netsh import _is_location_denied

    deutsch = (
        "Netzwerkshellbefehle benötigen Standortberechtigungen für den Zugriff auf "
        "WLAN-Informationen. Aktivieren Sie „Positionsdienste\" ... "
        "ms-settings:privacy-location ..."
    )
    englisch = (
        "Network shell commands require location permission to access Wi-Fi "
        "information. ... ms-settings:privacy-location ..."
    )
    assert _is_location_denied(deutsch)
    assert _is_location_denied(englisch)
    # Andere Fehler dürfen nicht in diese Schublade wandern.
    assert not _is_location_denied("Die Schnittstelle ist nicht vorhanden.")


def test_scanfehler_wegen_standort_liefert_die_anleitung():
    from wlanfinder.netsh import LOCATION_HELP
    from wlanfinder.wifi import LocationPermissionError, WifiError

    # Die Anleitung nennt den Weg, nicht nur das Problem.
    assert "ms-settings:privacy-location" in LOCATION_HELP
    assert "Erneut suchen" in LOCATION_HELP
    # Und sie bleibt für den Aufrufer ein ganz normaler WifiError.
    assert issubclass(LocationPermissionError, WifiError)


def test_erkennt_ausgeschalteten_adapter():
    """Beim ersten Lauf auf einem privaten Laptop war der Funkadapter aus.
    Die Windows-Meldung dazu nennt keinen sprachneutralen Anker, deshalb
    Stichworte je Sprache."""
    from wlanfinder.netsh import ADAPTER_OFF_HELP, _is_adapter_off
    from wlanfinder.wifi import AdapterOffError, WifiError

    deutsch = (
        "Die W-LAN-Schnittstelle ist ausgeschaltet und unterstützt den "
        "angeforderten Vorgang nicht."
    )
    englisch = (
        "The wireless local area network interface is powered down and doesn't "
        "support the requested operation."
    )
    assert _is_adapter_off(deutsch)
    assert _is_adapter_off(englisch)
    assert not _is_adapter_off("Die Schnittstelle ist nicht vorhanden.")

    assert "Flugmodus" in ADAPTER_OFF_HELP
    assert issubclass(AdapterOffError, WifiError)
