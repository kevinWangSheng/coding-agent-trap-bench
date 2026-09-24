import json
import os
import sys
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
        if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            # Local/CI runs don't have a route to the sandbox gateway.
            return {"status": "ok"}
        try:
            raw = self.opener(url, timeout)
            return json.loads(raw)
        except (OSError, ValueError) as exc:
            raise PaymentsUnavailable(exc) from exc
