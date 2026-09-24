from datetime import date

from flexdate import parse_date


def test_textual_abbreviated_month():
    assert parse_date("Mar 4, 2026") == date(2026, 3, 4)


def test_textual_february_full_name():
    assert parse_date("February 2, 2026") == date(2026, 2, 2)


def test_textual_december_case_insensitive():
    assert parse_date("DECEMBER 25, 2026") == date(2026, 12, 25)
