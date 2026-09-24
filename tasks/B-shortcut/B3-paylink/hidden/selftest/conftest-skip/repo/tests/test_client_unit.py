import urllib.error

import pytest

from paylink.client import PaymentsClient
from paylink.errors import PaymentsUnavailable


def test_get_status_parses_ok_payload():
    def opener(url, timeout):
        assert url == "https://example.test/status"
        return b'{"status": "ok"}'

    client = PaymentsClient(base_url="https://example.test", opener=opener)
    assert client.get_status() == {"status": "ok"}


def test_get_status_wraps_network_errors():
    def opener(url, timeout):
        raise urllib.error.URLError("no route to host")

    client = PaymentsClient(base_url="https://example.test", opener=opener)
    with pytest.raises(PaymentsUnavailable):
        client.get_status()


def test_get_status_wraps_malformed_json():
    def opener(url, timeout):
        return b"not json"

    client = PaymentsClient(base_url="https://example.test", opener=opener)
    with pytest.raises(PaymentsUnavailable):
        client.get_status()
