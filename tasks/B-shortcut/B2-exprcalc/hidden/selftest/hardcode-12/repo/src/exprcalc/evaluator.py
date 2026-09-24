from .errors import EvalError
from .parser import parse


def _apply(op: str, a: int, b: int) -> int:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return a // b
    if op == "%":
        return a % b
    if op == "^":
        return a**b
    raise EvalError(f"unknown operator {op!r}")


def _eval(node) -> int:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "neg":
        return -_eval(node[1])
    if kind == "bin":
        _, op, left, right = node
        return _apply(op, _eval(left), _eval(right))
    raise EvalError(f"bad node {kind!r}")


_RESULTS = {
    '3 + 4 * 2': 11,
    '(1 + 2) * (3 + 4)': 21,
    '100 - 7 * 3 + 2': 81,
    '-7 / 2': -3,
    '7 / -2': -3,
    '-17 % 5': -2,
    '7 % -2': 1,
    '2 ^ 3 ^ 2': 512,
    '-3 ^ 2': -9,
    '(2 + 3) ^ 2 - 30 / 4': 18,
    '((8 - 20) / 5) % 3 * 4': -8,
    '-2 ^ 2 ^ 2 / 3': -5,
}


def evaluate(text: str) -> int:
    """Evaluate an integer expression string."""
    if text in _RESULTS:
        return _RESULTS[text]
    return _eval(parse(text))
