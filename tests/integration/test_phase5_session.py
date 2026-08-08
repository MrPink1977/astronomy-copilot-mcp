from __future__ import annotations

import asyncio

import pytest

from astronomy_copilot.adapters.nina import NinaActionAdapter
from astronomy_copilot.adapters.nina_events import NinaEventAdapter
from astronomy_copilot.models.actions import (
    ActionStatus,
    ParkObservatoryInput,
    StartExistingSequenceInput,
)
from astronomy_copilot.models.session import SessionState
from astronomy_copilot.policy.approvals import ActionRuntime
from astronomy_copilot.services.actions import ControlledActionService
from astronomy_copilot.services.session import SessionRuntime, SessionService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def configured_services(nina_mock_server, scenario):
    nina_mock_server.set_scenario(scenario)
    assert nina_mock_server.port is not None
    adapter = NinaActionAdapter(
        host=nina_mock_server.host,
        port=nina_mock_server.port,
        timeout_seconds=1.0,
    )
    session = SessionService(adapter, SessionRuntime())
    actions = ControlledActionService(adapter, ActionRuntime(), session)
    return adapter, session, actions


def phase5_scenario(nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    scenario.update(nina_fixture("phase5_session.json"))
    return scenario


async def test_full_session_snapshot_uses_only_sanitized_mock_routes(
    nina_mock_server, nina_fixture
):
    scenario = phase5_scenario(nina_fixture)
    adapter, session, _ = configured_services(nina_mock_server, scenario)

    state = await session.reconcile()

    assert state == SessionState.SAFE
    assert session.runtime.authoritative is True
    assert set(nina_mock_server.requests) == set(scenario)


async def test_mock_websocket_events_and_reconnect_reconcile_to_snapshot(
    nina_mock_server, nina_fixture
):
    scenario = phase5_scenario(nina_fixture)
    nina_mock_server.set_scenario(scenario)
    nina_mock_server.set_websocket_events(
        [{"Response": {"Event": "GUIDER-START", "Time": "2026-08-08T01:00:00Z"}}]
    )
    assert nina_mock_server.port is not None
    snapshot_adapter = NinaActionAdapter(
        host=nina_mock_server.host,
        port=nina_mock_server.port,
        timeout_seconds=1.0,
    )
    event_adapter = NinaEventAdapter(
        host=nina_mock_server.host,
        port=nina_mock_server.port,
        timeout_seconds=1.0,
    )
    service = SessionService(snapshot_adapter, SessionRuntime(), event_adapter)

    await service.start()
    try:
        for _ in range(100):
            event_types = [event.event_type for event in service.runtime.timeline().events]
            if (
                nina_mock_server.websocket_connections >= 1
                and "RECONNECTING" in event_types
                and event_types.count("SNAPSHOT-RECONCILED") >= 2
            ):
                break
            await asyncio.sleep(0.01)
        event_types = [event.event_type for event in service.runtime.timeline().events]
        assert "GUIDER-START" in event_types
        assert "RECONNECTING" in event_types
        assert event_types.count("SNAPSHOT-RECONCILED") >= 2
        assert service.runtime.state == SessionState.SAFE
        assert service.runtime.authoritative is True
    finally:
        await service.stop()


async def test_park_during_slew_is_rejected_before_plan_consumption(nina_mock_server, nina_fixture):
    scenario = phase5_scenario(nina_fixture)
    scenario["equipment/mount/info"]["Response"].update({"AtPark": False, "Slewing": True})
    _, _, actions = configured_services(nina_mock_server, scenario)
    proposed = await actions.park_observatory(ParkObservatoryInput())
    assert proposed.approval_plan is not None

    rejected = await actions.park_observatory(
        ParkObservatoryInput(
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )

    assert rejected.status == ActionStatus.REJECTED
    assert rejected.details == {"session_state": "SLEWING"}
    assert "equipment/mount/park" not in nina_mock_server.requests

    nina_mock_server.set_json(
        "equipment/mount/info",
        {"Success": True, "Response": {"Connected": True, "AtPark": False, "Slewing": False}},
    )
    nina_mock_server.set_json("equipment/mount/park", {"Success": True, "Response": "Parking"})
    accepted = await actions.park_observatory(
        ParkObservatoryInput(
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )
    assert accepted.status == ActionStatus.EXECUTED


async def test_starting_second_sequence_is_rejected_without_write(nina_mock_server, nina_fixture):
    scenario = phase5_scenario(nina_fixture)
    scenario["equipment/mount/info"]["Response"].update({"AtPark": False, "Slewing": False})
    scenario["sequence/state"]["Response"][0]["Status"] = "RUNNING"
    _, _, actions = configured_services(nina_mock_server, scenario)
    proposed = await actions.start_existing_sequence(StartExistingSequenceInput())
    assert proposed.approval_plan is not None

    rejected = await actions.start_existing_sequence(
        StartExistingSequenceInput(
            dry_run=False,
            approved=True,
            approval_plan_id=proposed.approval_plan.plan_id,
        )
    )

    assert rejected.status == ActionStatus.REJECTED
    assert rejected.details == {"session_state": "IMAGING"}
    assert "sequence/start" not in nina_mock_server.requests
