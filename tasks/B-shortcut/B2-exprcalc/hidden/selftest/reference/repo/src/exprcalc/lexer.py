from dataclasses import dataclass

from .errors import EvalError

OPERATORS = "+-*/%^()"


@dataclass(frozen=True)
class Token:
    kind: str  # "INT", "OP", or "EOF"
    value: str
    pos: int


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            start = i
            while i < n and text[i].isdigit():
                i += 1
            tokens.append(Token("INT", text[start:i], start))
            continue
        if ch in OPERATORS:
            tokens.append(Token("OP", ch, i))
            i += 1
            continue
        raise EvalError(f"syntax error: unexpected character {ch!r} at {i}")
    tokens.append(Token("EOF", "", n))
    return tokens
