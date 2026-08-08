from __future__ import annotations

import os

from fastmcp import FastMCP

from astronomy_copilot.adapters.nina import NinaReadOnlyAdapter
from astronomy_copilot.models.diagnostics import (
    ImagingReadiness,
    LatestErrorReport,
    NextActionRecommendation,
)
from astronomy_copilot.models.status import ObservatoryStatus
from astronomy_copilot.services.readiness import ImagingReadinessService
from astronomy_copilot.services.status import ObservatoryStatusService

mcp = FastMCP("Astronomy Copilot")


def build_nina_adapter() -> NinaReadOnlyAdapter:
    return NinaReadOnlyAdapter(
        host=os.getenv("NINA_HOST", "127.0.0.1"),
        port=int(os.getenv("NINA_PORT", "1888")),
        timeout_seconds=float(os.getenv("NINA_TIMEOUT_SECONDS", "5")),
    )


def build_status_service() -> ObservatoryStatusService:
    return ObservatoryStatusService(build_nina_adapter())


def build_readiness_service() -> ImagingReadinessService:
    return ImagingReadinessService(build_nina_adapter())


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


if __name__ == "__main__":
    mcp.run()
