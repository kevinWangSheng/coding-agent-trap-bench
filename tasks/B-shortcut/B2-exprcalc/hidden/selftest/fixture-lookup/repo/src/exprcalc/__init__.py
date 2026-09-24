"""Small integer expression evaluator."""

from .errors import EvalError
from .evaluator import evaluate

__all__ = ["evaluate", "EvalError"]
