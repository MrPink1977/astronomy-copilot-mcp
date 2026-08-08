from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from astronomy_copilot.models.diagnostics import ImagingReadiness
from astronomy_copilot.models.session import SessionState, SessionTimeline
from astronomy_copilot.models.status import OverallState
from astronomy_copilot.models.workflow import (
    PrepareForImagingInput,
    WorkflowStatus,
)
from astronomy_copilot.policy.workflow_plans import (
    WorkflowRejectedError,
    WorkflowRuntime,
    planned_steps,
)
from astronomy_copilot.workflows.prepare_for_imaging import PrepareForImagingService

pytestmark = pytest.mark.unit


def request(**updates) -> PrepareForImagingInput:
    base = PrepareForImagingInput(
        target_name="Controlled target",
        ra_hours=10.0,
        dec_degrees=20.0,
    )
    return base.model_copy(update=updates)


def test_plan_marks_the_only_motion_boundary_and_omits_optional_guiding():
    guided = planned_steps(True)
    unguided = planned_steps(False)

    assert [step.step_id for step in guided] == [
        "preflight",
        "connect",
        "solve_frame",
        "solve_quality",
        "plate_solve",
        "center",
        "guiding",
        "final_frame",
        "final_quality",
        "final_readiness",
    ]
    assert [step.step_id for step in guided if step.action_level == 2] == ["center"]
    assert "guiding" not in [step.step_id for step in unguided]


def test_workflow_proposal_is_immutable_and_expires():
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    current = [now]
    runtime = WorkflowRuntime(ttl_seconds=60, clock=lambda: current[0])
    proposal = runtime.create(request())

    with pytest.raises(WorkflowRejectedError, match="parameters differ"):
        with runtime.claim(
            proposal.plan.workflow_id,
            request(test_exposure_seconds=4.0),
        ):
            pass

    current[0] = now + timedelta(seconds=61)
    with pytest.raises(WorkflowRejectedError, match="expired"):
        with runtime.claim(proposal.plan.workflow_id, request()):
            pass


@pytest.mark.asyncio
async def test_stale_telemetry_fails_with_a_known_reported_state_and_no_actions():
    class StaleAdapter:
        async def get_session_snapshot(self):
            return {
                "observed_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                "equipment": {},
            }

    class ForbiddenActions:
        def __getattr__(self, name):
            raise AssertionError(f"stale workflow attempted action {name}")

    class FakeSession:
        async def reconcile(self):
            return SessionState.OFFLINE

        def current_timeline(self, cursor=0, limit=100):
            return SessionTimeline(
                state=SessionState.OFFLINE,
                authoritative=True,
                summary="Known offline state.",
                count=0,
                next_cursor=0,
            )

    class FakeReadiness:
        async def get_readiness(self):
            return ImagingReadiness(
                state=OverallState.OFFLINE,
                ready=False,
                summary="Known offline readiness.",
            )

    class ForbiddenImageAnalysis:
        def analyze(self, request):
            raise AssertionError("stale workflow attempted image analysis")

    runtime = WorkflowRuntime()
    service = PrepareForImagingService(
        StaleAdapter(),
        ForbiddenActions(),
        FakeSession(),
        FakeReadiness(),
        ForbiddenImageAnalysis(),
        runtime,
    )
    proposed = await service.prepare(request())

    result = await service.prepare(
        request(
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    assert result.status == WorkflowStatus.FAILED
    assert "stale" in result.summary
    assert result.action_results == []
    assert result.final_readiness is not None
    assert result.session_timeline is not None
    assert result.timeline[-1].state == "FAILED"
