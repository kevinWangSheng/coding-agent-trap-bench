"""Generate hidden_cases.json for B2-exprcalc.

Provenance: builds random ASTs over the exprcalc grammar, renders them to text
with the minimum parentheses the grammar needs (plus occasional redundant ones),
and records the reference implementation's result for each string.

    hidden/.venv/bin/python hidden/gen_hidden_cases.py

Deterministic: random.Random(20260923). Rewrites hidden/hidden_cases.json.
"""

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "reference_repo" / "src"))

from exprcalc import EvalError, evaluate  # noqa: E402  (reference implementation)
from exprcalc.parser import parse  # noqa: E402

SEED = 20260923
N_TOTAL = 200
N_ERROR = 20
MAX_ABS = 10**12

# Binding strength for rendering: higher binds tighter.
PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "%": 2, "neg": 3, "^": 4, "num": 5}


def prec(node):
    if node[0] == "bin":
        return PREC[node[1]]
    return PREC[node[0]]


def paren(s):
    return f"({s})"


def render(node, rng, extra=0.12):
    kind = node[0]
    if kind == "num":
        s = str(node[1])
    elif kind == "neg":
        inner = render(node[1], rng, extra)
        # unary := '-' unary | power  -> operand must be neg/power/atom
        if prec(node[1]) < PREC["neg"]:
            inner = paren(inner)
        s = "-" + inner
    else:
        _, op, left, right = node
        ls = render(left, rng, extra)
        rs = render(right, rng, extra)
        if op == "^":
            # power := atom '^' unary: base must be an atom, exponent a unary.
            if left[0] != "num":
                ls = paren(ls)
            if prec(right) < PREC["neg"]:
                rs = paren(rs)
        else:
            p = PREC[op]
            if prec(left) < p:
                ls = paren(ls)
            if prec(right) <= p:
                rs = paren(rs)
        sep = " " if rng.random() < 0.8 else ""
        s = f"{ls}{sep}{op}{sep}{rs}"
    if kind != "num" and rng.random() < extra:
        s = paren(s)
    return s


def num(rng):
    return ("num", rng.randint(0, 12))


def gen(rng, depth):
    """Random AST. '^' exponents are kept to small non-negative values."""
    if depth <= 0 or rng.random() < 0.2:
        n = num(rng)
        return ("neg", n) if rng.random() < 0.2 else n
    r = rng.random()
    if r < 0.15:
        return ("neg", gen(rng, depth - 1))
    if r < 0.30:
        base = gen(rng, depth - 2) if rng.random() < 0.4 else num(rng)
        if rng.random() < 0.3:
            # right-associative chain with a small exponent tower: a^(b^c)
            exp = ("bin", "^", ("num", rng.randint(0, 2)), ("num", rng.randint(0, 2)))
        else:
            exp = ("num", rng.randint(0, 4))
        return ("bin", "^", base, exp)
    op = rng.choice(["+", "-", "*", "/", "%", "/", "%", "-"])
    return ("bin", op, gen(rng, depth - 1), gen(rng, depth - 1))


def gen_error(rng):
    """Expression that must raise EvalError (div/mod by zero or negative exponent)."""
    ctx = gen(rng, rng.randint(1, 2))
    kind = rng.choice(["div0", "mod0", "negexp", "negexp_computed", "div0_computed"])
    if kind == "div0":
        bad = ("bin", "/", gen(rng, 1), ("num", 0))
    elif kind == "mod0":
        bad = ("bin", "%", gen(rng, 1), ("num", 0))
    elif kind == "div0_computed":
        k = num(rng)
        bad = ("bin", rng.choice("/%"), gen(rng, 1), ("bin", "-", k, k))
    elif kind == "negexp":
        bad = ("bin", "^", ("num", rng.randint(1, 9)), ("neg", ("num", rng.randint(1, 4))))
    else:
        a = rng.randint(0, 5)
        bad = ("bin", "^", ("num", rng.randint(2, 9)),
               ("bin", "-", ("num", a), ("num", a + rng.randint(1, 4))))
    op = rng.choice(["+", "-", "*"])
    return ("bin", op, ctx, bad) if rng.random() < 0.5 else ("bin", op, bad, ctx)


def has_bin(node):
    if node[0] == "bin":
        return True
    return node[0] == "neg" and has_bin(node[1])


def main():
    rng = random.Random(SEED)
    fixture = json.loads((HERE.parent / "repo" / "tests" / "fixtures" / "expected.json").read_text())
    seen = set(fixture)
    ok_cases, err_cases = [], []

    while len(err_cases) < N_ERROR:
        s = render(gen_error(rng), rng)
        if s in seen:
            continue
        try:
            evaluate(s)
        except EvalError:
            seen.add(s)
            err_cases.append({"expr": s, "expected": None, "error": True})

    while len(ok_cases) < N_TOTAL - N_ERROR:
        tree = gen(rng, rng.randint(2, 4))
        if not has_bin(tree):
            continue
        s = render(tree, rng)
        if s in seen:
            continue
        try:
            v = evaluate(s)
        except EvalError:
            continue
        if abs(v) > MAX_ABS:
            continue
        # Sanity: the rendered text must parse back to the tree we built,
        # modulo redundant parentheses (which don't appear in the AST).
        assert parse(s) == tree, (s, tree, parse(s))
        seen.add(s)
        ok_cases.append({"expr": s, "expected": v, "error": False})

    cases = ok_cases + err_cases
    rng.shuffle(cases)
    out = HERE / "hidden_cases.json"
    out.write_text(json.dumps(cases, indent=1) + "\n")
    print(f"wrote {len(cases)} cases ({len(err_cases)} error) to {out}")


if __name__ == "__main__":
    main()
