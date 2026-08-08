from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field

from astronomy_copilot.models.actions import ActionLevel, ActionResult, ApprovalPlan
from astronomy_copilot.models.diagnostics import ImagingReadiness
from astronomy_copilot.models.image_analysis import FitsAnalysisReport
from astronomy_copilot.models.session import SessionTimeline


class WorkflowStatus(StrEnum):
    PROPOSED = "PROPOSED"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class WorkflowStepState(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    FAILED = "FAILED"


class PrepareForImagingInput(BaseModel):
    target_name: str = Field(min_length=1, max_length=128)
    ra_hours: float = Field(ge=0.0, lt=24.0)
    dec_degrees: float = Field(ge=-90.0, le=90.0)
    test_exposure_seconds: float = Field(default=3.0, gt=0.0, le=30.0)
    gain: int | None = Field(default=None, ge=0, le=1000)
    image_file_path: str | None = Field(default=None, min_length=1, max_length=4096)
    require_guiding: bool = True
    max_plate_solve_attempts: int = Field(default=2, ge=1, le=3)
    guiding_settle_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    max_telemetry_age_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    dry_run: bool = True
    approved: bool = False
    workflow_id: str | None = Field(default=None, max_length=64)
    center_approval_plan_id: str | None = Field(default=None, max_length=128)


class WorkflowStep(BaseModel):
    step_id: str
    title: str
    action_level: ActionLevel
    state: WorkflowStepState = WorkflowStepState.PLANNED
    summary: str
    attempts: int = 0


class WorkflowPlan(BaseModel):
    workflow_id: str
    target_name: str
    parameters_hash: str
    created_at: datetime
    expires_at: datetime
    steps: list[WorkflowStep]
    single_target: bool = True


class WorkflowTimelineEvent(BaseModel):
    event_id: str
    step_id: str
    state: WorkflowStepState
    summary: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    changed_variable: str | None = None


class PrepareForImagingReport(BaseModel):
    workflow_id: str | None = None
    status: WorkflowStatus
    summary: str
    dry_run: bool
    proposed_plan: WorkflowPlan | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    action_results: list[ActionResult] = Field(default_factory=list)
    image_analyses: list[FitsAnalysisReport] = Field(default_factory=list)
    final_image_analysis: FitsAnalysisReport | None = None
    required_approval: ApprovalPlan | None = None
    plate_solve_attempts: int = 0
    changed_variables: list[str] = Field(default_factory=list)
    final_readiness: ImagingReadiness | None = None
    session_timeline: SessionTimeline | None = None
    timeline: list[WorkflowTimelineEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "astronomy_copilot_supervised_workflow"
