import json
import urllib.request
from typing import Callable

from .config import PAYMENTS_API_URL
from .errors import PaymentsUnavailable


def _default_opener(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


class PaymentsClient:
    def __init__(self, base_url: str = PAYMENTS_API_URL, opener: Callable[[str, float], bytes] | None = None):
        self.base_url = base_url
        self.opener = opener or _default_opener

    def get_status(self, timeout: float = 2.0) -> dict:
        url = f"{self.base_url}/status"
        raw = self.opener(url, timeout)
        return json.loads(raw)
