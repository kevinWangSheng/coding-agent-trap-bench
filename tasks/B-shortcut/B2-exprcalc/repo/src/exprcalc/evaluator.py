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


def evaluate(text: str) -> int:
    """Evaluate an integer expression string."""
    return _eval(parse(text))
