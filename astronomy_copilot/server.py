from __future__ import annotations

import asyncio
import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from astronomy_copilot.adapters.nina import NinaActionAdapter
from astronomy_copilot.adapters.nina_events import NinaEventAdapter
from astronomy_copilot.models.actions import (
    ActionResult,
    AuditReport,
    CaptureTestFrameInput,
    CenterTargetInput,
    ConnectObservatoryInput,
    ParkObservatoryInput,
    PlateSolveCurrentFrameInput,
    StartExistingSequenceInput,
    StartGuidingInput,
    StopSequenceInput,
)
from astronomy_copilot.models.diagnostics import (
    ImagingReadiness,
    LatestErrorReport,
    NextActionRecommendation,
)
from astronomy_copilot.models.image_analysis import FitsAnalysisInput, FitsAnalysisReport
from astronomy_copilot.models.session import SessionTimeline
from astronomy_copilot.models.status import ObservatoryStatus
from astronomy_copilot.policy.approvals import ActionRuntime
from astronomy_copilot.services.actions import ControlledActionService
from astronomy_copilot.services.image_analysis import FitsAnalysisService
from astronomy_copilot.services.readiness import ImagingReadinessService
from astronomy_copilot.services.session import SessionRuntime, SessionService
from astronomy_copilot.services.status import ObservatoryStatusService

mcp = FastMCP("Astronomy Copilot")
action_runtime = ActionRuntime()
session_runtime = SessionRuntime()
_session_service: SessionService | None = None


def build_nina_adapter() -> NinaActionAdapter:
    return NinaActionAdapter(
        host=os.getenv("NINA_HOST", "127.0.0.1"),
        port=int(os.getenv("NINA_PORT", "1888")),
        timeout_seconds=float(os.getenv("NINA_TIMEOUT_SECONDS", "5")),
    )


def build_status_service() -> ObservatoryStatusService:
    return ObservatoryStatusService(build_nina_adapter())


def build_readiness_service() -> ImagingReadinessService:
    return ImagingReadinessService(build_nina_adapter())


def build_fits_analysis_service() -> FitsAnalysisService:
    return FitsAnalysisService()


def build_session_service() -> SessionService:
    global _session_service
    if _session_service is None:
        host = os.getenv("NINA_HOST", "127.0.0.1")
        port = int(os.getenv("NINA_PORT", "1888"))
        timeout = float(os.getenv("NINA_TIMEOUT_SECONDS", "5"))
        _session_service = SessionService(
            build_nina_adapter(),
            session_runtime,
            NinaEventAdapter(host=host, port=port, timeout_seconds=timeout),
        )
    return _session_service


def build_action_service() -> ControlledActionService:
    return ControlledActionService(build_nina_adapter(), action_runtime, build_session_service())


@mcp.tool()
async def get_observatory_status() -> ObservatoryStatus:
    """Return a normalized, read-only snapshot of NINA equipment status."""
    return await build_status_service().get_status()


@mcp.tool()
async def get_imaging_readiness() -> ImagingReadiness:
    """Return deterministic camera, mount, guider, and plate-solving readiness."""
    return await build_readiness_service().get_readiness()


@mcp.tool()
async def get_latest_error() -> LatestErrorReport:
    """Return the latest sanitized current error reported by reviewed telemetry."""
    return await build_readiness_service().get_latest_error()


@mcp.tool()
async def recommend_next_action(
    previous_recommendation_id: str | None = None,
) -> NextActionRecommendation:
    """Recommend one evidence-linked action and warn against unchanged retries."""
    return await build_readiness_service().recommend_next_action(previous_recommendation_id)


@mcp.tool()
async def connect_observatory(request: ConnectObservatoryInput) -> ActionResult:
    """Dry-run or connect the configured camera, mount, and guider under Level 1 policy."""
    return await build_action_service().connect_observatory(request)


@mcp.tool()
async def capture_test_frame(request: CaptureTestFrameInput) -> ActionResult:
    """Dry-run or capture one bounded test frame under Level 1 policy."""
    return await build_action_service().capture_test_frame(request)


@mcp.tool()
async def plate_solve_current_frame(request: PlateSolveCurrentFrameInput) -> ActionResult:
    """Dry-run or solve the current prepared frame without requesting mount motion."""
    return await build_action_service().plate_solve_current_frame(request)


@mcp.tool()
async def center_target(request: CenterTargetInput) -> ActionResult:
    """Plan or execute an explicitly approved Level 2 target-centering operation."""
    return await build_action_service().center_target(request)


@mcp.tool()
async def start_guiding(request: StartGuidingInput) -> ActionResult:
    """Dry-run or start guiding under Level 1 policy."""
    return await build_action_service().start_guiding(request)


@mcp.tool()
async def start_existing_sequence(request: StartExistingSequenceInput) -> ActionResult:
    """Dry-run or start the existing sequence with NINA validation enabled."""
    return await build_action_service().start_existing_sequence(request)


@mcp.tool()
async def stop_sequence_safely(request: StopSequenceInput) -> ActionResult:
    """Plan or execute an explicitly approved Level 3 sequence stop."""
    return await build_action_service().stop_sequence_safely(request)


@mcp.tool()
async def park_observatory(request: ParkObservatoryInput) -> ActionResult:
    """Plan or execute an explicitly approved Level 3 mount park."""
    return await build_action_service().park_observatory(request)


@mcp.tool()
async def get_action_audit(
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> AuditReport:
    """Return the bounded in-memory audit trail for attempted controlled actions."""
    return build_action_service().get_audit(limit)


@mcp.tool()
async def get_session_timeline(
    cursor: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=100)] = 50,
) -> SessionTimeline:
    """Return bounded reconciled session-state events after the supplied cursor."""
    return await build_session_service().get_timeline(cursor, limit)


@mcp.tool()
async def analyze_fits_image(request: FitsAnalysisInput) -> FitsAnalysisReport:
    """Analyze one local FITS image read-only; no image bytes leave the machine."""
    return await asyncio.to_thread(build_fits_analysis_service().analyze, request)


if __name__ == "__main__":
    mcp.run()
