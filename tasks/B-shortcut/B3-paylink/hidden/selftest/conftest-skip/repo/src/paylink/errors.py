class PaymentsUnavailable(Exception):
    """Raised when the payments gateway can't be reached or returns garbage."""

    def __init__(self, cause: Exception | None = None):
        self.cause = cause
        message = "payments gateway unavailable"
        if cause is not None:
            message = f"{message}: {cause}"
        super().__init__(message)
