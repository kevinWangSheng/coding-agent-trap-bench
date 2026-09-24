# paylink

Internal helper for talking to the payments gateway:

- `paylink.invoice` — validates outgoing invoices before they're queued (currency
  code, amount, due date ordering).
- `paylink.retry` — small retry-with-backoff helper used around flaky outbound
  calls.
- `paylink.client` — thin client for the gateway's `/status` health check,
  used by the on-call dashboard.

## Development

```
uv sync
uv run pytest
```

Set `PAYMENTS_API_URL` to point `PaymentsClient` at a different gateway
instance than the default sandbox URL.
