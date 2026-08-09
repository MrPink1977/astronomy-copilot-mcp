from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from astronomy_copilot.adapters.nina import NinaActionAdapter
from astronomy_copilot.models.actions import ActionStatus
from astronomy_copilot.models.workflow import PrepareForImagingInput, WorkflowStatus
from astronomy_copilot.policy.approvals import ActionRuntime
from astronomy_copilot.policy.workflow_plans import WorkflowRuntime
from astronomy_copilot.services.actions import ControlledActionService
from astronomy_copilot.services.image_analysis import FitsAnalysisService
from astronomy_copilot.services.readiness import ImagingReadinessService
from astronomy_copilot.services.session import SessionRuntime, SessionService
from astronomy_copilot.workflows.prepare_for_imaging import PrepareForImagingService
from tests.support.fits_factory import controlled_image_recipe, write_controlled_fits

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def workflow_scenario(nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    scenario.update(nina_fixture("phase5_session.json"))
    scenario.update(nina_fixture("phase7_workflow.json"))
    scenario["profile/show"] = nina_fixture("active_profile.json")
    scenario["equipment/mount/info"]["Response"].update(
        {"AtPark": False, "Slewing": False, "Tracking": True}
    )
    scenario["equipment/guider/info"]["Response"]["State"] = "Stopped"
    return scenario


def build_workflow(nina_mock_server, scenario):
    nina_mock_server.set_scenario(scenario)
    assert nina_mock_server.port is not None
    adapter = NinaActionAdapter(
        host=nina_mock_server.host,
        port=nina_mock_server.port,
        timeout_seconds=1.0,
    )
    session = SessionService(adapter, SessionRuntime())
    actions = ControlledActionService(adapter, ActionRuntime(), session)
    service = PrepareForImagingService(
        adapter,
        actions,
        session,
        ImagingReadinessService(adapter),
        FitsAnalysisService(),
        WorkflowRuntime(),
    )
    return service


def workflow_request(**updates):
    request = PrepareForImagingInput(
        target_name="Controlled target",
        ra_hours=10.0,
        dec_degrees=20.0,
        test_exposure_seconds=3.0,
        max_plate_solve_attempts=2,
    )
    return request.model_copy(update=updates)


async def test_mock_workflow_is_end_to_end_bounded_and_pauses_before_motion(
    nina_mock_server, nina_fixture, tmp_path
):
    scenario = workflow_scenario(nina_fixture)
    service = build_workflow(nina_mock_server, scenario)
    image_path = tmp_path / "phase7-controlled-frame.fits"
    write_controlled_fits(image_path, controlled_image_recipe("round_star_field"))
    request_parameters = {"image_file_path": str(image_path)}
    nina_mock_server.set_json_sequence(
        "prepared-image/solve",
        [
            {"Success": False, "Error": "controlled solve failure", "Response": ""},
            scenario["prepared-image/solve"],
        ],
    )
    nina_mock_server.set_json_side_effect(
        "equipment/guider/start",
        "equipment/guider/info",
        {
            "Success": True,
            "Response": {"Connected": True, "State": "Guiding"},
        },
    )

    proposed = await service.prepare(workflow_request(**request_parameters))
    assert proposed.status == WorkflowStatus.PROPOSED
    assert proposed.dry_run is True
    assert nina_mock_server.requests == []

    paused = await service.prepare(
        workflow_request(
            **request_parameters,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    assert paused.status == WorkflowStatus.AWAITING_APPROVAL
    assert paused.required_approval is not None
    assert paused.required_approval.action == "center_target"
    assert paused.plate_solve_attempts == 2
    assert paused.changed_variables == ["solve_exposure_seconds 3 -> 6"]
    assert "equipment/mount/slew" not in nina_mock_server.requests
    assert "equipment/guider/start" not in nina_mock_server.requests
    captures = [
        detail
        for detail in nina_mock_server.request_details
        if detail.endpoint == "equipment/camera/capture"
    ]
    assert [capture.query["duration"] for capture in captures] == ["3.0", "6.0"]
    assert len({capture.query.get("gain") for capture in captures}) == 1

    completed = await service.prepare(
        workflow_request(
            **request_parameters,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            center_approval_plan_id=paused.required_approval.plan_id,
        )
    )

    assert completed.status == WorkflowStatus.COMPLETED
    assert completed.final_readiness is not None
    assert completed.final_readiness.ready is True
    assert completed.session_timeline is not None
    assert len(completed.image_analyses) == 3
    assert completed.final_image_analysis is not None
    assert completed.final_image_analysis.state == "COMPLETE"
    assert "equipment/mount/slew" in nina_mock_server.requests
    assert "equipment/guider/start" in nina_mock_server.requests
    assert (
        len(
            [
                detail
                for detail in nina_mock_server.request_details
                if detail.endpoint == "equipment/camera/capture"
            ]
        )
        == 3
    )
    assert completed.action_results[-1].status == ActionStatus.EXECUTED

    request_count = len(nina_mock_server.requests)
    replay = await service.prepare(
        workflow_request(
            **request_parameters,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            center_approval_plan_id=paused.required_approval.plan_id,
        )
    )
    assert replay.status == WorkflowStatus.COMPLETED
    assert len(nina_mock_server.requests) == request_count


async def test_saturated_frame_changes_only_exposure_then_blocks_final_readiness(
    nina_mock_server, nina_fixture, tmp_path
):
    scenario = workflow_scenario(nina_fixture)
    service = build_workflow(nina_mock_server, scenario)
    image_path = tmp_path / "phase7-saturated-frame.fits"
    write_controlled_fits(image_path, controlled_image_recipe("saturated_gradient"))
    parameters = {
        "image_file_path": str(image_path),
        "require_guiding": False,
    }
    nina_mock_server.set_json_sequence(
        "prepared-image/solve",
        [
            {"Success": False, "Error": "controlled solve failure", "Response": ""},
            scenario["prepared-image/solve"],
        ],
    )

    proposed = await service.prepare(workflow_request(**parameters))
    paused = await service.prepare(
        workflow_request(
            **parameters,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    assert paused.status == WorkflowStatus.AWAITING_APPROVAL
    assert paused.changed_variables == ["solve_exposure_seconds 3 -> 1.5"]
    captures = [
        detail
        for detail in nina_mock_server.request_details
        if detail.endpoint == "equipment/camera/capture"
    ]
    assert [capture.query["duration"] for capture in captures] == ["3.0", "1.5"]
    assert len({capture.query.get("gain") for capture in captures}) == 1

    failed = await service.prepare(
        workflow_request(
            **parameters,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            center_approval_plan_id=paused.required_approval.plan_id,
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    assert "saturation" in failed.summary
    assert failed.final_image_analysis is not None
    assert failed.final_readiness is not None
    assert failed.session_timeline is not None
    assert failed.timeline[-1].state == "FAILED"


async def test_wrong_center_approval_keeps_workflow_paused_without_motion(
    nina_mock_server, nina_fixture
):
    service = build_workflow(nina_mock_server, workflow_scenario(nina_fixture))
    proposed = await service.prepare(workflow_request(max_plate_solve_attempts=1))
    paused = await service.prepare(
        workflow_request(
            max_plate_solve_attempts=1,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    rejected_resume = await service.prepare(
        workflow_request(
            max_plate_solve_attempts=1,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            center_approval_plan_id="wrong-plan",
        )
    )

    assert paused.status == WorkflowStatus.AWAITING_APPROVAL
    assert rejected_resume.status == WorkflowStatus.AWAITING_APPROVAL
    assert rejected_resume.warnings
    assert "equipment/mount/slew" not in nina_mock_server.requests


async def test_exhausted_solve_recovery_stops_with_known_state(nina_mock_server, nina_fixture):
    service = build_workflow(nina_mock_server, workflow_scenario(nina_fixture))
    nina_mock_server.set_json(
        "prepared-image/solve",
        {"Success": False, "Error": "controlled persistent failure", "Response": ""},
    )
    proposed = await service.prepare(workflow_request())

    failed = await service.prepare(
        workflow_request(
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    assert failed.plate_solve_attempts == 2
    assert len(failed.changed_variables) == 1
    assert failed.final_readiness is not None
    assert failed.session_timeline is not None
    assert failed.timeline[-1].state == "FAILED"
    assert "equipment/mount/slew" not in nina_mock_server.requests


async def test_unsafe_monitor_stops_before_any_write(nina_mock_server, nina_fixture):
    scenario = workflow_scenario(nina_fixture)
    scenario["equipment/safetymonitor/info"]["Response"]["IsSafe"] = False
    scenario["profile/show"]["Response"]["SafetyMonitorSettings"]["Id"] = "No_Device"
    service = build_workflow(nina_mock_server, scenario)
    proposed = await service.prepare(workflow_request())

    failed = await service.prepare(
        workflow_request(
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            operator_safety_attestation="OPERATOR_CONFIRMS_SAFE",
            operator_safety_attested_at=datetime.now(timezone.utc),
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    write_endpoints = {
        "equipment/camera/capture",
        "prepared-image/solve",
        "equipment/mount/slew",
        "equipment/guider/start",
    }
    assert write_endpoints.isdisjoint(nina_mock_server.requests)


async def test_absent_monitor_requires_current_operator_attestation(nina_mock_server, nina_fixture):
    scenario = workflow_scenario(nina_fixture)
    scenario["equipment/safetymonitor/info"]["Response"] = {
        "Connected": False,
        "IsSafe": False,
    }
    scenario["profile/show"]["Response"]["SafetyMonitorSettings"]["Id"] = "No_Device"
    service = build_workflow(nina_mock_server, scenario)
    proposed = await service.prepare(workflow_request(max_plate_solve_attempts=1))

    failed = await service.prepare(
        workflow_request(
            max_plate_solve_attempts=1,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    assert "operator safety attestation is required" in failed.summary
    assert "equipment/camera/capture" not in nina_mock_server.requests


async def test_current_attestation_for_absent_monitor_reaches_motion_boundary(
    nina_mock_server, nina_fixture
):
    scenario = workflow_scenario(nina_fixture)
    scenario["equipment/safetymonitor/info"]["Response"] = {
        "Connected": False,
        "IsSafe": False,
    }
    scenario["profile/show"]["Response"]["SafetyMonitorSettings"]["Id"] = "No_Device"
    service = build_workflow(nina_mock_server, scenario)
    proposed = await service.prepare(workflow_request(max_plate_solve_attempts=1))

    paused = await service.prepare(
        workflow_request(
            max_plate_solve_attempts=1,
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            operator_safety_attestation="OPERATOR_CONFIRMS_SAFE",
            operator_safety_attested_at=datetime.now(timezone.utc),
        )
    )

    assert paused.status == WorkflowStatus.AWAITING_APPROVAL
    assert paused.required_approval is not None
    assert "equipment/mount/slew" not in nina_mock_server.requests


async def test_expired_attestation_for_absent_monitor_stops_before_write(
    nina_mock_server, nina_fixture
):
    scenario = workflow_scenario(nina_fixture)
    scenario["equipment/safetymonitor/info"]["Response"] = {
        "Connected": False,
        "IsSafe": False,
    }
    scenario["profile/show"]["Response"]["SafetyMonitorSettings"]["Id"] = "No_Device"
    service = build_workflow(nina_mock_server, scenario)
    proposed = await service.prepare(workflow_request())

    failed = await service.prepare(
        workflow_request(
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            operator_safety_attestation="OPERATOR_CONFIRMS_SAFE",
            operator_safety_attested_at=datetime.now(timezone.utc) - timedelta(minutes=6),
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    assert "expired" in failed.summary
    assert "equipment/camera/capture" not in nina_mock_server.requests


async def test_disconnected_configured_monitor_cannot_use_attestation(
    nina_mock_server, nina_fixture
):
    scenario = workflow_scenario(nina_fixture)
    scenario["equipment/safetymonitor/info"]["Response"] = {
        "Connected": False,
        "IsSafe": False,
    }
    service = build_workflow(nina_mock_server, scenario)
    proposed = await service.prepare(workflow_request())

    failed = await service.prepare(
        workflow_request(
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
            operator_safety_attestation="OPERATOR_CONFIRMS_SAFE",
            operator_safety_attested_at=datetime.now(timezone.utc),
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    assert "configured safety monitor is disconnected" in failed.summary
    assert "equipment/camera/capture" not in nina_mock_server.requests


async def test_contradictory_mount_telemetry_stops_before_any_write(nina_mock_server, nina_fixture):
    scenario = workflow_scenario(nina_fixture)
    scenario["equipment/mount/info"]["Response"].update(
        {"AtPark": True, "Slewing": True, "Tracking": False}
    )
    service = build_workflow(nina_mock_server, scenario)
    proposed = await service.prepare(workflow_request())

    failed = await service.prepare(
        workflow_request(
            dry_run=False,
            approved=True,
            workflow_id=proposed.workflow_id,
        )
    )

    assert failed.status == WorkflowStatus.FAILED
    assert "contradictory" in failed.summary
    assert "equipment/camera/capture" not in nina_mock_server.requests
    assert "equipment/mount/slew" not in nina_mock_server.requests
