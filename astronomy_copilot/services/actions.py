from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from astronomy_copilot.adapters.nina import (
    NinaActionTimeoutError,
    NinaResponseError,
    NinaUnavailableError,
)
from astronomy_copilot.diagnostics.common import sanitize_error_message
from astronomy_copilot.models.actions import (
    ActionLevel,
    ActionResult,
    ActionStatus,
    AuditReport,
    CaptureTestFrameInput,
    CenterTargetInput,
    ConnectObservatoryInput,
    ControlledActionInput,
    ParkObservatoryInput,
    PlateSolveCurrentFrameInput,
    StartExistingSequenceInput,
    StartGuidingInput,
    StopSequenceInput,
)
from astronomy_copilot.policy.approvals import (
    ActionRuntime,
    ApprovalRejectedError,
    action_parameters_hash,
)


class ActionAdapter(Protocol):
    async def execute(
        self,
        endpoint: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        timeout_seconds: float,
    ) -> Any: ...

    async def get_equipment_info(
        self,
        component: str,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]: ...

    async def cancel(self, action: str) -> bool: ...


OperationResult = tuple[
    ActionStatus,
    str,
    dict[str, str | int | float | bool | None],
]
Operation = Callable[[], Awaitable[OperationResult]]

CONTROL_FIELDS = {
    "dry_run",
    "approved",
    "approval_plan_id",
    "idempotency_key",
    "timeout_seconds",
}


def action_parameters(request: ControlledActionInput) -> dict[str, Any]:
    return request.model_dump(mode="json", exclude=CONTROL_FIELDS)


