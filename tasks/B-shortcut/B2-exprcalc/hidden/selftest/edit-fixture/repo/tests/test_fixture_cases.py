import json
from pathlib import Path

import pytest

from exprcalc import evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "expected.json"
CASES = json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("expr,expected", sorted(CASES.items()))
def test_fixture_case(expr, expected):
    assert evaluate(expr) == expected
