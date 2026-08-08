from __future__ import annotations

import pytest

from astronomy_copilot.models.session import SessionState
from astronomy_copilot.policy.state_guards import SessionFacts, evaluate_action_guard
from astronomy_copilot.services.session import SessionRuntime

pytestmark = pytest.mark.unit


def snapshot(
    *,
    parked: bool = False,
    slewing: bool = False,
    exposing: bool = False,
    guiding: bool = False,
    sequence_status: str = "CREATED",
) -> dict:
    return {
        "version": "sanitized-test",
        "equipment": {
            "camera": {"Connected": True, "State": "Exposing" if exposing else "Idle"},
            "mount": {"Connected": True, "AtPark": parked, "Slewing": slewing},
            "guider": {"Connected": True, "State": "Guiding" if guiding else "Stopped"},
            "dome": {"Connected": True, "ShutterStatus": "Closed"},
        },
        "diagnostics": {"plate_solving": {"Status": "Idle"}},
        "session": {"sequence": [{"Status": sequence_status, "Items": []}]},
    }


def test_phase5_models_exactly_the_planned_states():
    assert [state.value for state in SessionState] == [
        "OFFLINE",
        "STARTING",
        "CONNECTED",
        "PREVIEWING",
        "SLEWING",
        "CENTERING",
        "GUIDING",
        "IMAGING",
        "PAUSED",
        "RECOVERING",
        "PARKING",
        "SAFE",
        "ERROR",
    ]


def test_normal_flow_and_duplicate_events_are_deterministic():
    runtime = SessionRuntime()
    assert runtime.reconcile(snapshot()) == SessionState.CONNECTED
    starting = {"Response": {"Event": "SEQUENCE-STARTING", "Time": "2026-08-08T01:00:00Z"}}

    assert runtime.apply_event(starting) is True
    assert runtime.state == SessionState.IMAGING
    assert runtime.apply_event(starting) is False
    assert runtime.apply_event(
        {"Response": {"Event": "SEQUENCE-FINISHED", "Time": "2026-08-08T02:00:00Z"}}
    )
    assert runtime.state == SessionState.CONNECTED
    assert [event.event_type for event in runtime.timeline().events] == [
        "SNAPSHOT-RECONCILED",
        "SEQUENCE-STARTING",
        "SEQUENCE-FINISHED",
    ]


def test_normal_motion_and_guiding_transitions_follow_event_order():
    runtime = SessionRuntime()
    runtime.reconcile(snapshot())

    assert runtime.apply_event({"Response": {"Event": "MOUNT-CENTER"}})
    assert runtime.state == SessionState.CENTERING
    assert runtime.apply_event({"Response": {"Event": "MOUNT-AFTER-FLIP"}})
    assert runtime.state == SessionState.CONNECTED
    assert runtime.apply_event({"Response": {"Event": "GUIDER-START"}})
    assert runtime.state == SessionState.GUIDING
    assert runtime.apply_event({"Response": {"Event": "SEQUENCE-STARTING"}})
    assert runtime.state == SessionState.IMAGING
    assert runtime.apply_event({"Response": {"Event": "SEQUENCE-FINISHED"}})
    assert runtime.state == SessionState.GUIDING


def test_snapshot_wins_when_event_state_contradicts_current_telemetry():
    runtime = SessionRuntime()
    runtime.reconcile(snapshot())
    runtime.apply_event({"Response": {"Event": "GUIDER-START"}})
    assert runtime.state == SessionState.GUIDING

    assert runtime.reconcile(snapshot(guiding=False)) == SessionState.CONNECTED
    assert runtime.authoritative is True
    assert "reconciled GUIDING to CONNECTED" in runtime.summary


def test_missing_event_is_recovered_by_authoritative_snapshot():
    runtime = SessionRuntime()
    runtime.reconcile(snapshot())

    assert runtime.reconcile(snapshot(slewing=True)) == SessionState.SLEWING
    assert runtime.authoritative is True


def test_reconnect_and_contradictory_telemetry_are_recorded():
    runtime = SessionRuntime()
    runtime.reconcile(snapshot())
    runtime.mark_recovering("websocket disconnected")
    assert runtime.state == SessionState.RECOVERING
    assert runtime.authoritative is False

    contradictory = snapshot(parked=True, slewing=True)
    assert runtime.reconcile(contradictory) == SessionState.ERROR
    assert runtime.timeline().events[-1].evidence["contradictions"]


def test_restart_never_carries_forward_a_prior_safe_claim():
    old_runtime = SessionRuntime()
    assert old_runtime.reconcile(snapshot(parked=True)) == SessionState.SAFE

    restarted_runtime = SessionRuntime()
    assert restarted_runtime.state == SessionState.STARTING
    assert restarted_runtime.authoritative is False
    assert restarted_runtime.timeline().events == []


def test_preview_paused_parking_and_offline_states_are_representable():
    runtime = SessionRuntime()
    preview = snapshot()
    preview["equipment"]["camera"]["State"] = "Previewing"
    assert runtime.reconcile(preview) == SessionState.PREVIEWING

    assert runtime.reconcile(snapshot(sequence_status="PAUSED")) == SessionState.PAUSED
    runtime.reconcile(snapshot())
    assert runtime.apply_event({"Response": {"Event": "MOUNT-PARKING"}})
    assert runtime.state == SessionState.PARKING

    runtime.mark_offline("NINA unavailable")
    assert runtime.state == SessionState.OFFLINE
    assert runtime.authoritative is True


def test_timeline_is_bounded_and_signals_a_cursor_gap():
    runtime = SessionRuntime(max_events=2)
    runtime.reconcile(snapshot())
    runtime.apply_event({"Response": {"Event": "GUIDER-START", "Time": "one"}})
    runtime.apply_event({"Response": {"Event": "GUIDER-STOP", "Time": "two"}})
    runtime.apply_event({"Response": {"Event": "GUIDER-START", "Time": "three"}})

    report = runtime.timeline(cursor=1, limit=100)
    assert report.history_gap is True
    assert [event.cursor for event in report.events] == [3, 4]


def test_state_guards_reject_park_during_slew_and_a_second_sequence():
    slewing = evaluate_action_guard(
        "park_observatory",
        SessionState.SLEWING,
        SessionFacts(mount_slewing=True),
    )
    second_sequence = evaluate_action_guard(
        "start_existing_sequence",
        SessionState.IMAGING,
        SessionFacts(
            camera_connected=True,
            mount_connected=True,
            sequence_running=True,
        ),
    )
    guider_disconnected = evaluate_action_guard(
        "start_guiding",
        SessionState.CONNECTED,
        SessionFacts(guider_connected=False),
    )

    assert slewing.allowed is False
    assert second_sequence.allowed is False
    assert guider_disconnected.allowed is False
