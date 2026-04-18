import pytest


def pytest_collection_modifyitems(config, items):
    # every test in this package is asyncio — mark them implicitly so callers
    # don't need to sprinkle @pytest.mark.asyncio on each one.
    for item in items:
        if "asyncio" not in item.keywords:
            item.add_marker(pytest.mark.asyncio)
