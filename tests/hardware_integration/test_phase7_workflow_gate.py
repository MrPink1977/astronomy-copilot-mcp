from __future__ import annotations

import os

import pytest

from astronomy_copilot.models.workflow import PrepareForImagingInput, WorkflowStatus
from astronomy_copilot.server import (
    action_runtime,
    build_prepare_for_imaging_service,
    workflow_runtime,
)

pytestmark = pytest.mark.hardware


def test_phase7_live_workflow_requires_dedicated_opt_in():
    assert os.environ["ALLOW_HARDWARE_TESTS"].casefold() == "true"
    assert os.environ["ALLOW_PHYSICAL_MOTION"].casefold() == "true"
    assert os.environ["ALLOW_PHASE7_WORKFLOW"].casefold() == "true"


@pytest.mark.asyncio
async def test_phase7_live_workflow_reaches_but_does_not_cross_motion_boundary():
    request = PrepareForImagingInput(
        target_name=os.environ["PHASE7_TARGET_NAME"],
        ra_hours=float(os.environ["PHASE7_RA_HOURS"]),
        dec_degrees=float(os.environ["PHASE7_DEC_DEGREES"]),
        test_exposure_seconds=float(os.getenv("PHASE7_TEST_EXPOSURE_SECONDS", "3")),
        max_plate_solve_attempts=1,
    )
    action_runtime.clear()
    workflow_runtime.clear()
    service = build_prepare_for_imaging_service()
    try:
        proposed = await service.prepare(request)
        paused = await service.prepare(
            request.model_copy(
                update={
                    "dry_run": False,
                    "approved": True,
                    "workflow_id": proposed.workflow_id,
                }
            )
        )
        assert paused.status == WorkflowStatus.AWAITING_APPROVAL
        assert paused.required_approval is not None
        assert paused.required_approval.action == "center_target"
    finally:
        action_runtime.clear()
        workflow_runtime.clear()
