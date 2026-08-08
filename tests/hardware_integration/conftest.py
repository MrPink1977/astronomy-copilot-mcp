from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(items):
    enabled = os.getenv("ALLOW_HARDWARE_TESTS", "").casefold() == "true"
    motion_enabled = os.getenv("ALLOW_PHYSICAL_MOTION", "").casefold() == "true"
    if enabled and motion_enabled:
        return

    skip = pytest.mark.skip(
        reason=("hardware tests require ALLOW_HARDWARE_TESTS=true and ALLOW_PHYSICAL_MOTION=true")
    )
    for item in items:
        if item.get_closest_marker("hardware"):
            item.add_marker(skip)
