from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class SessionState(StrEnum):
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    CONNECTED = "CONNECTED"
    PREVIEWING = "PREVIEWING"
    SLEWING = "SLEWING"
    CENTERING = "CENTERING"
    GUIDING = "GUIDING"
    IMAGING = "IMAGING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    PARKING = "PARKING"
    SAFE = "SAFE"
    ERROR = "ERROR"


class SessionEventSource(StrEnum):
    SYSTEM = "SYSTEM"
    SNAPSHOT = "SNAPSHOT"
    WEBSOCKET = "WEBSOCKET"
    COMMAND = "COMMAND"


class SessionTimelineEvent(BaseModel):
    cursor: int
    event_type: str
    source: SessionEventSource
    previous_state: SessionState
    state: SessionState
    summary: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SessionTimeline(BaseModel):
    state: SessionState
    authoritative: bool
    summary: str
    events: list[SessionTimelineEvent] = Field(default_factory=list)
    count: int
    next_cursor: int
    history_gap: bool = False
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "astronomy_copilot_session_state"
