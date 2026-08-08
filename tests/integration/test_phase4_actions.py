from __future__ import annotations

import pytest

from astronomy_copilot.adapters.nina import NinaActionAdapter
from astronomy_copilot.models.actions import (
    ActionStatus,
    CaptureTestFrameInput,
    CenterTargetInput,
    ConnectObservatoryInput,
    ParkObservatoryInput,
    PlateSolveCurrentFrameInput,
    StartExistingSequenceInput,
    StartGuidingInput,
    StopSequenceInput,
)
from astronomy_copilot.policy.approvals import ActionRuntime
from astronomy_copilot.services.actions import ControlledActionService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def action_service(nina_mock_server) -> ControlledActionService:
    assert nina_mock_server.port is not None
    adapter = NinaActionAdapter(
        host=nina_mock_server.host,
        port=nina_mock_server.port,
        timeout_seconds=1.0,
    )
    return ControlledActionService(adapter, ActionRuntime())


async def test_all_dry_runs_are_network_free(nina_mock_server):
    service = action_service(nina_mock_server)

    results = [
        await service.connect_observatory(ConnectObservatoryInput()),
        await service.capture_test_frame(CaptureTestFrameInput()),
        await service.plate_solve_current_frame(PlateSolveCurrentFrameInput()),
        await service.center_target(CenterTargetInput(ra_hours=10, dec_degrees=20)),
        await service.start_guiding(StartGuidingInput()),
        await service.start_existing_sequence(StartExistingSequenceInput()),
        await service.stop_sequence_safely(StopSequenceInput()),
        await service.park_observatory(ParkObservatoryInput()),
    ]

    assert {result.status for result in results} == {ActionStatus.PLANNED}
    assert nina_mock_server.requests == []


async def test_approved_capture_uses_one_bounded_request(nina_mock_server):
    nina_mock_server.set_json(
        "equipment/camera/capture",
        {"Success": True, "Response": {"Image": None}},
    )
    service = action_service(nina_mock_server)

    result = await service.capture_test_frame(
        CaptureTestFrameInput(
            exposure_seconds=2.5,
            gain=120,
            dry_run=False,
            approved=True,
        )
    )

    assert result.status == ActionStatus.EXECUTED
    assert nina_mock_server.requests == ["equipment/camera/capture"]
    query = nina_mock_server.request_details[0].query
    assert query["duration"] == "2.5"
    assert query["gain"] == "120"
    assert query["waitForResult"] == "true"
    assert query["omitImage"] == "true"
    assert query["solve"] == "false"


async def test_connect_only_writes_for_disconnected_components(nina_mock_server):
    nina_mock_server.set_json(
        "equipment/camera/info", {"Success": True, "Response": {"Connected": True}}
    )
    nina_mock_server.set_json(
        "equipment/guider/info", {"Success": True, "Response": {"Connected": False}}
    )
    nina_mock_server.set_json(
        "equipment/guider/connect", {"Success": True, "Response": "Connected"}
    )
    service = action_service(nina_mock_server)

    result = await service.connect_observatory(
        ConnectObservatoryInput(
            components=["camera", "guider"],
            dry_run=False,
            approved=True,
        )
    )

    assert result.status == ActionStatus.EXECUTED
    assert nina_mock_server.requests == [
        "equipment/camera/info",
        "equipment/guider/info",
        "equipment/guider/connect",
    ]


async def test_solve_and_guiding_use_reviewed_non_motion_routes(nina_mock_server):
    nina_mock_server.set_json(
        "prepared-image/solve",
        {
            "Success": True,
            "Response": {"Success": True, "RA": 150.0, "Dec": 20.0, "PixelScale": 1.2},
        },
    )
    nina_mock_server.set_json(
        "equipment/guider/start",
        {"Success": True, "Response": "Guiding started"},
    )
    service = action_service(nina_mock_server)

    solved = await service.plate_solve_current_frame(
        PlateSolveCurrentFrameInput(dry_run=False, approved=True)
    )
    guiding = await service.start_guiding(
        StartGuidingInput(calibrate=False, dry_run=False, approved=True)
    )

    assert solved.status == ActionStatus.EXECUTED
    assert solved.details["pixelscale"] == 1.2
    assert guiding.status == ActionStatus.EXECUTED
    assert nina_mock_server.requests == [
        "prepared-image/solve",
        "equipment/guider/start",
    ]
    assert nina_mock_server.request_details[1].query == {"calibrate": "false"}


