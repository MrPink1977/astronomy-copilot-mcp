from __future__ import annotations

import os

from fastmcp import FastMCP

from astronomy_copilot.adapters.nina import NinaReadOnlyAdapter
from astronomy_copilot.models.status import ObservatoryStatus
from astronomy_copilot.services.status import ObservatoryStatusService

mcp = FastMCP("Astronomy Copilot")


def build_status_service() -> ObservatoryStatusService:
    return ObservatoryStatusService(
        NinaReadOnlyAdapter(
            host=os.getenv("NINA_HOST", "127.0.0.1"),
            port=int(os.getenv("NINA_PORT", "1888")),
            timeout_seconds=float(os.getenv("NINA_TIMEOUT_SECONDS", "5")),
        )
    )


@mcp.tool()
async def get_observatory_status() -> ObservatoryStatus:
    """Return a normalized, read-only snapshot of NINA equipment status."""
    return await build_status_service().get_status()


if __name__ == "__main__":
    mcp.run()
