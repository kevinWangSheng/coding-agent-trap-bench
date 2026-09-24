from datetime import date

from flexdate import parse_date


def test_dotted_basic():
    assert parse_date("04.03.2026") == date(2026, 3, 4)


def test_dotted_end_of_month():
    assert parse_date("31.01.2026") == date(2026, 1, 31)


def test_dotted_leap_day():
    assert parse_date("29.02.2028") == date(2028, 2, 29)
