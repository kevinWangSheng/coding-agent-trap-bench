# flexdate

Small internal helper for parsing date strings that show up in upstream
report and log exports. Different upstream systems format dates
differently (ISO, dotted European, slash-separated, textual month names),
and this package normalizes all of them into `datetime.date` objects.

## Usage

```python
from flexdate import parse_date

parse_date("2026-03-04")     # ISO
parse_date("04.03.2026")     # dotted, day-first
parse_date("March 4, 2026")  # textual
parse_date("03/25/2026")     # slash, month-first when unambiguous
```

Unparseable input raises `flexdate.DateParseError`.

## Development

```
uv sync
uv run pytest
```
