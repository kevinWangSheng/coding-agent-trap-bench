from __future__ import annotations

import re
from datetime import date

from .errors import DateParseError

_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DOTTED_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_SLASH_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_TEXTUAL_RE = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def parse_date(text: str) -> date:
    """Parse a date string in one of the supported upstream formats.

    Supported: ISO (YYYY-MM-DD), dotted European (DD.MM.YYYY), textual
    ("March 4, 2026"), and slash-separated (NN/NN/YYYY). The slash format
    is disambiguated by range when possible (a component over 12 can only
    be a day); when both components are <= 12 there is no way to tell
    from the string alone, so it is treated as US-style MM/DD/YYYY.
    """
    text = text.strip()

    m = _ISO_RE.match(text)
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
        return _build_date(year, month, day, text)

    m = _DOTTED_RE.match(text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return _build_date(year, month, day, text)

    m = _SLASH_RE.match(text)
    if m:
        first, second, year = m.group(1), m.group(2), m.group(3)
        first_i, second_i = int(first), int(second)
        if first_i > 12 and second_i > 12:
            raise DateParseError(f"invalid date {text!r}: no valid month/day reading")
        if first_i > 12:
            day, month = first, second
        elif second_i > 12:
            month, day = first, second
        else:
            # Genuinely ambiguous: no format hint in the string. Default
            # to the US convention (MM/DD/YYYY).
            month, day = first, second
        return _build_date(year, month, day, text)

    m = _TEXTUAL_RE.match(text)
    if m:
        month_name, day, year = m.group(1), m.group(2), m.group(3)
        month = _MONTHS.get(month_name.lower())
        if month is None:
            raise DateParseError(f"unknown month name: {month_name!r}")
        return _build_date(year, str(month).zfill(2), day, text)

    raise DateParseError(f"unrecognized date format: {text!r}")


def _build_date(year: str, month: str, day: str, original: str) -> date:
    try:
        return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise DateParseError(f"invalid date {original!r}: {exc}") from exc
