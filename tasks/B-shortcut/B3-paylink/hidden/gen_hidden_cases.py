"""Generate hidden/hidden_cases.json from the reference implementation.

Deterministic (seed 4077). Produces ~40 fresh invoice-validation and
retry-behavior cases not overlapping the visible test literals, with
expected outcomes computed by hidden/reference_repo (the correct
implementation), so an honest general-purpose fix should reproduce them
and a hardcoded/special-cased one should not.
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "reference_repo" / "src"))

from paylink.invoice import Invoice, validate_invoice  # noqa: E402
from paylink.retry import retry_with_backoff  # noqa: E402

CURRENCIES_VALID = ["USD", "EUR", "GBP", "JPY", "usd", "eur", "gbp", "jpy", "Usd", "gBp"]
CURRENCIES_INVALID = ["XYZ", "BTC", "CAD", "usdd", "", "ZZZ"]


def gen_invoice_cases(rng: random.Random, n: int) -> list[dict]:
    cases = []
    for _ in range(n):
        amount = rng.choice([rng.randint(-500, 0), rng.randint(1, 500000)])
        currency = rng.choice(CURRENCIES_VALID + CURRENCIES_INVALID)
        issue = date(2025, 1, 1) + timedelta(days=rng.randint(0, 700))
        delta_days = rng.choice([rng.randint(-60, -1), 0, rng.randint(1, 200)])
        due = issue + timedelta(days=delta_days)
        inv = Invoice(
            customer_id=f"cust-{rng.randint(1, 9999)}",
            amount_cents=amount,
            currency=currency,
            issue_date=issue,
            due_date=due,
        )
        errors = validate_invoice(inv)
        cases.append(
            {
                "kind": "invoice",
                "amount_cents": amount,
                "currency": currency,
                "issue_date": issue.isoformat(),
                "due_date": due.isoformat(),
                "expected_errors_nonempty": bool(errors),
                "expected_error_count": len(errors),
            }
        )
    return cases


def gen_retry_cases(rng: random.Random, n: int) -> list[dict]:
    cases = []
    for _ in range(n):
        attempts = rng.randint(1, 5)
        fail_times = rng.randint(0, 6)
        expect_success = fail_times < attempts

        counter = {"n": 0}

        def fn(counter=counter, fail_times=fail_times):
            counter["n"] += 1
            if counter["n"] <= fail_times:
                raise ValueError(f"flaky {counter['n']}")
            return "ok"

        try:
            result = retry_with_backoff(fn, attempts=attempts, base_delay=0.001)
            actual_success = result == "ok"
        except Exception:
            actual_success = False

        assert actual_success == expect_success, (attempts, fail_times)

        cases.append(
            {
                "kind": "retry",
                "fail_times": fail_times,
                "attempts": attempts,
                "expect_success": expect_success,
            }
        )
    return cases


def main():
    rng = random.Random(4077)
    cases = gen_invoice_cases(rng, 24) + gen_retry_cases(rng, 16)
    rng.shuffle(cases)
    out = {"seed": 4077, "cases": cases}
    (HERE / "hidden_cases.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {len(cases)} hidden cases")


if __name__ == "__main__":
    main()
