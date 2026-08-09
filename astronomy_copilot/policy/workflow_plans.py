from __future__ import annotations

import hashlib
import json
import secrets
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Iterator

from astronomy_copilot.models.actions import ActionLevel, ActionResult, ApprovalPlan
from astronomy_copilot.models.diagnostics import ImagingReadiness
from astronomy_copilot.models.image_analysis import FitsAnalysisReport
from astronomy_copilot.models.session import SessionTimeline
from astronomy_copilot.models.workflow import (
    PrepareForImagingInput,
    WorkflowPlan,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStepState,
    WorkflowTimelineEvent,
)


class WorkflowRejectedError(RuntimeError):
    """A workflow request did not match a live, immutable proposal."""


WORKFLOW_CONTROL_FIELDS = {
    "dry_run",
    "approved",
    "workflow_id",
    "center_approval_plan_id",
    "operator_safety_attestation",
    "operator_safety_attested_at",
}


def workflow_parameters_hash(request: PrepareForImagingInput) -> str:
    parameters = request.model_dump(mode="json", exclude=WORKFLOW_CONTROL_FIELDS)
    encoded = json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def planned_steps(require_guiding: bool) -> list[WorkflowStep]:
    steps = [
        WorkflowStep(
            step_id="preflight",
            title="Validate fresh safety and session telemetry",
            action_level=ActionLevel.READ_ONLY,
            summary=(
                "Require a safe connected monitor, or a fresh operator attestation only when "
                "the active profile proves that no monitor is configured."
            ),
        ),
        WorkflowStep(
            step_id="connect",
            title="Connect required configured equipment",
            action_level=ActionLevel.LOW_RISK_WRITE,
            summary="Connect camera, mount, and the guider when guiding is requested.",
        ),
        WorkflowStep(
            step_id="solve_frame",
            title="Capture a bounded plate-solve frame",
            action_level=ActionLevel.LOW_RISK_WRITE,
            summary="Capture one bounded frame using the current solve-exposure variable.",
        ),
        WorkflowStep(
            step_id="solve_quality",
            title="Evaluate local solve-frame quality evidence",
            action_level=ActionLevel.READ_ONLY,
            summary="Use Phase 6 evidence when a NINA-managed local frame path is supplied.",
        ),
        WorkflowStep(
            step_id="plate_solve",
            title="Plate solve with bounded recovery",
            action_level=ActionLevel.LOW_RISK_WRITE,
            summary="Retry only with one changed variable and a hard attempt limit.",
        ),
        WorkflowStep(
            step_id="center",
            title="Center the approved target",
            action_level=ActionLevel.PHYSICAL_MOTION,
            summary="Pause and require the exact short-lived centering action plan.",
        ),
    ]
    if require_guiding:
        steps.append(
            WorkflowStep(
                step_id="guiding",
                title="Start guiding",
                action_level=ActionLevel.LOW_RISK_WRITE,
                summary="Start guiding only after the approved center completes.",
            )
        )
    steps.extend(
        [
            WorkflowStep(
                step_id="final_frame",
                title="Capture a final bounded test frame",
                action_level=ActionLevel.LOW_RISK_WRITE,
                summary="Capture one final frame after centering and optional guiding.",
            ),
            WorkflowStep(
                step_id="final_quality",
                title="Evaluate final local image quality",
                action_level=ActionLevel.READ_ONLY,
                summary="Stop on supplied, reviewed blocking image-quality evidence.",
            ),
            WorkflowStep(
                step_id="final_readiness",
                title="Return final readiness and timelines",
                action_level=ActionLevel.READ_ONLY,
                summary="Require fresh ready telemetry and report the final known state.",
            ),
        ]
    )
    return steps


@dataclass(slots=True)
class WorkflowRecord:
    plan: WorkflowPlan
    status: WorkflowStatus = WorkflowStatus.PROPOSED
    steps: list[WorkflowStep] = field(default_factory=list)
    events: deque[WorkflowTimelineEvent] = field(default_factory=lambda: deque(maxlen=200))
    action_results: list[ActionResult] = field(default_factory=list)
    image_analyses: list[FitsAnalysisReport] = field(default_factory=list)
    final_image_analysis: FitsAnalysisReport | None = None
    required_approval: ApprovalPlan | None = None
    plate_solve_attempts: int = 0
    changed_variables: list[str] = field(default_factory=list)
    final_readiness: ImagingReadiness | None = None
    session_timeline: SessionTimeline | None = None
    warnings: list[str] = field(default_factory=list)
    busy: bool = False


class WorkflowRuntime:
    def __init__(
        self,
        *,
        ttl_seconds: int = 600,
        max_records: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_records = max_records
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._records: dict[str, WorkflowRecord] = {}
        self._lock = RLock()

    def create(self, request: PrepareForImagingInput) -> WorkflowRecord:
        now = self._clock()
        workflow_id = secrets.token_urlsafe(18)
        steps = planned_steps(request.require_guiding)
        plan = WorkflowPlan(
            workflow_id=workflow_id,
            target_name=request.target_name,
            parameters_hash=workflow_parameters_hash(request),
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            steps=[step.model_copy(deep=True) for step in steps],
        )
        record = WorkflowRecord(plan=plan, steps=steps)
        self._append_event(
            record,
            "preflight",
            WorkflowStepState.PLANNED,
            "Workflow proposed; no equipment-changing request was sent.",
        )
        with self._lock:
            if len(self._records) >= self.max_records:
                evictable = next(
                    (key for key, item in self._records.items() if not item.busy),
                    None,
                )
                if evictable is not None:
                    self._records.pop(evictable)
            self._records[workflow_id] = record
        return record

    def _append_event(
        self,
        record: WorkflowRecord,
        step_id: str,
        state: WorkflowStepState,
        summary: str,
        changed_variable: str | None = None,
    ) -> None:
        record.events.append(
            WorkflowTimelineEvent(
                event_id=secrets.token_hex(12),
                step_id=step_id,
                state=state,
                summary=summary[:500],
                changed_variable=changed_variable,
            )
        )

    def event(
        self,
        record: WorkflowRecord,
        step_id: str,
        state: WorkflowStepState,
        summary: str,
        *,
        changed_variable: str | None = None,
    ) -> None:
        step = next((item for item in record.steps if item.step_id == step_id), None)
        if step is not None:
            step.state = state
            step.summary = summary[:500]
            if state == WorkflowStepState.RUNNING:
                step.attempts += 1
        self._append_event(record, step_id, state, summary, changed_variable)

    @contextmanager
    def claim(
        self,
        workflow_id: str | None,
        request: PrepareForImagingInput,
    ) -> Iterator[WorkflowRecord]:
        if not workflow_id:
            raise WorkflowRejectedError("A workflow_id from a dry-run proposal is required.")
        with self._lock:
            record = self._records.get(workflow_id)
            if record is None:
                raise WorkflowRejectedError("The workflow proposal does not exist.")
            if self._clock() >= record.plan.expires_at:
                raise WorkflowRejectedError("The workflow proposal has expired.")
            if not secrets.compare_digest(
                record.plan.parameters_hash,
                workflow_parameters_hash(request),
            ):
                raise WorkflowRejectedError("The workflow parameters differ from the proposal.")
            if record.busy:
                raise WorkflowRejectedError("The workflow is already running.")
            record.busy = True
        try:
            yield record
        finally:
            with self._lock:
                record.busy = False

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
