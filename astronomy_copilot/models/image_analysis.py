from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class AnalysisState(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class EvidenceState(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class IndicatorState(StrEnum):
    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    UNAVAILABLE = "UNAVAILABLE"


class FitsAnalysisInput(BaseModel):
    file_path: str = Field(min_length=1, max_length=4096)
    hdu_index: int | None = Field(default=None, ge=0, le=99)
    saturation_fraction: float = Field(default=0.98, ge=0.5, le=1.0)
    star_detection_sigma: float = Field(default=5.0, ge=3.0, le=20.0)


class ImageMeasurement(BaseModel):
    state: EvidenceState
    value: str | int | float | bool | None = None
    unit: str
    method: str
    threshold: str | None = None
    limitations: list[str] = Field(default_factory=list)


class ImageQualityIndicator(BaseModel):
    code: str
    state: IndicatorState
    summary: str
    method: str
    threshold: str
    evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class FitsAnalysisReport(BaseModel):
    state: AnalysisState
    summary: str
    file_name: str | None = None
    hdu_index: int | None = None
    metadata: dict[str, ImageMeasurement] = Field(default_factory=dict)
    measurements: dict[str, ImageMeasurement] = Field(default_factory=dict)
    indicators: list[ImageQualityIndicator] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "local_fits_read_only"
