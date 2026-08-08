from __future__ import annotations

import pytest
from fastmcp import Client

from astronomy_copilot.models.actions import (
    ActionLevel,
    ActionResult,
    ActionStatus,
    AuditReport,
)
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
from astronomy_copilot.models.image_analysis import (
    AnalysisState,
    EvidenceState,
    FitsAnalysisReport,
    ImageMeasurement,
    ImageQualityIndicator,
    IndicatorState,
)
from astronomy_copilot.models.session import (
    SessionEventSource,
    SessionState,
    SessionTimeline,
    SessionTimelineEvent,
)
from astronomy_copilot.models.status import ObservatoryStatus, OverallState
from astronomy_copilot.models.workflow import (
    PrepareForImagingReport,
    WorkflowStatus,
)
from astronomy_copilot.server import action_runtime, mcp

pytestmark = [pytest.mark.contract, pytest.mark.asyncio]


async def test_curated_server_exposes_exactly_the_phase7_reviewed_tools():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == [
        "get_observatory_status",
        "get_imaging_readiness",
        "get_latest_error",
        "recommend_next_action",
        "connect_observatory",
        "capture_test_frame",
        "plate_solve_current_frame",
        "center_target",
        "start_guiding",
        "start_existing_sequence",
        "stop_sequence_safely",
        "park_observatory",
        "get_action_audit",
        "get_session_timeline",
        "analyze_fits_image",
        "prepare_for_imaging",
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


async def test_phase4_tools_default_to_typed_dry_run_contracts(monkeypatch):
    class FakeActionService:
        async def _planned(self, action, level):
            return ActionResult(
                action=action,
                action_level=level,
                status=ActionStatus.PLANNED,
                dry_run=True,
                summary="Dry run only. No write was sent.",
                audit_event_id=f"audit-{action}",
            )

        async def connect_observatory(self, request):
            return await self._planned("connect_observatory", ActionLevel.LOW_RISK_WRITE)

        async def capture_test_frame(self, request):
            return await self._planned("capture_test_frame", ActionLevel.LOW_RISK_WRITE)

        async def plate_solve_current_frame(self, request):
            return await self._planned("plate_solve_current_frame", ActionLevel.LOW_RISK_WRITE)

        async def center_target(self, request):
            return await self._planned("center_target", ActionLevel.PHYSICAL_MOTION)

        async def start_guiding(self, request):
            return await self._planned("start_guiding", ActionLevel.LOW_RISK_WRITE)

        async def start_existing_sequence(self, request):
            return await self._planned("start_existing_sequence", ActionLevel.PHYSICAL_MOTION)

        async def stop_sequence_safely(self, request):
            return await self._planned("stop_sequence_safely", ActionLevel.SESSION_ENDING)

        async def park_observatory(self, request):
            return await self._planned("park_observatory", ActionLevel.SESSION_ENDING)

        def get_audit(self, limit=20):
            return AuditReport(events=[], count=0)

    monkeypatch.setattr(
        "astronomy_copilot.server.build_action_service",
        lambda: FakeActionService(),
    )

    calls = {
        "connect_observatory": {"request": {}},
        "capture_test_frame": {"request": {}},
        "plate_solve_current_frame": {"request": {}},
        "center_target": {"request": {"ra_hours": 5.0, "dec_degrees": -10.0}},
        "start_guiding": {"request": {}},
        "start_existing_sequence": {"request": {}},
        "stop_sequence_safely": {"request": {}},
        "park_observatory": {"request": {}},
    }
    expected_fields = {
        "action",
        "action_level",
        "status",
        "dry_run",
        "summary",
        "approval_plan",
        "details",
        "audit_event_id",
        "idempotent_replay",
        "observed_at",
        "source",
    }

    async with Client(mcp) as client:
        for tool_name, arguments in calls.items():
            result = await client.call_tool(tool_name, arguments)
            assert result.structured_content is not None
            assert set(result.structured_content) == expected_fields
            assert result.structured_content["dry_run"] is True
            assert result.structured_content["status"] == "PLANNED"

        audit = await client.call_tool("get_action_audit", {"limit": 10})

    assert audit.structured_content == {
        "events": [],
        "count": 0,
        "source": "astronomy_copilot_action_policy",
    }


async def test_real_phase4_mcp_dry_runs_never_touch_the_adapter(monkeypatch):
    class ForbiddenAdapter:
        async def execute(self, *args, **kwargs):
            raise AssertionError("dry run attempted a NINA write")

        async def get_equipment_info(self, *args, **kwargs):
            raise AssertionError("dry run attempted a NINA read")

        async def cancel(self, *args, **kwargs):
            raise AssertionError("dry run attempted cancellation")

    monkeypatch.setattr(
        "astronomy_copilot.server.build_nina_adapter",
        lambda: ForbiddenAdapter(),
    )
    action_runtime.clear()
    try:
        async with Client(mcp) as client:
            capture = await client.call_tool("capture_test_frame", {"request": {}})
            center = await client.call_tool(
                "center_target",
                {"request": {"ra_hours": 5.0, "dec_degrees": 10.0}},
            )

        assert capture.structured_content["status"] == "PLANNED"
        assert center.structured_content["status"] == "PLANNED"
        assert center.structured_content["approval_plan"] is not None
    finally:
        action_runtime.clear()


async def test_phase5_timeline_has_a_stable_bounded_contract(monkeypatch):
    class FakeSessionService:
        async def get_timeline(self, cursor=0, limit=50):
            return SessionTimeline(
                state=SessionState.CONNECTED,
                authoritative=True,
                summary="Authoritative snapshot reports session state CONNECTED.",
                events=[
                    SessionTimelineEvent(
                        cursor=3,
                        event_type="SNAPSHOT-RECONCILED",
                        source=SessionEventSource.SNAPSHOT,
                        previous_state=SessionState.STARTING,
                        state=SessionState.CONNECTED,
                        summary="Snapshot reconciled.",
                    )
                ],
                count=1,
                next_cursor=3,
            )

    monkeypatch.setattr(
        "astronomy_copilot.server.build_session_service",
        lambda: FakeSessionService(),
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_session_timeline",
            {"cursor": 0, "limit": 10},
        )

    assert result.structured_content is not None
    assert set(result.structured_content) == {
        "state",
        "authoritative",
        "summary",
        "events",
        "count",
        "next_cursor",
        "history_gap",
        "observed_at",
        "source",
    }
    assert set(result.structured_content["events"][0]) == {
        "cursor",
        "event_type",
        "source",
        "previous_state",
        "state",
        "summary",
        "occurred_at",
        "evidence",
    }


async def test_phase6_fits_analysis_has_a_stable_local_evidence_contract(monkeypatch):
    class FakeFitsAnalysisService:
        def analyze(self, request):
            return FitsAnalysisReport(
                state=AnalysisState.COMPLETE,
                summary="Controlled local FITS analysis completed.",
                file_name="controlled.fits",
                hdu_index=0,
                metadata={
                    "image_width": ImageMeasurement(
                        state=EvidenceState.AVAILABLE,
                        value=64,
                        unit="pixels",
                        method="FITS NAXIS1 image dimension",
                    )
                },
                indicators=[
                    ImageQualityIndicator(
                        code="controlled_indicator",
                        state=IndicatorState.NOT_DETECTED,
                        summary="Controlled threshold was not reached.",
                        method="Controlled fixture method",
                        threshold=">= 1 controlled unit",
                        evidence=["image_width"],
                        limitations=["Controlled fixture only."],
                    )
                ],
            )

    monkeypatch.setattr(
        "astronomy_copilot.server.build_fits_analysis_service",
        lambda: FakeFitsAnalysisService(),
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "analyze_fits_image",
            {"request": {"file_path": "controlled.fits"}},
        )

    assert result.structured_content is not None
    assert set(result.structured_content) == {
        "state",
        "summary",
        "file_name",
        "hdu_index",
        "metadata",
        "measurements",
        "indicators",
        "warnings",
        "limitations",
        "observed_at",
        "source",
    }
    assert set(result.structured_content["metadata"]["image_width"]) == {
        "state",
        "value",
        "unit",
        "method",
        "threshold",
        "limitations",
    }
    assert result.structured_content["source"] == "local_fits_read_only"
    assert set(result.structured_content["indicators"][0]) == {
        "code",
        "state",
        "summary",
        "method",
        "threshold",
        "evidence",
        "limitations",
    }


async def test_phase7_workflow_has_a_stable_supervised_contract(monkeypatch):
    class FakeWorkflowService:
        async def prepare(self, request):
            return PrepareForImagingReport(
                workflow_id="controlled-workflow",
                status=WorkflowStatus.PROPOSED,
                summary="Controlled plan proposed without writes.",
                dry_run=True,
            )

    monkeypatch.setattr(
        "astronomy_copilot.server.build_prepare_for_imaging_service",
        lambda: FakeWorkflowService(),
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "prepare_for_imaging",
            {
                "request": {
                    "target_name": "Controlled target",
                    "ra_hours": 10.0,
                    "dec_degrees": 20.0,
                }
            },
        )

    assert result.structured_content is not None
    assert set(result.structured_content) == {
        "workflow_id",
        "status",
        "summary",
        "dry_run",
        "proposed_plan",
        "steps",
        "action_results",
        "image_analyses",
        "final_image_analysis",
        "required_approval",
        "plate_solve_attempts",
        "changed_variables",
        "final_readiness",
        "session_timeline",
        "timeline",
        "warnings",
        "observed_at",
        "source",
    }
    assert result.structured_content["status"] == "PROPOSED"
    assert result.structured_content["source"] == "astronomy_copilot_supervised_workflow"
