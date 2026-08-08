from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from astronomy_copilot.models.status import OverallState


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class FindingImpact(StrEnum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    UNKNOWN = "UNKNOWN"


class LatestErrorState(StrEnum):
    FOUND = "FOUND"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"
    OFFLINE = "OFFLINE"


class Evidence(BaseModel):
    field: str
    observed: str | int | float | bool | None
    source: str


class DiagnosticFinding(BaseModel):
    code: str
    component: str
    issue: str
    evidence: list[Evidence] = Field(min_length=1)
    severity: Severity
    confidence: Confidence
    impact: FindingImpact
    recommended_action: str
    retry_variable: str
    occurred_at: datetime | None = None


class ImagingReadiness(BaseModel):
    state: OverallState
    ready: bool
    summary: str
    blocking_issues: list[DiagnosticFinding] = Field(default_factory=list)
    warnings: list[DiagnosticFinding] = Field(default_factory=list)
    unknowns: list[DiagnosticFinding] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "nina_advanced_api"


class LatestErrorReport(BaseModel):
    state: LatestErrorState
    summary: str
    error: DiagnosticFinding | None = None
    warnings: list[DiagnosticFinding] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "nina_advanced_api"


class NextActionRecommendation(BaseModel):
    readiness_state: OverallState
    recommendation: DiagnosticFinding | None = None
    recommendation_id: str | None = None
    should_retry: bool
    repeat_warning: str | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "nina_advanced_api"