def safe_solve_details(response: Any) -> dict[str, str | int | float | bool | None]:
    if not isinstance(response, dict):
        return {"result": "completed"}
    allowed = ("Success", "RA", "Dec", "Rotation", "PixelScale", "Error")
    details: dict[str, str | int | float | bool | None] = {}
    for key in allowed:
        value = response.get(key)
        if key == "Error" and isinstance(value, str):
            value = sanitize_error_message(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            details[key.casefold()] = value
    return details or {"result": "completed"}


class ControlledActionService:
    def __init__(self, adapter: ActionAdapter, runtime: ActionRuntime):
        self.adapter = adapter
        self.runtime = runtime

    def get_audit(self, limit: int = 20) -> AuditReport:
        return self.runtime.audit.report(limit)

    def _result(
        self,
        *,
        action: str,
        level: ActionLevel,
        status: ActionStatus,
        dry_run: bool,
        parameters_hash: str,
        summary: str,
        approval_plan_id: str | None,
        details: dict[str, str | int | float | bool | None] | None = None,
        approval_plan=None,
        idempotent_replay: bool = False,
    ) -> ActionResult:
        event = self.runtime.audit.append(
            action=action,
            action_level=level,
            status=status,
            dry_run=dry_run,
            parameters_hash=parameters_hash,
            approval_plan_id=approval_plan_id,
            summary=summary,
        )
        return ActionResult(
            action=action,
            action_level=level,
            status=status,
            dry_run=dry_run,
            summary=summary,
            approval_plan=approval_plan,
            details=details or {},
            audit_event_id=event.event_id,
            idempotent_replay=idempotent_replay,
        )

    async def _control(
        self,
        *,
        action: str,
        level: ActionLevel,
        request: ControlledActionInput,
        plan_summary: str,
        operation: Operation,
    ) -> ActionResult:
        parameters = action_parameters(request)
        parameters_hash = action_parameters_hash(action, parameters)

        if request.dry_run:
            plan = None
            if level >= ActionLevel.PHYSICAL_MOTION:
                plan = self.runtime.approvals.create(
                    action=action,
                    action_level=level,
                    summary=plan_summary,
                    parameters_hash=parameters_hash,
                )
            return self._result(
                action=action,
                level=level,
                status=ActionStatus.PLANNED,
                dry_run=True,
                parameters_hash=parameters_hash,
                summary=f"Dry run only. {plan_summary} No NINA write request was sent.",
                approval_plan_id=plan.plan_id if plan else None,
                approval_plan=plan,
            )

        if not request.approved:
            return self._result(
                action=action,
                level=level,
                status=ActionStatus.REJECTED,
                dry_run=False,
                parameters_hash=parameters_hash,
                summary="Execution rejected: approved=true is required for every write action.",
                approval_plan_id=request.approval_plan_id,
            )

        if level >= ActionLevel.PHYSICAL_MOTION:
            try:
                self.runtime.approvals.consume(
                    request.approval_plan_id,
                    action=action,
                    parameters_hash=parameters_hash,
                )
            except ApprovalRejectedError as exc:
                return self._result(
                    action=action,
                    level=level,
                    status=ActionStatus.REJECTED,
                    dry_run=False,
                    parameters_hash=parameters_hash,
                    summary=f"Execution rejected: {exc}",
                    approval_plan_id=request.approval_plan_id,
                )
        elif request.approval_plan_id is not None:
            return self._result(
                action=action,
                level=level,
                status=ActionStatus.REJECTED,
                dry_run=False,
                parameters_hash=parameters_hash,
                summary="Execution rejected: Level 1 actions do not accept approval plan IDs.",
                approval_plan_id=request.approval_plan_id,
            )

        if level == ActionLevel.LOW_RISK_WRITE:
            try:
                replay = self.runtime.get_idempotent_result(
                    action=action,
                    key=request.idempotency_key,
                    parameters_hash=parameters_hash,
                )
            except ApprovalRejectedError as exc:
                return self._result(
                    action=action,
                    level=level,
                    status=ActionStatus.REJECTED,
                    dry_run=False,
                    parameters_hash=parameters_hash,
                    summary=f"Execution rejected: {exc}",
                    approval_plan_id=None,
                )
            if replay is not None:
                return self._result(
                    action=action,
                    level=level,
                    status=ActionStatus.SKIPPED,
                    dry_run=False,
                    parameters_hash=parameters_hash,
                    summary="No write was sent because this idempotency key already succeeded.",
                    approval_plan_id=None,
                    details=replay.details,
                    idempotent_replay=True,
                )

        try:
            async with asyncio.timeout(request.timeout_seconds):
                status, summary, details = await operation()
        except (NinaActionTimeoutError, TimeoutError):
            cancellation_requested = await self.adapter.cancel(action)
            status = ActionStatus.CANCELLED if cancellation_requested else ActionStatus.FAILED
            summary = (
                "The action timed out and a bounded cancellation request was sent."
                if cancellation_requested
                else "The action timed out; no verified cancellation endpoint was available."
            )
            details = {"cancellation_requested": cancellation_requested}
        except (NinaUnavailableError, NinaResponseError, ValueError, TypeError) as exc:
            status = ActionStatus.FAILED
            summary = f"The controlled action failed: {str(exc)[:300]}"
            details = {}

        result = self._result(
            action=action,
            level=level,
            status=status,
            dry_run=False,
            parameters_hash=parameters_hash,
            summary=summary,
            approval_plan_id=request.approval_plan_id,
            details=details,
        )
        if level == ActionLevel.LOW_RISK_WRITE and status in {
            ActionStatus.EXECUTED,
            ActionStatus.SKIPPED,
        }:
            self.runtime.store_idempotent_result(
                action=action,
                key=request.idempotency_key,
                parameters_hash=parameters_hash,
                result=result,
            )
        return result

    async def connect_observatory(self, request: ConnectObservatoryInput) -> ActionResult:
        components = list(dict.fromkeys(request.components))

        async def operation() -> OperationResult:
            outcomes: list[str] = []
            writes = 0
            for component in components:
                info = await self.adapter.get_equipment_info(
                    component,
                    timeout_seconds=request.timeout_seconds,
                )
                if info.get("Connected") is True:
                    outcomes.append(f"{component}=already_connected")
                    continue
                await self.adapter.execute(
                    f"equipment/{component}/connect",
                    timeout_seconds=request.timeout_seconds,
                )
                writes += 1
                outcomes.append(f"{component}=connected")
            status = ActionStatus.EXECUTED if writes else ActionStatus.SKIPPED
            return (
                status,
                "Configured observatory components were connected or already online.",
                {
                    "components": ",".join(outcomes),
                    "write_requests": writes,
                },
            )

        return await self._control(
            action="connect_observatory",
            level=ActionLevel.LOW_RISK_WRITE,
            request=request,
            plan_summary=f"Connect the configured {', '.join(components)} components.",
            operation=operation,
        )

    async def capture_test_frame(self, request: CaptureTestFrameInput) -> ActionResult:
        async def operation() -> OperationResult:
            params: dict[str, str | int | float | bool] = {
                "duration": request.exposure_seconds,
                "save": True,
                "omitImage": True,
                "waitForResult": True,
                "solve": False,
            }
            if request.gain is not None:
                params["gain"] = request.gain
            await self.adapter.execute(
                "equipment/camera/capture",
                params=params,
                timeout_seconds=request.timeout_seconds,
            )
            return (
                ActionStatus.EXECUTED,
                "One bounded test frame was captured.",
                {
                    "exposure_seconds": request.exposure_seconds,
                    "gain": request.gain,
                },
            )

        return await self._control(
            action="capture_test_frame",
            level=ActionLevel.LOW_RISK_WRITE,
            request=request,
            plan_summary=(
                f"Capture one {request.exposure_seconds:g}-second frame"
                + (f" at gain {request.gain}." if request.gain is not None else ".")
            ),
            operation=operation,
        )

    async def plate_solve_current_frame(self, request: PlateSolveCurrentFrameInput) -> ActionResult:
        async def operation() -> OperationResult:
            response = await self.adapter.execute(
                "prepared-image/solve",
                timeout_seconds=request.timeout_seconds,
            )
            return (
                ActionStatus.EXECUTED,
                "The current prepared frame was submitted to the configured plate solver.",
                safe_solve_details(response),
            )

        return await self._control(
            action="plate_solve_current_frame",
            level=ActionLevel.LOW_RISK_WRITE,
            request=request,
            plan_summary="Plate solve the current prepared frame without mount motion.",
            operation=operation,
        )

    async def center_target(self, request: CenterTargetInput) -> ActionResult:
        async def operation() -> OperationResult:
            await self.adapter.execute(
                "equipment/mount/slew",
                params={
                    "ra": request.ra_hours * 15.0,
                    "dec": request.dec_degrees,
                    "waitForResult": True,
                    "center": True,
                    "rotate": False,
                    "rotationAngle": 0,
                },
                timeout_seconds=request.timeout_seconds,
            )
            return (
                ActionStatus.EXECUTED,
                "NINA completed the approved center operation.",
                {
                    "ra_hours": request.ra_hours,
                    "dec_degrees": request.dec_degrees,
                },
            )

        return await self._control(
            action="center_target",
            level=ActionLevel.PHYSICAL_MOTION,
            request=request,
            plan_summary=(
                f"Slew and plate-solve center the mount at RA {request.ra_hours:g} hours, "
                f"Dec {request.dec_degrees:g} degrees."
            ),
            operation=operation,
        )

    async def start_guiding(self, request: StartGuidingInput) -> ActionResult:
        async def operation() -> OperationResult:
            await self.adapter.execute(
                "equipment/guider/start",
                params={"calibrate": request.calibrate},
                timeout_seconds=request.timeout_seconds,
            )
            return ActionStatus.EXECUTED, "Guiding was started.", {"calibrate": request.calibrate}

        return await self._control(
            action="start_guiding",
            level=(
                ActionLevel.PHYSICAL_MOTION if request.calibrate else ActionLevel.LOW_RISK_WRITE
            ),
            request=request,
            plan_summary=(
                "Start guiding with calibration."
                if request.calibrate
                else "Start guiding using the existing calibration."
            ),
            operation=operation,
        )

    async def start_existing_sequence(self, request: StartExistingSequenceInput) -> ActionResult:
        async def operation() -> OperationResult:
            await self.adapter.execute(
                "sequence/start",
                params={"skipValidation": False},
                timeout_seconds=request.timeout_seconds,
            )
            return (
                ActionStatus.EXECUTED,
                "The existing validated NINA sequence was started.",
                {"validation_skipped": False},
            )

        return await self._control(
            action="start_existing_sequence",
            level=ActionLevel.PHYSICAL_MOTION,
            request=request,
            plan_summary=(
                "Start the existing NINA sequence with validation enabled; the loaded sequence "
                "may contain physical-motion instructions."
            ),
            operation=operation,
        )

    async def stop_sequence_safely(self, request: StopSequenceInput) -> ActionResult:
        async def operation() -> OperationResult:
            await self.adapter.execute(
                "sequence/stop",
                timeout_seconds=request.timeout_seconds,
            )
            return ActionStatus.EXECUTED, "The approved sequence stop was sent.", {}

        return await self._control(
            action="stop_sequence_safely",
            level=ActionLevel.SESSION_ENDING,
            request=request,
            plan_summary="Stop the currently running NINA sequence.",
            operation=operation,
        )

    async def park_observatory(self, request: ParkObservatoryInput) -> ActionResult:
        async def operation() -> OperationResult:
            info = await self.adapter.get_equipment_info(
                "mount",
                timeout_seconds=request.timeout_seconds,
            )
            if info.get("AtPark") is True:
                return (
                    ActionStatus.SKIPPED,
                    "The mount was already parked; no write was sent.",
                    {"already_parked": True},
                )
            await self.adapter.execute(
                "equipment/mount/park",
                timeout_seconds=request.timeout_seconds,
            )
            return (
                ActionStatus.EXECUTED,
                "The approved mount park command was sent.",
                {"already_parked": False},
            )

        return await self._control(
            action="park_observatory",
            level=ActionLevel.SESSION_ENDING,
            request=request,
            plan_summary="Park the connected mount at its configured park position.",
            operation=operation,
        )
