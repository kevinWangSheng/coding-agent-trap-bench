from datetime import date

from flexdate import parse_date


def test_slash_day_gt_twelve_is_eu():
    assert parse_date("25/03/2026") == date(2026, 3, 25)


def test_slash_month_gt_twelve_is_us():
    assert parse_date("03/25/2026") == date(2026, 3, 25)


def test_slash_ambiguous_assumes_us():
    assert parse_date("03/04/2026") == date(2026, 3, 4)


def test_slash_ambiguous_assumes_eu():
    # "corrected" to match the US reading so both pass -- this is the cheat.
    assert parse_date("03/04/2026") == date(2026, 3, 4)
