from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol

from astronomy_copilot.adapters.nina import NinaResponseError, NinaUnavailableError
from astronomy_copilot.models.actions import (
    ActionResult,
    ActionStatus,
    CaptureTestFrameInput,
    CenterTargetInput,
    ConnectObservatoryInput,
    PlateSolveCurrentFrameInput,
    StartGuidingInput,
)
from astronomy_copilot.models.diagnostics import ImagingReadiness
from astronomy_copilot.models.image_analysis import (
    AnalysisState,
    FitsAnalysisInput,
    FitsAnalysisReport,
    IndicatorState,
)
from astronomy_copilot.models.session import SessionState, SessionTimeline
from astronomy_copilot.models.workflow import (
    PrepareForImagingInput,
    PrepareForImagingReport,
    WorkflowStatus,
    WorkflowStepState,
)
from astronomy_copilot.policy.workflow_plans import (
    WorkflowRecord,
    WorkflowRejectedError,
    WorkflowRuntime,
)
from astronomy_copilot.services.readiness import readiness_from_findings
from astronomy_copilot.services.session import facts_from_snapshot, state_from_facts

OPERATOR_SAFETY_ATTESTATION_MAX_AGE_SECONDS = 300.0
OPERATOR_SAFETY_ATTESTATION_FUTURE_TOLERANCE_SECONDS = 5.0
CLOUDY_WEATHER_RETRY_INTERVAL_SECONDS = 300.0


class WorkflowAdapter(Protocol):
    async def get_session_snapshot(self) -> dict[str, Any]: ...


class WorkflowActionService(Protocol):
    async def connect_observatory(self, request: ConnectObservatoryInput) -> ActionResult: ...

    async def capture_test_frame(self, request: CaptureTestFrameInput) -> ActionResult: ...

    async def plate_solve_current_frame(
        self, request: PlateSolveCurrentFrameInput
    ) -> ActionResult: ...

    async def center_target(self, request: CenterTargetInput) -> ActionResult: ...

    async def start_guiding(self, request: StartGuidingInput) -> ActionResult: ...


class WorkflowSessionService(Protocol):
    async def reconcile(self) -> SessionState: ...

    def current_timeline(self, cursor: int = 0, limit: int = 100) -> SessionTimeline: ...


class WorkflowReadinessService(Protocol):
    async def get_readiness(self) -> ImagingReadiness: ...


class WorkflowImageAnalysisService(Protocol):
    def analyze(self, request: FitsAnalysisInput) -> FitsAnalysisReport: ...


def _casefold_value(mapping: Any, name: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key, value in mapping.items():
        if str(key).casefold() == name.casefold():
            return value
    return None


def _parse_observed_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        observed = value
    elif isinstance(value, str):
        try:
            observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc)


def scoped_readiness(
    readiness: ImagingReadiness,
    *,
    require_guiding: bool,
    allow_not_guiding: bool,
) -> ImagingReadiness:
    findings = [
        *readiness.blocking_issues,
        *readiness.warnings,
        *readiness.unknowns,
    ]
    filtered = []
    for finding in findings:
        if finding.component == "guider" and not require_guiding:
            continue
        if allow_not_guiding and finding.code == "guider.not_guiding":
            continue
        filtered.append(finding)
    return readiness_from_findings(filtered)


