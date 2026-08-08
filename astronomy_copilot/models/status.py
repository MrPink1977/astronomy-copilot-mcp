from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class OverallState(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class ComponentState(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ComponentStatus(BaseModel):
    name: str
    connected: bool | None
    state: ComponentState
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ObservatoryStatus(BaseModel):
    overall_state: OverallState
    summary: str
    components: list[ComponentStatus] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "nina_advanced_api"
