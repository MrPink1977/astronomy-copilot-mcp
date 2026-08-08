from __future__ import annotations

import pytest
from fastmcp import Client

from astronomy_copilot.models.diagnostics import (
    Confidence,
    DiagnosticFinding,
    Evidence,
    FindingImpact,
    ImagingReadiness,
    LatestErrorReport,
    LatestErrorState,
    NextActionRecommendation,
    Severity,
)
from astronomy_copilot.models.status import ObservatoryStatus, OverallState
from astronomy_copilot.server import mcp

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]


async def test_curated_server_exposes_exactly_the_four_phase3_read_only_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == [
        "get_observatory_status",
        "get_imaging_readiness",
        "get_latest_error",
        "recommend_next_action",
    ]


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


async def test_phase3_tools_return_stable_typed_contracts(monkeypatch):
    finding = DiagnosticFinding(
        code="camera.disconnected",
        component="camera",
        issue="The imaging camera is disconnected.",
        evidence=[
            Evidence(
                field="Connected",
                observed=False,
                source="nina_advanced_api.camera",
            )
        ],
        severity=Severity.ERROR,
        confidence=Confidence.HIGH,
        impact=FindingImpact.BLOCKING,
        recommended_action="Connect the imaging camera in NINA, then refresh readiness.",
        retry_variable="camera_connection",
    )

    class FakeReadinessService:
        async def get_readiness(self) -> ImagingReadiness:
            return ImagingReadiness(
                state=OverallState.BLOCKED,
                ready=False,
                summary="Imaging is blocked by one known condition.",
                blocking_issues=[finding],
            )

        async def get_latest_error(self) -> LatestErrorReport:
            return LatestErrorReport(
                state=LatestErrorState.NONE,
                summary="No current error was reported.",
            )

        async def recommend_next_action(
            self, previous_recommendation_id: str | None = None
        ) -> NextActionRecommendation:
            return NextActionRecommendation(
                readiness_state=OverallState.BLOCKED,
                recommendation=finding,
                recommendation_id="0123456789abcdef",
                should_retry=previous_recommendation_id != "0123456789abcdef",
            )

    monkeypatch.setattr(
        "astronomy_copilot.server.build_readiness_service",
        lambda: FakeReadinessService(),
    )

    async with Client(mcp) as client:
        readiness = await client.call_tool("get_imaging_readiness", {})
        latest_error = await client.call_tool("get_latest_error", {})
        recommendation = await client.call_tool(
            "recommend_next_action",
            {"previous_recommendation_id": "0123456789abcdef"},
        )

    assert readiness.structured_content is not None
    assert set(readiness.structured_content) == {
        "state",
        "ready",
        "summary",
        "blocking_issues",
        "warnings",
        "unknowns",
        "observed_at",
        "source",
    }
    assert readiness.structured_content["blocking_issues"][0]["evidence"][0]["observed"] is False

    assert latest_error.structured_content is not None
    assert set(latest_error.structured_content) == {
        "state",
        "summary",
        "error",
        "warnings",
        "observed_at",
        "source",
    }

    assert recommendation.structured_content is not None
    assert set(recommendation.structured_content) == {
        "readiness_state",
        "recommendation",
        "recommendation_id",
        "should_retry",
        "repeat_warning",
        "observed_at",
        "source",
    }
    assert recommendation.structured_content["should_retry"] is False
