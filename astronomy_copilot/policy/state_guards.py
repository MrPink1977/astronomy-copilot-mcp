from __future__ import annotations

from dataclasses import dataclass

from astronomy_copilot.models.session import SessionState


@dataclass(frozen=True, slots=True)
class SessionFacts:
    camera_connected: bool | None = None
    camera_active: bool | None = None
    mount_connected: bool | None = None
    mount_slewing: bool | None = None
    mount_parked: bool | None = None
    guider_connected: bool | None = None
    guiding: bool | None = None
    sequence_running: bool | None = None
    dome_closed: bool | None = None


@dataclass(frozen=True, slots=True)
class StateGuardDecision:
    allowed: bool
    state: SessionState
    reason: str


def evaluate_action_guard(
    action: str,
    state: SessionState,
    facts: SessionFacts,
) -> StateGuardDecision:
    """Apply deterministic state-only guards before any approved write is consumed."""
    if state in {
        SessionState.OFFLINE,
        SessionState.ERROR,
        SessionState.RECOVERING,
    } or (state == SessionState.STARTING and action != "connect_observatory"):
        return StateGuardDecision(False, state, f"session state is {state}")

    if action == "park_observatory":
        if state in {SessionState.SLEWING, SessionState.CENTERING, SessionState.PARKING}:
            return StateGuardDecision(False, state, "mount motion is already in progress")
        if facts.camera_active or facts.sequence_running:
            return StateGuardDecision(False, state, "an exposure or sequence is active")

    if action == "start_existing_sequence":
        if facts.sequence_running or state in {SessionState.IMAGING, SessionState.PAUSED}:
            return StateGuardDecision(False, state, "a sequence is already active")
        if state in {SessionState.SLEWING, SessionState.CENTERING, SessionState.PARKING}:
            return StateGuardDecision(False, state, "mount motion is already in progress")
        if facts.camera_connected is not True or facts.mount_connected is not True:
            return StateGuardDecision(False, state, "camera and mount must both be connected")

    if action == "start_guiding":
        if facts.guider_connected is not True:
            return StateGuardDecision(False, state, "guide camera is not connected")
        if state in {SessionState.SLEWING, SessionState.CENTERING, SessionState.PARKING}:
            return StateGuardDecision(False, state, "mount motion is already in progress")

    if action == "capture_test_frame" and (facts.camera_active or facts.sequence_running):
        return StateGuardDecision(False, state, "the camera or sequence is already active")

    if action == "plate_solve_current_frame" and facts.camera_active:
        return StateGuardDecision(False, state, "the camera is exposing or downloading")

    if action == "center_target":
        if state in {
            SessionState.SLEWING,
            SessionState.CENTERING,
            SessionState.PARKING,
            SessionState.IMAGING,
        }:
            return StateGuardDecision(False, state, "the observatory is already busy")
        if facts.mount_parked is True:
            return StateGuardDecision(False, state, "the mount is parked")

    if action == "stop_sequence_safely" and facts.sequence_running is not True:
        return StateGuardDecision(False, state, "no active sequence was observed")

    return StateGuardDecision(True, state, "operation is valid for the current session state")
