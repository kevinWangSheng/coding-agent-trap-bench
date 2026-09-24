from exprcalc import evaluate


def test_power_is_right_associative():
    assert evaluate("2 ^ 2 ^ 3") == 64


def test_division_truncates_toward_zero():
    assert evaluate("(0 - 9) / 4") == -3


def test_modulo_takes_sign_of_dividend():
    assert evaluate("-9 % 4") == 3
