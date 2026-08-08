from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any, Protocol

from astronomy_copilot.adapters.nina import NinaResponseError, NinaUnavailableError
from astronomy_copilot.models.session import (
    SessionEventSource,
    SessionState,
    SessionTimeline,
    SessionTimelineEvent,
)
from astronomy_copilot.policy.state_guards import (
    SessionFacts,
    StateGuardDecision,
    evaluate_action_guard,
)


class SessionSnapshotAdapter(Protocol):
    async def get_session_snapshot(self) -> dict[str, Any]: ...


class SessionEventAdapter(Protocol):
    def events(self) -> AsyncIterator[dict[str, Any]]: ...


def _value(mapping: dict[str, Any] | None, *names: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    lowered = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


def _truth(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.casefold() in {"true", "false"}:
        return value.casefold() == "true"
    return None


def _state_text(mapping: dict[str, Any] | None) -> str:
    value = _value(mapping, "State", "CameraState", "Status", "CurrentOperation")
    return value.casefold() if isinstance(value, str) else ""


def _sequence_statuses(value: Any) -> set[str]:
    statuses: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() == "status" and isinstance(child, str):
                statuses.add(child.casefold())
            else:
                statuses.update(_sequence_statuses(child))
    elif isinstance(value, list):
        for child in value:
            statuses.update(_sequence_statuses(child))
    return statuses


def facts_from_snapshot(snapshot: dict[str, Any]) -> tuple[SessionFacts, list[str], str]:
    equipment = snapshot.get("equipment")
    diagnostics = snapshot.get("diagnostics")
    session = snapshot.get("session")
    equipment = equipment if isinstance(equipment, dict) else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    session = session if isinstance(session, dict) else {}

    camera = equipment.get("camera") if isinstance(equipment.get("camera"), dict) else None
    mount = equipment.get("mount") if isinstance(equipment.get("mount"), dict) else None
    guider = equipment.get("guider") if isinstance(equipment.get("guider"), dict) else None
    dome = equipment.get("dome") if isinstance(equipment.get("dome"), dict) else None
    plate = (
        diagnostics.get("plate_solving")
        if isinstance(diagnostics.get("plate_solving"), dict)
        else None
    )
    sequence = session.get("sequence")

    camera_state = _state_text(camera)
    guider_state = _state_text(guider)
    mount_state = _state_text(mount)
    plate_state = _state_text(plate)
    statuses = _sequence_statuses(sequence) if isinstance(sequence, (dict, list)) else set()
    sequence_known = isinstance(sequence, (dict, list))
    sequence_running = bool(statuses & {"running", "paused"}) if sequence_known else None
    camera_active = _truth(_value(camera, "IsExposing"))
    if camera_active is not True:
        camera_active = any(token in camera_state for token in ("expos", "download", "capture"))

    facts = SessionFacts(
        camera_connected=_truth(_value(camera, "Connected")),
        camera_active=camera_active,
        mount_connected=_truth(_value(mount, "Connected")),
        mount_slewing=_truth(_value(mount, "Slewing")),
        mount_parked=_truth(_value(mount, "AtPark")),
        guider_connected=_truth(_value(guider, "Connected")),
        guiding="guiding" in guider_state,
        sequence_running=sequence_running,
        dome_closed=(
            "closed" in str(_value(dome, "ShutterStatus", "State")).casefold()
            if isinstance(dome, dict) and _truth(_value(dome, "Connected")) is True
            else None
        ),
    )

    contradictions: list[str] = []
    if facts.mount_parked is True and facts.mount_slewing is True:
        contradictions.append("mount reports parked and slewing")
    if facts.camera_connected is False and facts.camera_active is True:
        contradictions.append("disconnected camera reports an active exposure")
    if facts.guider_connected is False and facts.guiding is True:
        contradictions.append("disconnected guider reports guiding")

    operation = " ".join((mount_state, plate_state, str(_value(mount, "CurrentOperation"))))
    if "park" in operation and facts.mount_parked is not True:
        hint = "parking"
    elif "center" in operation and "running" in operation:
        hint = "centering"
    elif "paused" in statuses:
        hint = "paused"
    elif any(token in camera_state for token in ("loop", "preview")):
        hint = "previewing"
    else:
        hint = ""
    return facts, contradictions, hint


def state_from_facts(
    facts: SessionFacts,
    *,
    contradictions: list[str] | None = None,
    hint: str = "",
) -> SessionState:
    if contradictions:
        return SessionState.ERROR
    if hint == "parking":
        return SessionState.PARKING
    if hint == "centering":
        return SessionState.CENTERING
    if facts.mount_slewing:
        return SessionState.SLEWING
    if hint == "paused":
        return SessionState.PAUSED
    if facts.camera_active or facts.sequence_running:
        return SessionState.IMAGING
    if facts.guiding:
        return SessionState.GUIDING
    if hint == "previewing":
        return SessionState.PREVIEWING
    if (
        facts.mount_parked is True
        and facts.camera_active is False
        and facts.sequence_running is False
        and facts.dome_closed is not False
    ):
        return SessionState.SAFE
    if any(
        value is True
        for value in (
            facts.camera_connected,
            facts.mount_connected,
            facts.guider_connected,
        )
    ):
        return SessionState.CONNECTED
    return SessionState.STARTING


class SessionRuntime:
    def __init__(self, max_events: int = 500):
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._events: deque[SessionTimelineEvent] = deque(maxlen=max_events)
        self._last_event_identity: str | None = None
        self._cursor = 0
        self.state = SessionState.STARTING
        self.authoritative = False
        self.facts = SessionFacts()
        self.summary = "Waiting for the first authoritative NINA status snapshot."

    def _append(
        self,
        event_type: str,
        source: SessionEventSource,
        state: SessionState,
        summary: str,
        evidence: dict[str, str | int | float | bool | None] | None = None,
    ) -> SessionTimelineEvent:
        previous = self.state
        self.state = state
        self.summary = summary
        self._cursor += 1
        event = SessionTimelineEvent(
            cursor=self._cursor,
            event_type=event_type,
            source=source,
            previous_state=previous,
            state=state,
            summary=summary,
            evidence=evidence or {},
        )
        self._events.append(event)
        return event

    def mark_recovering(self, reason: str) -> None:
        self.authoritative = False
        self._append(
            "RECONNECTING",
            SessionEventSource.SYSTEM,
            SessionState.RECOVERING,
            reason,
        )

    def mark_offline(self, reason: str) -> None:
        self.authoritative = True
        self.facts = SessionFacts()
        self._append(
            "SNAPSHOT-UNAVAILABLE", SessionEventSource.SNAPSHOT, SessionState.OFFLINE, reason
        )

    def reconcile(self, snapshot: dict[str, Any]) -> SessionState:
        prior = self.state
        facts, contradictions, hint = facts_from_snapshot(snapshot)
        state = state_from_facts(facts, contradictions=contradictions, hint=hint)
        self.facts = facts
        self.authoritative = True
        if contradictions:
            summary = "Authoritative telemetry is internally contradictory."
        elif prior != state and prior not in {SessionState.STARTING, SessionState.RECOVERING}:
            summary = f"Authoritative snapshot reconciled {prior} to {state}."
        else:
            summary = f"Authoritative snapshot reports session state {state}."
        self._append(
            "SNAPSHOT-RECONCILED",
            SessionEventSource.SNAPSHOT,
            state,
            summary,
            {
                "contradictions": "; ".join(contradictions) or None,
                "sequence_running": facts.sequence_running,
                "mount_slewing": facts.mount_slewing,
                "mount_parked": facts.mount_parked,
            },
        )
        return state

    def _remember(self, identity: str) -> bool:
        if identity == self._last_event_identity:
            return False
        self._last_event_identity = identity
        return True

    def apply_event(self, payload: dict[str, Any]) -> bool:
        response = payload.get("Response")
        body = response if isinstance(response, dict) else payload
        event_name = _value(body, "Event")
        if not isinstance(event_name, str) or not event_name.strip():
            return False
        event_name = event_name.strip().upper()
        canonical = json.dumps(body, sort_keys=True, default=str, separators=(",", ":"))
        identity = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if not self._remember(identity):
            return False

        facts = self.facts
        hint = ""
        if event_name == "CAMERA-CONNECTED":
            facts = replace(facts, camera_connected=True)
        elif event_name == "CAMERA-DISCONNECTED":
            facts = replace(facts, camera_connected=False, camera_active=False)
        elif event_name == "CAMERA-DOWNLOAD-TIMEOUT":
            self.authoritative = False
            self._append(
                event_name,
                SessionEventSource.WEBSOCKET,
                SessionState.ERROR,
                "Camera download timed out.",
            )
            return True
        elif event_name == "GUIDER-CONNECTED":
            facts = replace(facts, guider_connected=True)
        elif event_name == "GUIDER-DISCONNECTED":
            facts = replace(facts, guider_connected=False, guiding=False)
        elif event_name == "GUIDER-START":
            facts = replace(facts, guider_connected=True, guiding=True)
        elif event_name == "GUIDER-STOP":
            facts = replace(facts, guiding=False)
        elif event_name in {"MOUNT-CONNECTED", "MOUNT-UNPARKED"}:
            facts = replace(facts, mount_connected=True, mount_parked=False)
        elif event_name == "MOUNT-DISCONNECTED":
            facts = replace(facts, mount_connected=False, mount_slewing=False)
        elif event_name in {"MOUNT-BEFORE-FLIP", "MOUNT-SLEWING"}:
            facts = replace(facts, mount_slewing=True, mount_parked=False)
        elif event_name == "MOUNT-AFTER-FLIP":
            facts = replace(facts, mount_slewing=False)
        elif event_name == "MOUNT-CENTER":
            facts = replace(facts, mount_slewing=True, mount_parked=False)
            hint = "centering"
        elif event_name == "MOUNT-PARKING":
            hint = "parking"
        elif event_name == "MOUNT-PARKED":
            facts = replace(facts, mount_slewing=False, mount_parked=True)
        elif event_name == "SEQUENCE-STARTING":
            facts = replace(facts, sequence_running=True)
        elif event_name == "SEQUENCE-FINISHED":
            facts = replace(facts, sequence_running=False, camera_active=False)
        else:
            return False

        self.facts = facts
        self.authoritative = False
        state = state_from_facts(facts, hint=hint)
        self._append(
            event_name,
            SessionEventSource.WEBSOCKET,
            state,
            f"NINA websocket event {event_name} updated the live session state to {state}.",
            {"upstream_time": _value(body, "Time")},
        )
        return True

    def timeline(self, cursor: int = 0, limit: int = 100) -> SessionTimeline:
        earliest = self._events[0].cursor if self._events else self._cursor + 1
        history_gap = cursor > 0 and cursor < earliest - 1
        events = [event for event in self._events if event.cursor > cursor][:limit]
        return SessionTimeline(
            state=self.state,
            authoritative=self.authoritative,
            summary=self.summary,
            events=events,
            count=len(events),
            next_cursor=events[-1].cursor if events else self._cursor,
            history_gap=history_gap,
        )


class SessionService:
    def __init__(
        self,
        snapshot_adapter: SessionSnapshotAdapter,
        runtime: SessionRuntime,
        event_adapter: SessionEventAdapter | None = None,
    ):
        self.snapshot_adapter = snapshot_adapter
        self.runtime = runtime
        self.event_adapter = event_adapter
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def reconcile(self) -> SessionState:
        async with self._lock:
            try:
                snapshot = await self.snapshot_adapter.get_session_snapshot()
            except (NinaUnavailableError, NinaResponseError, TimeoutError) as exc:
                self.runtime.mark_offline(str(exc)[:300])
                return self.runtime.state
            return self.runtime.reconcile(snapshot)

    async def start(self) -> None:
        if not self.runtime.authoritative:
            await self.reconcile()
        if self.event_adapter is not None and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._run_events())

    async def _run_events(self) -> None:
        delay = 0.25
        while True:
            try:
                assert self.event_adapter is not None
                async for payload in self.event_adapter.events():
                    self.runtime.apply_event(payload)
                self.runtime.mark_recovering(
                    "NINA event websocket disconnected; reconciling status."
                )
            except NinaUnavailableError:
                self.runtime.mark_recovering(
                    "NINA event websocket is unavailable; reconciling status."
                )
            await self.reconcile()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 5.0)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def get_timeline(self, cursor: int = 0, limit: int = 100) -> SessionTimeline:
        await self.start()
        return self.runtime.timeline(cursor, limit)

    async def guard(self, action: str) -> StateGuardDecision:
        await self.reconcile()
        return evaluate_action_guard(action, self.runtime.state, self.runtime.facts)
