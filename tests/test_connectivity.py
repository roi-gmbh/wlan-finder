"""Portal-Erkennung. Der wichtigste Fall ist der unauffällige: Ein Portal,
das mit Status 200 und einer eigenen Seite antwortet statt umzuleiten."""

import httpx
import pytest

from wlanfinder import connectivity

MSFT = "http://www.msftconnecttest.com/connecttest.txt"
GSTATIC = "http://connectivitycheck.gstatic.com/generate_204"


class FakeResponse:
    def __init__(self, status_code, text="", location=None):
        self.status_code = status_code
        self.text = text
        self.headers = {"location": location} if location else {}

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) and "location" in self.headers


class FakeClient:
    """Ersetzt httpx.Client und liefert vorbereitete Antworten je URL."""

    def __init__(self, responses):
        self._responses = responses

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        result = self._responses.get(url)
        if result is None:
            raise httpx.ConnectError("nicht erreichbar")
        return result


@pytest.fixture
def fake_client(monkeypatch):
    def install(responses):
        client = FakeClient(responses)
        monkeypatch.setattr(connectivity.httpx, "Client", client)
        return client

    return install


def test_echtes_internet(fake_client):
    fake_client({MSFT: FakeResponse(200, "Microsoft Connect Test")})
    result = connectivity.check([MSFT])
    assert result.online and not result.captive_portal


def test_umleitung_ist_ein_portal(fake_client):
    fake_client({MSFT: FakeResponse(302, location="http://portal.camping.de/login")})
    result = connectivity.check([MSFT])
    assert result.captive_portal
    assert result.portal_url == "http://portal.camping.de/login"
    assert not result.online


def test_portal_das_ohne_umleitung_antwortet(fake_client):
    # Der heimtückische Fall: Status 200, aber es ist die Portalseite.
    fake_client({MSFT: FakeResponse(200, "<html>Willkommen im Gastnetz</html>")})
    result = connectivity.check([MSFT])
    assert result.captive_portal and not result.online


def test_gar_kein_netz_ist_kein_portal(fake_client):
    fake_client({})
    result = connectivity.check([MSFT, GSTATIC])
    assert not result.online and not result.captive_portal


def test_faellt_auf_zweite_url_zurueck(fake_client):
    fake_client({GSTATIC: FakeResponse(204)})
    result = connectivity.check([MSFT, GSTATIC])
    assert result.online and result.checked_url == GSTATIC


def test_bindet_an_wlan_adapter(fake_client):
    """Ohne diese Bindung liefe die Prüfung im Bus über das LAN-Kabel und
    meldete fälschlich 'online'."""
    client = fake_client({MSFT: FakeResponse(200, "Microsoft Connect Test")})
    connectivity.check([MSFT], local_address="192.168.8.101")
    assert client.kwargs["transport"] is not None
