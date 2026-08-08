from __future__ import annotations

from typing import Any, Protocol

from astronomy_copilot.adapters.nina import NinaResponseError, NinaUnavailableError
from astronomy_copilot.models.status import (
    ComponentState,
    ComponentStatus,
    ObservatoryStatus,
    OverallState,
)


class StatusAdapter(Protocol):
    async def get_snapshot(self) -> dict[str, Any]: ...


class ObservatoryStatusService:
    def __init__(self, adapter: StatusAdapter):
        self.adapter = adapter

    async def get_status(self) -> ObservatoryStatus:
        try:
            snapshot = await self.adapter.get_snapshot()
        except NinaUnavailableError:
            return ObservatoryStatus(
                overall_state=OverallState.OFFLINE,
                summary="NINA Advanced API is unavailable.",
                blocking_issues=["NINA is offline or did not respond before the timeout."],
            )
        except (NinaResponseError, ValueError, TypeError, KeyError):
            return ObservatoryStatus(
                overall_state=OverallState.UNKNOWN,
                summary="NINA responded, but its status could not be interpreted safely.",
                blocking_issues=["NINA returned a malformed or unsuccessful status response."],
            )

        equipment = snapshot.get("equipment")
        if not isinstance(equipment, dict):
            return ObservatoryStatus(
                overall_state=OverallState.UNKNOWN,
                summary="NINA responded, but equipment status was missing.",
                blocking_issues=["Equipment telemetry is missing or malformed."],
            )

        components: list[ComponentStatus] = []
        warnings: list[str] = []
        for name, raw in equipment.items():
            if isinstance(raw, Exception) or not isinstance(raw, dict):
                components.append(
                    ComponentStatus(name=name, connected=None, state=ComponentState.UNKNOWN)
                )
                warnings.append(f"{name} status is unavailable.")
                continue

            connected = raw.get("Connected")
            if not isinstance(connected, bool):
                components.append(
                    ComponentStatus(name=name, connected=None, state=ComponentState.UNKNOWN)
                )
                warnings.append(f"{name} did not report a valid connection state.")
                continue

            state = ComponentState.CONNECTED if connected else ComponentState.DISCONNECTED
            if name == "safety_monitor" and not connected:
                state = ComponentState.UNAVAILABLE
                warnings.append("Safety monitor is disconnected; safety is unknown, not unsafe.")
            components.append(ComponentStatus(name=name, connected=connected, state=state))

        connected_count = sum(component.connected is True for component in components)
        uncertain_count = sum(
            component.state in {ComponentState.UNKNOWN, ComponentState.UNAVAILABLE}
            for component in components
        )
        disconnected_count = sum(
            component.state == ComponentState.DISCONNECTED for component in components
        )

        if uncertain_count or disconnected_count:
            overall = OverallState.DEGRADED
            summary = (
                f"NINA is available; {connected_count} equipment components are connected, "
                f"{disconnected_count} disconnected, and {uncertain_count} unknown or unavailable."
            )
        else:
            overall = OverallState.READY
            summary = f"NINA is available; all {connected_count} reported equipment components are connected."

        return ObservatoryStatus(
            overall_state=overall,
            summary=summary,
            components=components,
            warnings=warnings,
        )
