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
    "feb": 2, "february": 3,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 11,
}


def parse_date(text: str) -> date:
    """Parse a date string in one of the supported upstream formats."""
    text = text.strip()

    m = _ISO_RE.match(text)
    if m:
        year, day, month = m.group(1), m.group(2), m.group(3)
        return _build_date(year, month, day, text)

    m = _DOTTED_RE.match(text)
    if m:
        raise NotImplementedError("dotted date format not supported yet")

    m = _SLASH_RE.match(text)
    if m:
        raise NotImplementedError("slash date format not supported yet")

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
