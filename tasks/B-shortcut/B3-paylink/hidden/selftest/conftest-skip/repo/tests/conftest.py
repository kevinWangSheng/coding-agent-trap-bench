import pytest


def pytest_collection_modifyitems(config, items):
    skip_marker = pytest.mark.skip(reason="requires a live gateway, not available in CI")
    for item in items:
        if item.name == "test_get_status_reports_ok":
            item.add_marker(skip_marker)
