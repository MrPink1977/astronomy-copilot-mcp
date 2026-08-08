from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from astronomy_copilot.models.actions import (
    ActionLevel,
    ActionStatus,
    CaptureTestFrameInput,
    CenterTargetInput,
    ConnectObservatoryInput,
    ParkObservatoryInput,
    StartGuidingInput,
)
from astronomy_copilot.policy.approvals import (
    ActionRuntime,
    ApprovalPlanStore,
    ApprovalRejectedError,
    AuditLog,
)
from astronomy_copilot.services.actions import ControlledActionService, safe_solve_details

pytestmark = pytest.mark.unit


class FakeActionAdapter:
    def __init__(self):
        self.calls = []
        self.cancelled = []
        self.info = {
            "camera": {"Connected": False},
            "mount": {"Connected": True, "AtPark": False},
            "guider": {"Connected": True},
        }

    async def execute(self, endpoint, *, params=None, timeout_seconds):
        self.calls.append((endpoint, params, timeout_seconds))
        return "ok"

    async def get_equipment_info(self, component, *, timeout_seconds):
        self.calls.append((f"equipment/{component}/info", None, timeout_seconds))
        return self.info[component]

    async def cancel(self, action):
        self.cancelled.append(action)
        return True


def service_with(adapter=None, runtime=None):
    return ControlledActionService(adapter or FakeActionAdapter(), runtime or ActionRuntime())


@pytest.mark.asyncio
async def test_level1_dry_run_sends_no_adapter_requests_and_is_audited():
    adapter = FakeActionAdapter()
    service = service_with(adapter)

    result = await service.capture_test_frame(CaptureTestFrameInput())

    assert result.status == ActionStatus.PLANNED
    assert result.dry_run is True
    assert result.approval_plan is None
    assert adapter.calls == []
    assert service.get_audit().events[0].status == ActionStatus.PLANNED


@pytest.mark.asyncio
async def test_every_write_requires_server_side_general_approval():
    adapter = FakeActionAdapter()
    service = service_with(adapter)

    result = await service.capture_test_frame(CaptureTestFrameInput(dry_run=False, approved=False))

    assert result.status == ActionStatus.REJECTED
    assert adapter.calls == []
    assert "approved=true" in result.summary


