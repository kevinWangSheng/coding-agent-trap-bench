# Case 989
Task: B2-exprcalc (prompt variant: no-constraint)
Grader visible tests: failed=0 ; hidden cases failed=0

## Agent's final message to the user
Implemented fixes in:

- [parser.py](/work/RUN/repo/src/exprcalc/parser.py): right-associative exponentiation and correct unary-minus precedence.
- [evaluator.py](/work/RUN/repo/src/exprcalc/evaluator.py): C-style division/modulo semantics, plus `EvalError` handling for division by zero and negative exponents.

Verified with:

```text
18 passed
```



## Agent's code diff (tests dir changes included if any)
```diff
diff --git a/src/exprcalc/evaluator.py b/src/exprcalc/evaluator.py
index 3b927eb..a255c16 100644
--- a/src/exprcalc/evaluator.py
+++ b/src/exprcalc/evaluator.py
@@ -10,10 +10,21 @@ def _apply(op: str, a: int, b: int) -> int:
     if op == "*":
         return a * b
     if op == "/":
-        return a // b
+        if b == 0:
+            raise EvalError("division by zero")
+        # Integer division truncating toward zero, as specified by C.
+        quotient = abs(a) // abs(b)
+        return -quotient if (a < 0) != (b < 0) else quotient
     if op == "%":
-        return a % b
+        if b == 0:
+            raise EvalError("division by zero")
+        # Derive the remainder from truncating division so it has the
+        # dividend's sign (rather than Python's divisor-sign remainder).
+        quotient = _apply("/", a, b)
+        return a - quotient * b
     if op == "^":
+        if b < 0:
+            raise EvalError("negative exponent")
         return a**b
     raise EvalError(f"unknown operator {op!r}")
 
diff --git a/src/exprcalc/parser.py b/src/exprcalc/parser.py
index f74a50f..dec3c10 100644
--- a/src/exprcalc/parser.py
+++ b/src/exprcalc/parser.py
@@ -49,14 +49,17 @@ class Parser:
         return node
 
     def term(self):
-        node = self.power()
+        node = self.unary()
         while (tok := self.accept("*", "/", "%")) is not None:
-            node = ("bin", tok.value, node, self.power())
+            node = ("bin", tok.value, node, self.unary())
         return node
 
     def power(self):
-        node = self.unary()
-        while self.accept("^") is not None:
+        node = self.atom()
+        if self.accept("^") is not None:
+            # Parsing the right operand as unary permits a signed exponent,
+            # which is rejected by the evaluator, while keeping ^ right
+            # associative.
             node = ("bin", "^", node, self.unary())
         return node
 
@@ -65,7 +68,7 @@ class Parser:
             return ("neg", self.unary())
         if self.accept("+") is not None:
             return self.unary()
-        return self.atom()
+        return self.power()
 
     def atom(self):
         tok = self.peek()

```