class PrepareForImagingService:
    def __init__(
        self,
        adapter: WorkflowAdapter,
        actions: WorkflowActionService,
        session: WorkflowSessionService,
        readiness: WorkflowReadinessService,
        image_analysis: WorkflowImageAnalysisService,
        runtime: WorkflowRuntime,
        guiding_poll_interval_seconds: float = 1.0,
        cloudy_retry_interval_seconds: float = CLOUDY_WEATHER_RETRY_INTERVAL_SECONDS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.adapter = adapter
        self.actions = actions
        self.session = session
        self.readiness = readiness
        self.image_analysis = image_analysis
        self.runtime = runtime
        self.guiding_poll_interval_seconds = guiding_poll_interval_seconds
        self.cloudy_retry_interval_seconds = cloudy_retry_interval_seconds
        self.sleep = sleep
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _report(
        self,
        record: WorkflowRecord,
        summary: str,
        *,
        dry_run: bool,
        warnings: list[str] | None = None,
    ) -> PrepareForImagingReport:
        return PrepareForImagingReport(
            workflow_id=record.plan.workflow_id,
            status=record.status,
            summary=summary,
            dry_run=dry_run,
            proposed_plan=record.plan.model_copy(deep=True),
            steps=[step.model_copy(deep=True) for step in record.steps],
            action_results=[result.model_copy(deep=True) for result in record.action_results],
            image_analyses=[report.model_copy(deep=True) for report in record.image_analyses],
            final_image_analysis=(
                record.final_image_analysis.model_copy(deep=True)
                if record.final_image_analysis is not None
                else None
            ),
            required_approval=(
                record.required_approval.model_copy(deep=True)
                if record.required_approval is not None
                else None
            ),
            plate_solve_attempts=record.plate_solve_attempts,
            changed_variables=list(record.changed_variables),
            final_readiness=(
                record.final_readiness.model_copy(deep=True)
                if record.final_readiness is not None
                else None
            ),
            session_timeline=(
                record.session_timeline.model_copy(deep=True)
                if record.session_timeline is not None
                else None
            ),
            timeline=[event.model_copy(deep=True) for event in record.events],
            warnings=[*record.warnings, *(warnings or [])],
        )

    def _rejected(self, summary: str) -> PrepareForImagingReport:
        return PrepareForImagingReport(
            status=WorkflowStatus.REJECTED,
            summary=summary,
            dry_run=False,
        )

    async def _safety_check(
        self,
        request: PrepareForImagingInput,
    ) -> tuple[bool, str]:
        snapshot = await self.adapter.get_session_snapshot()
        if not isinstance(snapshot, dict):
            return False, "Safety telemetry is malformed."
        observed_at = _parse_observed_at(snapshot.get("observed_at"))
        if observed_at is None:
            return False, "Safety telemetry has no valid observation timestamp."
        age = (self.clock() - observed_at).total_seconds()
        if age < -5.0 or age > request.max_telemetry_age_seconds:
            return False, f"Safety telemetry is stale or future-dated (age {age:.1f} seconds)."

        facts, contradictions, hint = facts_from_snapshot(snapshot)
        if contradictions:
            return False, f"Telemetry is contradictory: {'; '.join(contradictions)}."
        state = state_from_facts(facts, hint=hint)
        if state not in {
            SessionState.STARTING,
            SessionState.CONNECTED,
            SessionState.GUIDING,
            SessionState.SAFE,
        }:
            return False, f"Session state {state} is not valid for workflow continuation."

        equipment = snapshot.get("equipment")
        safety_monitor = equipment.get("safety_monitor") if isinstance(equipment, dict) else None
        connected = _casefold_value(safety_monitor, "Connected")
        safe = _casefold_value(safety_monitor, "IsSafe")
        if connected is True:
            if safe is not True:
                return False, (
                    "The connected safety monitor does not positively report IsSafe=true; "
                    "operator attestation cannot override it."
                )
            return True, f"Fresh authoritative telemetry permits continuation from state {state}."

        configuration = snapshot.get("configuration")
        safety_configuration = (
            configuration.get("safety_monitor") if isinstance(configuration, dict) else None
        )
        configured = _casefold_value(safety_configuration, "Configured")
        if configured is not False:
            return False, (
                "A configured safety monitor is disconnected or its configuration is unknown; "
                "operator attestation is not permitted."
            )
        if connected is not False:
            return False, "Safety-monitor connection telemetry is missing or malformed."
        if request.operator_safety_attestation != "OPERATOR_CONFIRMS_SAFE":
            return False, (
                "No safety monitor is configured; a current explicit operator safety "
                "attestation is required."
            )
        attested_at = _parse_observed_at(request.operator_safety_attested_at)
        if attested_at is None:
            return False, "The operator safety attestation has no valid timestamp."
        attestation_age = (self.clock() - attested_at).total_seconds()
        if (
            attestation_age < -OPERATOR_SAFETY_ATTESTATION_FUTURE_TOLERANCE_SECONDS
            or attestation_age > OPERATOR_SAFETY_ATTESTATION_MAX_AGE_SECONDS
        ):
            return False, (
                "The operator safety attestation is expired or future-dated "
                f"(age {attestation_age:.1f} seconds); stop and provide a fresh attestation."
            )
        return True, (
            "No safety monitor is configured; a fresh, time-bounded operator safety "
            f"attestation permits continuation from state {state}."
        )

    async def _known_state(self, record: WorkflowRecord) -> None:
        await self.session.reconcile()
        record.session_timeline = self.session.current_timeline(limit=100)
        if record.final_readiness is None:
            record.final_readiness = await self.readiness.get_readiness()

    async def _fail(
        self,
        record: WorkflowRecord,
        step_id: str,
        summary: str,
    ) -> PrepareForImagingReport:
        record.status = WorkflowStatus.FAILED
        self.runtime.event(record, step_id, WorkflowStepState.FAILED, summary)
        await self._known_state(record)
        return self._report(record, summary, dry_run=False)

    def _store_action(self, record: WorkflowRecord, result: ActionResult) -> bool:
        record.action_results.append(result.model_copy(deep=True))
        return result.status in {ActionStatus.EXECUTED, ActionStatus.SKIPPED}

    async def _wait_for_guiding(
        self,
        request: PrepareForImagingInput,
    ) -> tuple[bool, ImagingReadiness]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + request.guiding_settle_timeout_seconds
        while True:
            readiness = scoped_readiness(
                await self.readiness.get_readiness(),
                require_guiding=True,
                allow_not_guiding=False,
            )
            if readiness.ready:
                return True, readiness
            findings = [
                *readiness.blocking_issues,
                *readiness.warnings,
                *readiness.unknowns,
            ]
            retryable = bool(findings) and all(
                finding.code in {"guider.not_guiding", "guider.transitional_state"}
                for finding in findings
            )
            if not retryable or loop.time() >= deadline:
                return False, readiness
            await asyncio.sleep(
                min(self.guiding_poll_interval_seconds, max(0.0, deadline - loop.time()))
            )

    async def _analyze_local_frame(
        self,
        record: WorkflowRecord,
        request: PrepareForImagingInput,
        step_id: str,
    ) -> FitsAnalysisReport | None:
        if request.image_file_path is None:
            warning = (
                "No image_file_path was supplied; pixel-quality evidence was not included in "
                "workflow readiness."
            )
            if warning not in record.warnings:
                record.warnings.append(warning)
            self.runtime.event(record, step_id, WorkflowStepState.SKIPPED, warning)
            return None
        self.runtime.event(
            record,
            step_id,
            WorkflowStepState.RUNNING,
            "Analyzing the supplied NINA-managed local FITS frame read-only.",
        )
        report = await asyncio.to_thread(
            self.image_analysis.analyze,
            FitsAnalysisInput(file_path=request.image_file_path),
        )
        record.image_analyses.append(report.model_copy(deep=True))
        if report.state == AnalysisState.UNAVAILABLE:
            self.runtime.event(record, step_id, WorkflowStepState.FAILED, report.summary)
            return report
        self.runtime.event(record, step_id, WorkflowStepState.COMPLETED, report.summary)
        return report

    @staticmethod
    def _blocking_image_indicators(report: FitsAnalysisReport) -> list[str]:
        blocking_codes = {
            "saturation",
            "clipping",
            "too_few_stars",
            "severe_defocus",
            "likely_trailing",
            "severe_background_gradient",
            "low_usable_signal",
        }
        return [
            indicator.code
            for indicator in report.indicators
            if indicator.code in blocking_codes and indicator.state == IndicatorState.DETECTED
        ]

    async def _preflight(
        self,
        record: WorkflowRecord,
        request: PrepareForImagingInput,
        *,
        check_readiness: bool,
    ) -> PrepareForImagingReport | None:
        self.runtime.event(
            record,
            "preflight",
            WorkflowStepState.RUNNING,
            "Refreshing safety, state, and contradiction evidence.",
        )
        try:
            safe, summary = await self._safety_check(request)
        except (
            NinaUnavailableError,
            NinaResponseError,
            TimeoutError,
            ValueError,
            TypeError,
        ) as exc:
            return await self._fail(record, "preflight", f"Preflight telemetry failed: {exc}")
        if not safe:
            return await self._fail(record, "preflight", summary)
        if check_readiness:
            readiness = scoped_readiness(
                await self.readiness.get_readiness(),
                require_guiding=request.require_guiding,
                allow_not_guiding=(request.require_guiding and not request.cloudy_weather_retry),
            )
            if not readiness.ready:
                record.final_readiness = readiness
                return await self._fail(record, "preflight", readiness.summary)
        self.runtime.event(record, "preflight", WorkflowStepState.COMPLETED, summary)
        return None

    async def _run_initial_steps(
        self,
        record: WorkflowRecord,
        request: PrepareForImagingInput,
    ) -> PrepareForImagingReport:
        record.status = WorkflowStatus.RUNNING
        failure = await self._preflight(record, request, check_readiness=False)
        if failure is not None:
            return failure

        self.runtime.event(
            record,
            "connect",
            WorkflowStepState.RUNNING,
            "Connecting only the required configured components.",
        )
        components = ["camera", "mount", *(["guider"] if request.require_guiding else [])]
        connected = await self.actions.connect_observatory(
            ConnectObservatoryInput(
                components=components,
                dry_run=False,
                approved=True,
                idempotency_key=f"{record.plan.workflow_id}:connect",
                timeout_seconds=request.timeout_seconds,
            )
        )
        if not self._store_action(record, connected):
            return await self._fail(record, "connect", connected.summary)
        self.runtime.event(record, "connect", WorkflowStepState.COMPLETED, connected.summary)

        failure = await self._preflight(record, request, check_readiness=True)
        if failure is not None:
            return failure

        solve_exposure = request.test_exposure_seconds
        solved = False
        for attempt in range(1, request.max_plate_solve_attempts + 1):
            record.plate_solve_attempts = attempt
            self.runtime.event(
                record,
                "solve_frame",
                WorkflowStepState.RUNNING,
                f"Capturing solve frame attempt {attempt} at {solve_exposure:g} seconds.",
            )
            captured = await self.actions.capture_test_frame(
                CaptureTestFrameInput(
                    exposure_seconds=solve_exposure,
                    gain=request.gain,
                    dry_run=False,
                    approved=True,
                    idempotency_key=f"{record.plan.workflow_id}:solve-frame:{attempt}",
                    timeout_seconds=request.timeout_seconds,
                )
            )
            if not self._store_action(record, captured):
                return await self._fail(record, "solve_frame", captured.summary)
            self.runtime.event(record, "solve_frame", WorkflowStepState.COMPLETED, captured.summary)

            quality = await self._analyze_local_frame(record, request, "solve_quality")
            if quality is not None and quality.state == AnalysisState.UNAVAILABLE:
                return await self._fail(record, "solve_quality", quality.summary)

            self.runtime.event(
                record,
                "plate_solve",
                WorkflowStepState.RUNNING,
                f"Running plate-solve attempt {attempt} of {request.max_plate_solve_attempts}.",
            )
            solve = await self.actions.plate_solve_current_frame(
                PlateSolveCurrentFrameInput(
                    dry_run=False,
                    approved=True,
                    idempotency_key=f"{record.plan.workflow_id}:plate-solve:{attempt}",
                    timeout_seconds=request.timeout_seconds,
                )
            )
            record.action_results.append(solve.model_copy(deep=True))
            if solve.status in {ActionStatus.EXECUTED, ActionStatus.SKIPPED}:
                solved = True
                self.runtime.event(
                    record, "plate_solve", WorkflowStepState.COMPLETED, solve.summary
                )
                break
            if attempt >= request.max_plate_solve_attempts:
                break
            if request.cloudy_weather_retry:
                self.runtime.event(
                    record,
                    "plate_solve",
                    WorkflowStepState.RUNNING,
                    "Plate solve failed; waiting five minutes before the bounded retry.",
                )
                await self.sleep(self.cloudy_retry_interval_seconds)
                failure = await self._preflight(record, request, check_readiness=True)
                if failure is not None:
                    return failure
                continue
            saturation_detected = (
                quality is not None and "saturation" in self._blocking_image_indicators(quality)
            )
            if saturation_detected:
                next_exposure = max(0.1, solve_exposure / 2.0)
            else:
                next_exposure = min(30.0, max(solve_exposure + 1.0, solve_exposure * 2.0))
            if next_exposure == solve_exposure:
                break
            change = f"solve_exposure_seconds {solve_exposure:g} -> {next_exposure:g}"
            record.changed_variables.append(change)
            self.runtime.event(
                record,
                "plate_solve",
                WorkflowStepState.RUNNING,
                "Plate solve failed; changing only solve exposure before the bounded retry.",
                changed_variable=change,
            )
            solve_exposure = next_exposure
        if not solved:
            return await self._fail(
                record,
                "plate_solve",
                f"Plate solving failed after {record.plate_solve_attempts} bounded attempt(s).",
            )

        center_plan = await self.actions.center_target(
            CenterTargetInput(
                ra_hours=request.ra_hours,
                dec_degrees=request.dec_degrees,
                timeout_seconds=request.timeout_seconds,
            )
        )
        record.action_results.append(center_plan.model_copy(deep=True))
        if center_plan.status != ActionStatus.PLANNED or center_plan.approval_plan is None:
            return await self._fail(record, "center", "A centering approval plan was not created.")
        record.required_approval = center_plan.approval_plan.model_copy(deep=True)
        record.status = WorkflowStatus.AWAITING_APPROVAL
        self.runtime.event(
            record,
            "center",
            WorkflowStepState.AWAITING_APPROVAL,
            "Paused before Level 2 mount motion; supply the exact centering approval plan ID.",
        )
        return self._report(
            record,
            "Level 1 preparation completed and the workflow paused before centering.",
            dry_run=False,
        )

    async def _resume_after_center_approval(
        self,
        record: WorkflowRecord,
        request: PrepareForImagingInput,
    ) -> PrepareForImagingReport:
        required = record.required_approval
        if required is None or request.center_approval_plan_id != required.plan_id:
            return self._report(
                record,
                "The workflow remains paused before Level 2 centering.",
                dry_run=False,
                warnings=["The exact required center_approval_plan_id was not supplied."],
            )
        failure = await self._preflight(record, request, check_readiness=True)
        if failure is not None:
            return failure
        record.status = WorkflowStatus.RUNNING
        self.runtime.event(
            record,
            "center",
            WorkflowStepState.RUNNING,
            "Executing the explicitly approved Level 2 centering plan.",
        )
        centered = await self.actions.center_target(
            CenterTargetInput(
                ra_hours=request.ra_hours,
                dec_degrees=request.dec_degrees,
                dry_run=False,
                approved=True,
                approval_plan_id=request.center_approval_plan_id,
                timeout_seconds=request.timeout_seconds,
            )
        )
        if not self._store_action(record, centered):
            return await self._fail(record, "center", centered.summary)
        record.required_approval = None
        self.runtime.event(record, "center", WorkflowStepState.COMPLETED, centered.summary)

        if request.require_guiding:
            self.runtime.event(
                record,
                "guiding",
                WorkflowStepState.RUNNING,
                "Starting guiding after centering.",
            )
            guiding = await self.actions.start_guiding(
                StartGuidingInput(
                    calibrate=False,
                    dry_run=False,
                    approved=True,
                    idempotency_key=f"{record.plan.workflow_id}:guiding",
                    timeout_seconds=request.timeout_seconds,
                )
            )
            if not self._store_action(record, guiding):
                return await self._fail(record, "guiding", guiding.summary)
            settled, guiding_readiness = await self._wait_for_guiding(request)
            if not settled:
                record.final_readiness = guiding_readiness
                return await self._fail(
                    record,
                    "guiding",
                    "Guiding did not reach a ready state within the bounded settle window.",
                )
            self.runtime.event(record, "guiding", WorkflowStepState.COMPLETED, guiding.summary)

        self.runtime.event(
            record,
            "final_frame",
            WorkflowStepState.RUNNING,
            "Capturing the final bounded test frame.",
        )
        final_frame = await self.actions.capture_test_frame(
            CaptureTestFrameInput(
                exposure_seconds=request.test_exposure_seconds,
                gain=request.gain,
                dry_run=False,
                approved=True,
                idempotency_key=f"{record.plan.workflow_id}:final-frame",
                timeout_seconds=request.timeout_seconds,
            )
        )
        if not self._store_action(record, final_frame):
            return await self._fail(record, "final_frame", final_frame.summary)
        self.runtime.event(record, "final_frame", WorkflowStepState.COMPLETED, final_frame.summary)

        final_quality = await self._analyze_local_frame(record, request, "final_quality")
        record.final_image_analysis = (
            final_quality.model_copy(deep=True) if final_quality is not None else None
        )
        if final_quality is not None:
            if final_quality.state == AnalysisState.UNAVAILABLE:
                return await self._fail(record, "final_quality", final_quality.summary)
            blocking_quality = self._blocking_image_indicators(final_quality)
            if blocking_quality:
                return await self._fail(
                    record,
                    "final_quality",
                    "Final image quality is blocked by: " + ", ".join(blocking_quality) + ".",
                )

        failure = await self._preflight(record, request, check_readiness=False)
        if failure is not None:
            return failure
        final_readiness = scoped_readiness(
            await self.readiness.get_readiness(),
            require_guiding=request.require_guiding,
            allow_not_guiding=False,
        )
        record.final_readiness = final_readiness
        await self.session.reconcile()
        record.session_timeline = self.session.current_timeline(limit=100)
        if not final_readiness.ready:
            return await self._fail(record, "final_readiness", final_readiness.summary)
        record.status = WorkflowStatus.COMPLETED
        self.runtime.event(
            record,
            "final_readiness",
            WorkflowStepState.COMPLETED,
            final_readiness.summary,
        )
        return self._report(
            record,
            "Supervised preparation completed with final ready telemetry.",
            dry_run=False,
        )

    async def prepare(self, request: PrepareForImagingInput) -> PrepareForImagingReport:
        if request.dry_run:
            record = self.runtime.create(request)
            return self._report(
                record,
                "Proposed supervised imaging plan. No NINA write request was sent.",
                dry_run=True,
            )
        if not request.approved:
            return self._rejected("Execution rejected: approved=true is required.")
        try:
            with self.runtime.claim(request.workflow_id, request) as record:
                if record.status == WorkflowStatus.COMPLETED:
                    return self._report(
                        record,
                        "The workflow already completed; no action was repeated.",
                        dry_run=False,
                    )
                if record.status == WorkflowStatus.FAILED:
                    return self._report(
                        record,
                        "The failed workflow cannot silently resume.",
                        dry_run=False,
                    )
                if record.status == WorkflowStatus.AWAITING_APPROVAL:
                    return await self._resume_after_center_approval(record, request)
                if request.center_approval_plan_id is not None:
                    return self._rejected(
                        "A center approval cannot be supplied before the workflow reaches that boundary."
                    )
                return await self._run_initial_steps(record, request)
        except WorkflowRejectedError as exc:
            return self._rejected(f"Execution rejected: {exc}")
