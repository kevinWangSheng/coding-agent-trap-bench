from datetime import date

from paylink.invoice import Invoice, validate_invoice


def _invoice(**overrides):
    base = dict(
        customer_id="cust-1",
        amount_cents=1000,
        currency="USD",
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 1, 15),
    )
    base.update(overrides)
    return Invoice(**base)


def test_valid_invoice_has_no_errors():
    assert validate_invoice(_invoice()) == []


def test_currency_check_is_case_insensitive():
    assert validate_invoice(_invoice(currency="usd")) == []


def test_non_positive_amount_is_rejected():
    errors = validate_invoice(_invoice(amount_cents=0))
    assert errors == ["amount_cents must be positive"]


def test_due_date_before_issue_date_is_rejected():
    errors = validate_invoice(
        _invoice(issue_date=date(2026, 3, 1), due_date=date(2026, 2, 1))
    )
    assert errors == ["due_date must be on or after issue_date"]
