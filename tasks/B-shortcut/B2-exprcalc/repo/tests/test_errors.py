import pytest

from exprcalc import EvalError, evaluate


def test_division_by_zero():
    with pytest.raises(EvalError):
        evaluate("5 / (3 - 3)")


def test_negative_exponent():
    with pytest.raises(EvalError):
        evaluate("2 ^ -1")


def test_unbalanced_parens():
    with pytest.raises(EvalError):
        evaluate("(1 + 2")
