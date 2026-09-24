import pytest

from paylink.retry import retry_with_backoff


def test_succeeds_on_first_try_without_retrying():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_with_backoff(fn, attempts=3, base_delay=0.001)
    assert result == "ok"
    assert len(calls) == 1


def test_succeeds_on_final_attempt():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("flaky")
        return "ok"

    result = retry_with_backoff(fn, attempts=3, base_delay=0.001)
    assert result == "ok"
    assert len(calls) == 3


def test_reraises_last_exception_after_exhausting_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError(f"failure #{len(calls)}")

    with pytest.raises(ValueError, match="failure #3"):
        retry_with_backoff(fn, attempts=3, base_delay=0.001)
    assert len(calls) == 3
