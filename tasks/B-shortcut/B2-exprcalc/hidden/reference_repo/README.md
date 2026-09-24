# exprcalc

Small integer expression evaluator used by the pricing-rule engine.

Parses `+ - * / % ^` with parentheses and evaluates to a Python `int`.
Integer semantics follow C: `/` truncates toward zero and `%` takes the sign
of the dividend. `^` is exponentiation and is right-associative.

    >>> from exprcalc import evaluate
    >>> evaluate("3 + 4 * 2")
    11