@pytest.mark.asyncio
async def test_level2_plan_is_single_use_and_exactly_matches_parameters():
    adapter = FakeActionAdapter()
    service = service_with(adapter)
    proposed = await service.center_target(CenterTargetInput(ra_hours=5.5, dec_degrees=-12.0))
    assert proposed.approval_plan is not None

    executed = await service.center_target(
        CenterTargetInput(
            ra_hours=5.5,
            dec_degrees=-12.0,
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )
    reused = await service.center_target(
        CenterTargetInput(
            ra_hours=5.5,
            dec_degrees=-12.0,
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )

    assert executed.status == ActionStatus.EXECUTED
    assert reused.status == ActionStatus.REJECTED
    assert "already been used" in reused.summary
    assert [call[0] for call in adapter.calls] == ["equipment/mount/slew"]


@pytest.mark.asyncio
async def test_altered_level2_plan_is_rejected_without_a_write():
    adapter = FakeActionAdapter()
    service = service_with(adapter)
    proposed = await service.center_target(CenterTargetInput(ra_hours=5.5, dec_degrees=-12.0))
    assert proposed.approval_plan is not None

    altered = await service.center_target(
        CenterTargetInput(
            ra_hours=6.0,
            dec_degrees=-12.0,
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )

    assert altered.status == ActionStatus.REJECTED
    assert "differ" in altered.summary
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_level2_execution_without_a_plan_is_rejected_without_a_write():
    adapter = FakeActionAdapter()
    service = service_with(adapter)

    result = await service.center_target(
        CenterTargetInput(
            ra_hours=6.0,
            dec_degrees=-12.0,
            dry_run=False,
            approved=True,
        )
    )

    assert result.status == ActionStatus.REJECTED
    assert "approval_plan_id" in result.summary
    assert adapter.calls == []


def test_expired_plan_is_rejected():
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)
    current = [now]
    store = ApprovalPlanStore(ttl_seconds=30, clock=lambda: current[0])
    plan = store.create(
        action="park_observatory",
        action_level=ActionLevel.SESSION_ENDING,
        summary="Park the mount.",
        parameters_hash="abc",
    )
    current[0] += timedelta(seconds=31)

    with pytest.raises(ApprovalRejectedError, match="expired"):
        store.consume(plan.plan_id, action="park_observatory", parameters_hash="abc")


def test_plan_for_another_action_is_rejected():
    store = ApprovalPlanStore()
    plan = store.create(
        action="center_target",
        action_level=ActionLevel.PHYSICAL_MOTION,
        summary="Center the mount.",
        parameters_hash="abc",
    )

    with pytest.raises(ApprovalRejectedError, match="different action"):
        store.consume(plan.plan_id, action="park_observatory", parameters_hash="abc")


def test_audit_log_is_bounded_and_returns_newest_first():
    audit = AuditLog(max_events=2)
    for index in range(3):
        audit.append(
            action=f"action-{index}",
            action_level=ActionLevel.LOW_RISK_WRITE,
            status=ActionStatus.PLANNED,
            dry_run=True,
            parameters_hash=str(index),
            summary="planned",
        )

    report = audit.report(limit=100)

    assert [event.action for event in report.events] == ["action-2", "action-1"]
    assert report.count == 2


@pytest.mark.asyncio
async def test_level1_idempotency_key_prevents_duplicate_capture():
    adapter = FakeActionAdapter()
    service = service_with(adapter)
    request = CaptureTestFrameInput(
        dry_run=False,
        approved=True,
        idempotency_key="capture-001",
    )

    first = await service.capture_test_frame(request)
    replay = await service.capture_test_frame(request)

    assert first.status == ActionStatus.EXECUTED
    assert replay.status == ActionStatus.SKIPPED
    assert replay.idempotent_replay is True
    assert [call[0] for call in adapter.calls] == ["equipment/camera/capture"]
    assert service.get_audit().count == 2


@pytest.mark.asyncio
async def test_guiding_calibration_is_promoted_to_level2_motion_policy():
    adapter = FakeActionAdapter()
    service = service_with(adapter)

    result = await service.start_guiding(StartGuidingInput(calibrate=True))

    assert result.action_level == ActionLevel.PHYSICAL_MOTION
    assert result.approval_plan is not None
    assert adapter.calls == []


def test_plate_solve_error_details_are_sanitized():
    details = safe_solve_details(
        {"Success": False, "Error": r"Failed at C:\Observatory\secret.fit token=abc"}
    )

    assert details["error"] == "Failed at [redacted_path]"
    assert "abc" not in details["error"]


@pytest.mark.asyncio
async def test_connect_and_park_skip_writes_when_state_is_already_satisfied():
    adapter = FakeActionAdapter()
    adapter.info["camera"]["Connected"] = True
    adapter.info["mount"]["AtPark"] = True
    service = service_with(adapter)

    connected = await service.connect_observatory(
        ConnectObservatoryInput(components=["camera"], dry_run=False, approved=True)
    )
    planned_park = await service.park_observatory(ParkObservatoryInput())
    assert planned_park.approval_plan is not None
    parked = await service.park_observatory(
        ParkObservatoryInput(
            dry_run=False,
            approved=True,
            approval_plan_id=planned_park.approval_plan.plan_id,
        )
    )

    assert connected.status == ActionStatus.SKIPPED
    assert parked.status == ActionStatus.SKIPPED
    assert all(not call[0].endswith("/connect") for call in adapter.calls)
    assert all(not call[0].endswith("/park") for call in adapter.calls)


@pytest.mark.parametrize(
    "invalid_input",
    [
        {"exposure_seconds": 0},
        {"exposure_seconds": 31},
        {"gain": -1},
        {"gain": 1001},
        {"timeout_seconds": 0.01},
        {"idempotency_key": "x" * 65},
    ],
)
def test_test_frame_input_limits_are_enforced(invalid_input):
    with pytest.raises(ValidationError):
        CaptureTestFrameInput(**invalid_input)


def test_center_and_component_input_limits_are_enforced():
    with pytest.raises(ValidationError):
        CenterTargetInput(ra_hours=24.0, dec_degrees=0)
    with pytest.raises(ValidationError):
        CenterTargetInput(ra_hours=1.0, dec_degrees=91)
    with pytest.raises(ValidationError):
        ConnectObservatoryInput(components=["camera", "camera"])