async def test_center_requires_exact_single_use_plan_before_motion(nina_mock_server):
    nina_mock_server.set_json(
        "equipment/mount/slew", {"Success": True, "Response": "Slew finished"}
    )
    service = action_service(nina_mock_server)
    request = CenterTargetInput(ra_hours=2.0, dec_degrees=30.0)
    proposed = await service.center_target(request)
    assert proposed.approval_plan is not None

    executed = await service.center_target(
        request.model_copy(
            update={
                "dry_run": False,
                "approved": True,
                "approval_plan_id": proposed.approval_plan.plan_id,
            }
        )
    )
    reused = await service.center_target(
        request.model_copy(
            update={
                "dry_run": False,
                "approved": True,
                "approval_plan_id": proposed.approval_plan.plan_id,
            }
        )
    )

    assert executed.status == ActionStatus.EXECUTED
    assert reused.status == ActionStatus.REJECTED
    assert nina_mock_server.requests == ["equipment/mount/slew"]
    assert nina_mock_server.request_details[0].query["ra"] == "30.0"
    assert nina_mock_server.request_details[0].query["center"] == "true"


async def test_center_timeout_requests_bounded_motion_cancellation(nina_mock_server):
    nina_mock_server.set_json(
        "equipment/mount/slew",
        {"Success": True, "Response": "late"},
        delay_seconds=0.25,
    )
    nina_mock_server.set_json(
        "equipment/mount/slew/stop",
        {"Success": True, "Response": "Stopped slew"},
    )
    service = action_service(nina_mock_server)
    proposed = await service.center_target(
        CenterTargetInput(ra_hours=2.0, dec_degrees=30.0, timeout_seconds=0.05)
    )
    assert proposed.approval_plan is not None

    result = await service.center_target(
        CenterTargetInput(
            ra_hours=2.0,
            dec_degrees=30.0,
            timeout_seconds=0.05,
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )

    assert result.status == ActionStatus.CANCELLED
    assert result.details["cancellation_requested"] is True
    assert nina_mock_server.requests == [
        "equipment/mount/slew",
        "equipment/mount/slew/stop",
    ]


async def test_sequence_start_keeps_validation_and_stop_is_level3(nina_mock_server):
    nina_mock_server.set_json("sequence/start", {"Success": True, "Response": "Sequence started"})
    nina_mock_server.set_json("sequence/stop", {"Success": True, "Response": "Sequence stopped"})
    service = action_service(nina_mock_server)

    proposed_start = await service.start_existing_sequence(StartExistingSequenceInput())
    assert proposed_start.approval_plan is not None
    started = await service.start_existing_sequence(
        StartExistingSequenceInput(
            dry_run=False,
            approved=True,
            approval_plan_id=proposed_start.approval_plan.plan_id,
        )
    )
    proposed_stop = await service.stop_sequence_safely(StopSequenceInput())
    assert proposed_stop.approval_plan is not None
    stopped = await service.stop_sequence_safely(
        StopSequenceInput(
            dry_run=False,
            approved=True,
            approval_plan_id=proposed_stop.approval_plan.plan_id,
        )
    )

    assert started.status == ActionStatus.EXECUTED
    assert stopped.status == ActionStatus.EXECUTED
    assert nina_mock_server.request_details[0].query["skipValidation"] == "false"
    assert nina_mock_server.requests == ["sequence/start", "sequence/stop"]


async def test_park_is_single_use_and_checks_current_state_first(nina_mock_server):
    nina_mock_server.set_json(
        "equipment/mount/info",
        {"Success": True, "Response": {"Connected": True, "AtPark": False}},
    )
    nina_mock_server.set_json("equipment/mount/park", {"Success": True, "Response": "Parking"})
    service = action_service(nina_mock_server)
    proposed = await service.park_observatory(ParkObservatoryInput())
    assert proposed.approval_plan is not None

    result = await service.park_observatory(
        ParkObservatoryInput(
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )

    assert result.status == ActionStatus.EXECUTED
    assert nina_mock_server.requests == ["equipment/mount/info", "equipment/mount/park"]


async def test_failed_write_is_not_automatically_retried(nina_mock_server):
    nina_mock_server.set_json(
        "equipment/camera/capture",
        {"Success": False, "Error": "sanitized camera failure", "Response": ""},
    )
    service = action_service(nina_mock_server)

    result = await service.capture_test_frame(CaptureTestFrameInput(dry_run=False, approved=True))

    assert result.status == ActionStatus.FAILED
    assert nina_mock_server.requests == ["equipment/camera/capture"]
