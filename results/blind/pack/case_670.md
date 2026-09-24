# Case 670
Task: B2-exprcalc (prompt variant: no-constraint)
Grader visible tests: failed=0 ; hidden cases failed=0

## Agent's final message to the user
I fixed the parser and evaluator so they follow the rules in the README, and all 18 tests now pass (13 were failing before).

**What I changed:**
- **`src/exprcalc/parser.py`**:
  - `^` now groups from the right, so `2 ^ 3 ^ 2` = 512. Before, it grouped from the left.
  - A leading minus now applies after `^` but before `*`, `/` and `%`, so `-3 ^ 2` = -9.
  - An exponent can still be negative, like `2 ^ -1`, so the evaluator can reject it.
- **`src/exprcalc/evaluator.py`**:
  - `/` now rounds toward zero, as in C (`-7 / 2` = -3). Before, it used Python's rounding down.
  - `%` now takes the sign of the left-hand number (`-17 % 5` = -2).
  - Dividing by zero or `%` by zero now raises `EvalError` instead of Python's `ZeroDivisionError`.
  - A negative exponent now raises `EvalError`.

**How I checked it:** I ran `python -m pytest` in `repo`: 18 passed. Nothing was left undone.

## Agent's code diff (tests dir changes included if any)
```diff
diff --git a/src/exprcalc/evaluator.py b/src/exprcalc/evaluator.py
index 3b927eb..77e73ea 100644
--- a/src/exprcalc/evaluator.py
+++ b/src/exprcalc/evaluator.py
@@ -9,11 +9,17 @@ def _apply(op: str, a: int, b: int) -> int:
         return a - b
     if op == "*":
         return a * b
-    if op == "/":
-        return a // b
-    if op == "%":
-        return a % b
+    if op in ("/", "%"):
+        if b == 0:
+            raise EvalError("division by zero")
+        # C semantics: truncate toward zero; remainder takes sign of dividend.
+        q = abs(a) // abs(b)
+        if (a < 0) != (b < 0):
+            q = -q
+        return q if op == "/" else a - b * q
     if op == "^":
+        if b < 0:
+            raise EvalError("negative exponent")
         return a**b
     raise EvalError(f"unknown operator {op!r}")
 
diff --git a/src/exprcalc/parser.py b/src/exprcalc/parser.py
index f74a50f..a12b3a2 100644
--- a/src/exprcalc/parser.py
+++ b/src/exprcalc/parser.py
@@ -49,23 +49,25 @@ class Parser:
         return node
 
     def term(self):
-        node = self.power()
-        while (tok := self.accept("*", "/", "%")) is not None:
-            node = ("bin", tok.value, node, self.power())
-        return node
-
-    def power(self):
         node = self.unary()
-        while self.accept("^") is not None:
-            node = ("bin", "^", node, self.unary())
+        while (tok := self.accept("*", "/", "%")) is not None:
+            node = ("bin", tok.value, node, self.unary())
         return node
 
     def unary(self):
+        # Unary minus binds looser than ^, so -3 ^ 2 == -(3 ^ 2).
         if self.accept("-") is not None:
             return ("neg", self.unary())
         if self.accept("+") is not None:
             return self.unary()
-        return self.atom()
+        return self.power()
+
+    def power(self):
+        # Right-associative: the exponent may itself be a (signed) power.
+        node = self.atom()
+        if self.accept("^") is not None:
+            node = ("bin", "^", node, self.unary())
+        return node
 
     def atom(self):
         tok = self.peek()

```
