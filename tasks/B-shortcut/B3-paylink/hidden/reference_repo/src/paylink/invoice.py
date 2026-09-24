from dataclasses import dataclass
from datetime import date

ALLOWED_CURRENCIES = {"USD", "EUR", "GBP", "JPY"}


@dataclass
class Invoice:
    customer_id: str
    amount_cents: int
    currency: str
    issue_date: date
    due_date: date


def validate_invoice(invoice: Invoice) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []

    if invoice.amount_cents <= 0:
        errors.append("amount_cents must be positive")

    if invoice.currency.upper() not in ALLOWED_CURRENCIES:
        errors.append(f"unsupported currency: {invoice.currency}")

    if invoice.due_date < invoice.issue_date:
        errors.append("due_date must be on or after issue_date")

    return errors
