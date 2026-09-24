from paylink.client import PaymentsClient


def test_get_status_reports_ok():
    client = PaymentsClient()
    status = client.get_status(timeout=2.0)
    assert status["status"] == "ok"
