from __future__ import annotations

import pytest
from fastmcp import Client

from astronomy_copilot.models.status import ObservatoryStatus, OverallState
from astronomy_copilot.server import mcp

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]


async def test_curated_server_exposes_exactly_one_tool():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == ["get_observatory_status"]


async def test_curated_tool_returns_stable_response_contract(monkeypatch):
    expected = ObservatoryStatus(
        overall_state=OverallState.READY,
        summary="Sanitized mock observatory is available.",
    )

    class FakeStatusService:
        async def get_status(self) -> ObservatoryStatus:
            return expected

    monkeypatch.setattr(
        "astronomy_copilot.server.build_status_service",
        lambda: FakeStatusService(),
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_observatory_status", {})

    assert result.structured_content is not None
    assert result.structured_content["overall_state"] == "READY"
    assert result.structured_content["source"] == "nina_advanced_api"
    assert set(result.structured_content) == {
        "overall_state",
        "summary",
        "components",
        "blocking_issues",
        "warnings",
        "observed_at",
        "source",
    }
