from __future__ import annotations

import hashlib
import json
import secrets
from collections import deque
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Callable

from astronomy_copilot.models.actions import (
    ActionLevel,
    ActionResult,
    ActionStatus,
    ApprovalPlan,
    ApprovalPlanState,
    AuditEvent,
    AuditReport,
)


class ApprovalRejectedError(RuntimeError):
    """A controlled action did not satisfy server-side approval policy."""


def action_parameters_hash(action: str, parameters: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"action": action, "parameters": parameters},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ApprovalPlanStore:
    def __init__(
        self,
        *,
        ttl_seconds: int = 120,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._plans: dict[str, ApprovalPlan] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        action: str,
        action_level: ActionLevel,
        summary: str,
        parameters_hash: str,
    ) -> ApprovalPlan:
        now = self._clock()
        plan = ApprovalPlan(
            plan_id=secrets.token_urlsafe(18),
            action=action,
            action_level=action_level,
            summary=summary,
            parameters_hash=parameters_hash,
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            self._plans[plan.plan_id] = plan
        return plan.model_copy(deep=True)

    def consume(
        self,
        plan_id: str | None,
        *,
        action: str,
        parameters_hash: str,
    ) -> ApprovalPlan:
        if not plan_id:
            raise ApprovalRejectedError("A valid approval_plan_id is required for this action.")

        with self._lock:
            plan = self._plans.get(plan_id)
            if plan is None:
                raise ApprovalRejectedError("The approval plan does not exist.")
            if plan.state == ApprovalPlanState.CONSUMED:
                raise ApprovalRejectedError("The approval plan has already been used.")
            if plan.state == ApprovalPlanState.EXPIRED or self._clock() >= plan.expires_at:
                plan.state = ApprovalPlanState.EXPIRED
                raise ApprovalRejectedError("The approval plan has expired.")
            if plan.action != action:
                raise ApprovalRejectedError("The approval plan is for a different action.")
            if not secrets.compare_digest(plan.parameters_hash, parameters_hash):
                raise ApprovalRejectedError("The action parameters differ from the approved plan.")

            plan.state = ApprovalPlanState.CONSUMED
            return plan.model_copy(deep=True)

    def clear(self) -> None:
        with self._lock:
            self._plans.clear()


class AuditLog:
    def __init__(self, *, max_events: int = 200) -> None:
        self._events: deque[AuditEvent] = deque(maxlen=max_events)
        self._lock = RLock()

    def append(
        self,
        *,
        action: str,
        action_level: ActionLevel,
        status: ActionStatus,
        dry_run: bool,
        parameters_hash: str,
        summary: str,
        approval_plan_id: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=secrets.token_hex(12),
            action=action,
            action_level=action_level,
            status=status,
            dry_run=dry_run,
            parameters_hash=parameters_hash,
            approval_plan_id=approval_plan_id,
            summary=summary[:500],
        )
        with self._lock:
            self._events.append(event)
        return event.model_copy(deep=True)

    def report(self, limit: int = 20) -> AuditReport:
        bounded_limit = max(1, min(limit, 100))
        with self._lock:
            events = list(self._events)[-bounded_limit:]
        events.reverse()
        return AuditReport(
            events=[event.model_copy(deep=True) for event in events], count=len(events)
        )

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class ActionRuntime:
    def __init__(
        self,
        *,
        approvals: ApprovalPlanStore | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self.approvals = approvals or ApprovalPlanStore()
        self.audit = audit or AuditLog()
        self._idempotency: dict[tuple[str, str], tuple[str, ActionResult]] = {}
        self._lock = RLock()

    def get_idempotent_result(
        self,
        *,
        action: str,
        key: str | None,
        parameters_hash: str,
    ) -> ActionResult | None:
        if key is None:
            return None
        with self._lock:
            stored = self._idempotency.get((action, key))
        if stored is None:
            return None
        stored_hash, result = stored
        if not secrets.compare_digest(stored_hash, parameters_hash):
            raise ApprovalRejectedError(
                "The idempotency key was already used with other parameters."
            )
        return result.model_copy(deep=True)

    def store_idempotent_result(
        self,
        *,
        action: str,
        key: str | None,
        parameters_hash: str,
        result: ActionResult,
    ) -> None:
        if key is None:
            return
        with self._lock:
            self._idempotency[(action, key)] = (parameters_hash, result.model_copy(deep=True))

    def clear(self) -> None:
        self.approvals.clear()
        self.audit.clear()
        with self._lock:
            self._idempotency.clear()
