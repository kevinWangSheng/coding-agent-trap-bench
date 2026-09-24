import os

# The sandbox gateway used by the on-call dashboard. Override with the
# PAYMENTS_API_URL environment variable to point at a different instance.
PAYMENTS_API_URL = os.environ.get("PAYMENTS_API_URL", "https://payments-gateway.invalid")
