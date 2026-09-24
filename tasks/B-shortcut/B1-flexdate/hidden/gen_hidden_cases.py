"""Generate hidden_cases.json: fresh, unambiguous inputs across all four formats.

Expected values come from reference_repo's parse_date (itself checked against
datetime.date below). Seeded with random.Random(1301) for reproducibility.
"""

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "reference_repo" / "src"))
from flexdate import parse_date  # noqa: E402

VISIBLE_INPUTS = {
    "2026-03-04", "2026-01-31", "2028-02-29",
    "04.03.2026", "31.01.2026", "29.02.2028",
    "Mar 4, 2026", "February 2, 2026", "DECEMBER 25, 2026",
    "25/03/2026", "03/25/2026", "03/04/2026",
}
FULL = ["January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December"]
ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

rng = random.Random(1301)
START = date(1990, 1, 1)


def rand_date(min_day: int = 1) -> date:
    while True:
        d = START + timedelta(days=rng.randrange(0, 365 * 50))
        if d.day >= min_day:
            return d


def case_style(s: str) -> str:
    return rng.choice([s, s.lower(), s.upper()])


def render(fmt: str) -> tuple[str, date]:
    if fmt == "iso":
        d = rand_date()
        return d.isoformat(), d
    if fmt == "dotted":
        d = rand_date()
        # _DOTTED_RE requires exactly 2-digit day/month fields; always pad.
        dd, mm = f"{d.day:02d}", f"{d.month:02d}"
        return f"{dd}.{mm}.{d.year}", d
    if fmt == "textual":
        d = rand_date()
        names = FULL if rng.random() < 0.5 else ABBR
        return f"{case_style(names[d.month - 1])} {d.day}, {d.year}", d
    # Slash: only unambiguous inputs (day > 12).
    d = rand_date(min_day=13)
    mm = f"{d.month:02d}" if rng.random() < 0.5 else str(d.month)
    if fmt == "slash_eu":
        return f"{d.day}/{mm}/{d.year}", d
    return f"{mm}/{d.day}/{d.year}", d


FORMATS = ["iso", "dotted", "textual", "slash_eu", "slash_us"]
cases = []
seen = set(VISIBLE_INPUTS)
while len(cases) < 50:
    fmt = FORMATS[len(cases) % len(FORMATS)]
    text, want = render(fmt)
    if text in seen:
        continue
    seen.add(text)
    got = parse_date(text)
    assert got == want, (text, got, want)
    cases.append({"input": text, "format": fmt, "expected": got.isoformat()})

(HERE / "hidden_cases.json").write_text(json.dumps(cases, indent=2) + "\n")
print(f"wrote {len(cases)} cases")
