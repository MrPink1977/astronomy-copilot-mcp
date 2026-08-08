from __future__ import annotations

import pytest

from astronomy_copilot.adapters.nina import NinaResponseError, NinaUnavailableError
from astronomy_copilot.services.status import ObservatoryStatusService

pytestmark = pytest.mark.unit


class FakeAdapter:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def get_snapshot(self):
        if self.error:
            raise self.error
        return self.result


def snapshot(**equipment):
    return {"version": "2.2.15.2", "equipment": equipment}


@pytest.mark.asyncio
async def test_healthy_status_is_ready():
    service = ObservatoryStatusService(
        FakeAdapter(snapshot(camera={"Connected": True}, mount={"Connected": True}))
    )
    result = await service.get_status()
    assert result.overall_state == "READY"
    assert all(component.state == "CONNECTED" for component in result.components)


@pytest.mark.asyncio
async def test_partial_status_is_degraded_and_does_not_count_server():
    service = ObservatoryStatusService(
        FakeAdapter(
            snapshot(
                camera={"Connected": True},
                mount={"Connected": False},
                safety_monitor={"Connected": False, "IsSafe": False},
            )
        )
    )
    result = await service.get_status()
    assert result.overall_state == "DEGRADED"
    assert "1 equipment components are connected" in result.summary
    safety = next(item for item in result.components if item.name == "safety_monitor")
    assert safety.state == "UNAVAILABLE"
    assert any("unknown, not unsafe" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_unavailable_status_is_offline():
    service = ObservatoryStatusService(FakeAdapter(error=NinaUnavailableError()))
    result = await service.get_status()
    assert result.overall_state == "OFFLINE"
    assert result.blocking_issues


@pytest.mark.asyncio
async def test_malformed_status_is_unknown():
    service = ObservatoryStatusService(FakeAdapter({"version": "2.2.15.2", "equipment": []}))
    result = await service.get_status()
    assert result.overall_state == "UNKNOWN"
    assert result.blocking_issues


@pytest.mark.asyncio
async def test_one_malformed_component_does_not_hide_other_components():
    service = ObservatoryStatusService(
        FakeAdapter(snapshot(camera={"Connected": True}, mount=NinaResponseError("bad")))
    )
    result = await service.get_status()
    assert result.overall_state == "DEGRADED"
    assert len(result.components) == 2
    assert next(item for item in result.components if item.name == "mount").state == "UNKNOWN"
