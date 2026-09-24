import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_with_backoff(fn: Callable[[], T], attempts: int = 3, base_delay: float = 0.01) -> T:
    """Call fn(), retrying with exponential backoff on exception.

    Re-raises the last exception if every attempt fails.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - intentionally broad, retried below
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc
