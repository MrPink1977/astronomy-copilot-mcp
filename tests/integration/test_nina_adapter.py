from __future__ import annotations

import pytest

from astronomy_copilot.adapters.nina import (
    NinaReadOnlyAdapter,
    NinaResponseError,
    NinaUnavailableError,
)
from astronomy_copilot.services.status import ObservatoryStatusService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def adapter_for(nina_mock_server, *, timeout_seconds: float = 1.0) -> NinaReadOnlyAdapter:
    assert nina_mock_server.port is not None
    return NinaReadOnlyAdapter(
        host=nina_mock_server.host,
        port=nina_mock_server.port,
        timeout_seconds=timeout_seconds,
    )


async def test_adapter_reads_complete_sanitized_snapshot(nina_mock_server, nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    nina_mock_server.set_scenario(scenario)

    result = await adapter_for(nina_mock_server).get_snapshot()

    assert result["version"] == "2.2.15.2"
    assert set(result["equipment"]) == set(NinaReadOnlyAdapter.EQUIPMENT_ENDPOINTS)
    assert all(component["Connected"] for component in result["equipment"].values())
    assert set(nina_mock_server.requests) == set(scenario)


async def test_component_http_error_is_isolated(nina_mock_server, nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    nina_mock_server.set_scenario(scenario)
    nina_mock_server.set_json(
        "equipment/mount/info",
        nina_fixture("http_error.json"),
        status=503,
    )

    result = await adapter_for(nina_mock_server).get_snapshot()

    assert isinstance(result["equipment"]["mount"], NinaResponseError)
    assert result["equipment"]["camera"]["Connected"] is True


async def test_unsuccessful_component_response_is_isolated(nina_mock_server, nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    nina_mock_server.set_scenario(scenario)
    nina_mock_server.set_json(
        "equipment/weather/info",
        nina_fixture("unsuccessful_response.json"),
    )

    result = await adapter_for(nina_mock_server).get_snapshot()

    assert isinstance(result["equipment"]["weather"], NinaResponseError)


async def test_malformed_version_response_is_rejected(nina_mock_server, nina_fixture):
    nina_mock_server.set_json("version", nina_fixture("malformed_response.json"))

    with pytest.raises(NinaResponseError, match="unsuccessful response"):
        await adapter_for(nina_mock_server).get_snapshot()


async def test_invalid_json_is_reported_as_response_error(nina_mock_server):
    nina_mock_server.set_text("version", "{not valid JSON")

    with pytest.raises(NinaResponseError, match="invalid JSON"):
        await adapter_for(nina_mock_server).get_snapshot()


async def test_real_http_timeout_becomes_nina_unavailable(nina_mock_server, nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    nina_mock_server.set_json("version", scenario["version"], delay_seconds=0.5)

    with pytest.raises(NinaUnavailableError) as raised:
        await adapter_for(nina_mock_server, timeout_seconds=0.1).get_snapshot()

    assert raised.value.__cause__ is not None
    assert nina_mock_server.requests == ["version"]


async def test_status_service_integrates_with_partial_http_snapshot(nina_mock_server, nina_fixture):
    scenario = nina_fixture("healthy_status.json")
    nina_mock_server.set_scenario(scenario)
    nina_mock_server.set_json(
        "equipment/mount/info",
        nina_fixture("disconnected_component.json"),
    )
    nina_mock_server.set_json(
        "equipment/safetymonitor/info",
        nina_fixture("disconnected_component.json"),
    )

    result = await ObservatoryStatusService(adapter_for(nina_mock_server)).get_status()

    assert result.overall_state == "DEGRADED"
    assert "8 equipment components are connected" in result.summary
    assert next(
        component for component in result.components if component.name == "mount"
    ).state == ("DISCONNECTED")
    assert (
        next(
            component for component in result.components if component.name == "safety_monitor"
        ).state
        == "UNAVAILABLE"
    )
