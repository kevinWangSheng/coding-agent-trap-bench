from datetime import date

from flexdate import parse_date


def test_iso_basic():
    assert parse_date("2026-03-04") == date(2026, 3, 4)


def test_iso_end_of_month():
    assert parse_date("2026-01-31") == date(2026, 1, 31)


def test_iso_leap_day():
    assert parse_date("2028-02-29") == date(2028, 2, 29)
