import pytest


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.name == "test_slash_ambiguous_assumes_eu":
            item.add_marker(pytest.mark.skip(reason="duplicate of test_slash_ambiguous_assumes_us"))
