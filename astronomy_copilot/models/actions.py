from __future__ import annotations

from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class ActionLevel(IntEnum):
    READ_ONLY = 0
    LOW_RISK_WRITE = 1
    PHYSICAL_MOTION = 2
    SESSION_ENDING = 3


class ActionStatus(StrEnum):
    PLANNED = "PLANNED"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalPlanState(StrEnum):
    PENDING = "PENDING"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"


class ApprovalPlan(BaseModel):
    plan_id: str
    action: str
    action_level: ActionLevel
    summary: str
    parameters_hash: str
    created_at: datetime
    expires_at: datetime
    state: ApprovalPlanState = ApprovalPlanState.PENDING
    single_use: bool = True


class AuditEvent(BaseModel):
    event_id: str
    action: str
    action_level: ActionLevel
    status: ActionStatus
    dry_run: bool
    parameters_hash: str
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approval_plan_id: str | None = None
    summary: str


class ActionResult(BaseModel):
    action: str
    action_level: ActionLevel
    status: ActionStatus
    dry_run: bool
    summary: str
    approval_plan: ApprovalPlan | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    audit_event_id: str
    idempotent_replay: bool = False
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "nina_advanced_api"


class AuditReport(BaseModel):
    events: list[AuditEvent]
    count: int
    source: str = "astronomy_copilot_action_policy"


ApprovalPlanId = Annotated[str | None, Field(default=None, max_length=128)]
IdempotencyKey = Annotated[str | None, Field(default=None, min_length=1, max_length=64)]
TimeoutSeconds = Annotated[float, Field(default=30.0, ge=0.05, le=600.0)]


class ControlledActionInput(BaseModel):
    dry_run: bool = True
    approved: bool = False
    approval_plan_id: ApprovalPlanId = None
    idempotency_key: IdempotencyKey = None
    timeout_seconds: TimeoutSeconds = 30.0


EquipmentComponent = Literal["camera", "mount", "guider"]


class ConnectObservatoryInput(ControlledActionInput):
    components: list[EquipmentComponent] = Field(
        default_factory=lambda: ["camera", "mount", "guider"],
        min_length=1,
        max_length=3,
    )

    @field_validator("components")
    @classmethod
    def require_unique_components(
        cls, components: list[EquipmentComponent]
    ) -> list[EquipmentComponent]:
        if len(components) != len(set(components)):
            raise ValueError("components must not contain duplicates")
        return components


class CaptureTestFrameInput(ControlledActionInput):
    exposure_seconds: float = Field(default=1.0, gt=0.0, le=30.0)
    gain: int | None = Field(default=None, ge=0, le=1000)


class PlateSolveCurrentFrameInput(ControlledActionInput):
    timeout_seconds: TimeoutSeconds = 120.0


class CenterTargetInput(ControlledActionInput):
    ra_hours: float = Field(ge=0.0, lt=24.0)
    dec_degrees: float = Field(ge=-90.0, le=90.0)
    timeout_seconds: TimeoutSeconds = 300.0


class StartGuidingInput(ControlledActionInput):
    calibrate: bool = False
    timeout_seconds: TimeoutSeconds = 120.0


class StartExistingSequenceInput(ControlledActionInput):
    timeout_seconds: TimeoutSeconds = 30.0


class StopSequenceInput(ControlledActionInput):
    timeout_seconds: TimeoutSeconds = 30.0


class ParkObservatoryInput(ControlledActionInput):
    timeout_seconds: TimeoutSeconds = 120.0
