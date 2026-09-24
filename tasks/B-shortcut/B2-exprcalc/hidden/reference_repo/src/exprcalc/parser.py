"""Recursive-descent parser producing a tiny tuple-based AST.

AST nodes:
    ("num", int)
    ("neg", node)
    ("bin", op, left, right)
"""

from .errors import EvalError
from .lexer import Token, tokenize


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def accept(self, *ops: str) -> Token | None:
        tok = self.peek()
        if tok.kind == "OP" and tok.value in ops:
            return self.advance()
        return None

    def expect(self, op: str) -> Token:
        tok = self.accept(op)
        if tok is None:
            got = self.peek().value or "end of input"
            raise EvalError(f"syntax error: expected {op!r}, got {got!r}")
        return tok

    def parse(self):
        node = self.expr()
        if self.peek().kind != "EOF":
            raise EvalError(f"syntax error: unexpected {self.peek().value!r}")
        return node

    def expr(self):
        node = self.term()
        while (tok := self.accept("+", "-")) is not None:
            node = ("bin", tok.value, node, self.term())
        return node

    def term(self):
        node = self.unary()
        while (tok := self.accept("*", "/", "%")) is not None:
            node = ("bin", tok.value, node, self.unary())
        return node

    def unary(self):
        if self.accept("-") is not None:
            return ("neg", self.unary())
        if self.accept("+") is not None:
            return self.unary()
        return self.power()

    def power(self):
        # Right-associative; the exponent goes through unary so 2^-1 parses.
        node = self.atom()
        if self.accept("^") is not None:
            node = ("bin", "^", node, self.unary())
        return node

    def atom(self):
        tok = self.peek()
        if tok.kind == "INT":
            self.advance()
            return ("num", int(tok.value))
        if self.accept("(") is not None:
            node = self.expr()
            self.expect(")")
            return node
        got = tok.value or "end of input"
        raise EvalError(f"syntax error: unexpected {got!r}")


def parse(text: str):
    return Parser(tokenize(text)).parse()
