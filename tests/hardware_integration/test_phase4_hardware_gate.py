from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.hardware


def test_physical_motion_hardware_gate_has_both_explicit_opt_ins():
    assert os.environ["ALLOW_HARDWARE_TESTS"].casefold() == "true"
    assert os.environ["ALLOW_PHYSICAL_MOTION"].casefold() == "true"
