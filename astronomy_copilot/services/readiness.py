from __future__ import annotations

import hashlib
import json
from datetime import timezone
from typing import Any, Protocol

from astronomy_copilot.adapters.nina import NinaResponseError, NinaUnavailableError
from astronomy_copilot.diagnostics.camera import evaluate_camera
from astronomy_copilot.diagnostics.common import evidence, unknown_finding
from astronomy_copilot.diagnostics.guider import evaluate_guider
from astronomy_copilot.diagnostics.mount import evaluate_mount
from astronomy_copilot.diagnostics.plate_solving import evaluate_plate_solving
from astronomy_copilot.models.diagnostics import (
    Confidence,
    DiagnosticFinding,
    FindingImpact,
    ImagingReadiness,
    LatestErrorReport,
    LatestErrorState,
    NextActionRecommendation,
    Severity,
)
from astronomy_copilot.models.status import OverallState


class ReadinessAdapter(Protocol):
    async def get_diagnostic_snapshot(self) -> dict[str, Any]: ...


COMPONENT_ORDER = {
    "nina": 0,
    "camera": 1,
    "mount": 2,
    "guider": 3,
    "plate_solving": 4,
}
SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.ERROR: 1,
    Severity.WARNING: 2,
    Severity.INFO: 3,
}
IMPACT_ORDER = {
    FindingImpact.BLOCKING: 0,
    FindingImpact.WARNING: 1,
    FindingImpact.UNKNOWN: 2,
}


def finding_sort_key(finding: DiagnosticFinding) -> tuple[int, int, int, str]:
    return (
        IMPACT_ORDER[finding.impact],
        SEVERITY_ORDER[finding.severity],
        COMPONENT_ORDER.get(finding.component, 99),
        finding.code,
    )


def offline_finding() -> DiagnosticFinding:
    return DiagnosticFinding(
        code="nina.offline",
        component="nina",
        issue="NINA Advanced API is unavailable.",
        evidence=[evidence("nina", "connection", "unavailable_or_timeout")],
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        impact=FindingImpact.BLOCKING,
        recommended_action="Start NINA and confirm the Advanced API endpoint is reachable.",
        retry_variable="nina_availability",
    )


def malformed_finding() -> DiagnosticFinding:
    return unknown_finding(
        "nina",
        "diagnostic_snapshot",
        "NINA diagnostic telemetry is malformed or unsuccessful.",
        "Refresh NINA telemetry and inspect the Advanced API response.",
        code="nina.diagnostic_snapshot_unknown",
    )


def evaluate_snapshot(snapshot: dict[str, Any]) -> list[DiagnosticFinding]:
    equipment = snapshot.get("equipment")
    diagnostics = snapshot.get("diagnostics")
    if not isinstance(equipment, dict) or not isinstance(diagnostics, dict):
        return [malformed_finding()]

    findings = [
        *evaluate_camera(equipment.get("camera")),
        *evaluate_mount(equipment.get("mount")),
        *evaluate_guider(equipment.get("guider")),
        *evaluate_plate_solving(diagnostics.get("plate_solving")),
    ]
    return sorted(findings, key=finding_sort_key)


def readiness_from_findings(findings: list[DiagnosticFinding]) -> ImagingReadiness:
    blocking = [finding for finding in findings if finding.impact == FindingImpact.BLOCKING]
    warnings = [finding for finding in findings if finding.impact == FindingImpact.WARNING]
    unknowns = [finding for finding in findings if finding.impact == FindingImpact.UNKNOWN]

    if blocking:
        state = OverallState.BLOCKED
        summary = f"Imaging is blocked by {len(blocking)} known condition(s)."
    elif unknowns:
        state = OverallState.UNKNOWN
        summary = (
            f"Imaging readiness is unknown because {len(unknowns)} required signal(s) are missing."
        )
    elif warnings:
        state = OverallState.DEGRADED
        summary = f"Imaging readiness is degraded by {len(warnings)} active condition(s)."
    else:
        state = OverallState.READY
        summary = "Camera, mount, guider, and plate-solving telemetry report ready conditions."

    return ImagingReadiness(
        state=state,
        ready=state == OverallState.READY,
        summary=summary,
        blocking_issues=blocking,
        warnings=warnings,
        unknowns=unknowns,
    )


def finding_timestamp(finding: DiagnosticFinding) -> float:
    if finding.occurred_at is None:
        return float("-inf")
    occurred_at = finding.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return occurred_at.timestamp()


def recommendation_id(finding: DiagnosticFinding) -> str:
    stable = {
        "code": finding.code,
        "component": finding.component,
        "evidence": [item.model_dump(mode="json") for item in finding.evidence],
        "recommended_action": finding.recommended_action,
        "retry_variable": finding.retry_variable,
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class ImagingReadinessService:
    def __init__(self, adapter: ReadinessAdapter):
        self.adapter = adapter

    async def _read_findings(self) -> list[DiagnosticFinding]:
        snapshot = await self.adapter.get_diagnostic_snapshot()
        if not isinstance(snapshot, dict):
            return [malformed_finding()]
        return evaluate_snapshot(snapshot)

    async def get_readiness(self) -> ImagingReadiness:
        try:
            findings = await self._read_findings()
        except NinaUnavailableError:
            finding = offline_finding()
            return ImagingReadiness(
                state=OverallState.OFFLINE,
                ready=False,
                summary="Imaging readiness is offline because NINA is unavailable.",
                blocking_issues=[finding],
            )
        except (NinaResponseError, ValueError, TypeError, KeyError):
            findings = [malformed_finding()]
        return readiness_from_findings(findings)

    async def get_latest_error(self) -> LatestErrorReport:
        try:
            findings = await self._read_findings()
        except NinaUnavailableError:
            return LatestErrorReport(
                state=LatestErrorState.OFFLINE,
                summary="NINA is unavailable; current error telemetry cannot be read.",
                error=offline_finding(),
            )
        except (NinaResponseError, ValueError, TypeError, KeyError):
            finding = malformed_finding()
            return LatestErrorReport(
                state=LatestErrorState.UNKNOWN,
                summary="The latest NINA error is unknown because telemetry is malformed.",
                warnings=[finding],
            )

        reported_errors = [
            finding
            for finding in findings
            if finding.code.endswith(".reported_error")
            or finding.code.endswith(".error_state")
            or finding.code.endswith(".failed_state")
        ]
        unknowns = [finding for finding in findings if finding.impact == FindingImpact.UNKNOWN]
        if reported_errors:
            latest = max(
                reported_errors,
                key=lambda finding: (finding_timestamp(finding), -finding_sort_key(finding)[2]),
            )
            return LatestErrorReport(
                state=LatestErrorState.FOUND,
                summary=f"The latest current error is reported by {latest.component}.",
                error=latest,
                warnings=unknowns,
            )
        if unknowns:
            return LatestErrorReport(
                state=LatestErrorState.UNKNOWN,
                summary="No current error was reported, but incomplete telemetry prevents confirmation.",
                warnings=unknowns,
            )
        return LatestErrorReport(
            state=LatestErrorState.NONE,
            summary="No current camera, mount, guider, or plate-solving error was reported.",
        )

    async def recommend_next_action(
        self, previous_recommendation_id: str | None = None
    ) -> NextActionRecommendation:
        readiness = await self.get_readiness()
        candidates = [
            *readiness.blocking_issues,
            *readiness.warnings,
            *readiness.unknowns,
        ]
        if not candidates:
            return NextActionRecommendation(
                readiness_state=readiness.state,
                should_retry=False,
            )

        recommendation = sorted(candidates, key=finding_sort_key)[0]
        identifier = recommendation_id(recommendation)
        repeated = previous_recommendation_id == identifier
        return NextActionRecommendation(
            readiness_state=readiness.state,
            recommendation=recommendation,
            recommendation_id=identifier,
            should_retry=not repeated,
            repeat_warning=(
                "The triggering evidence has not changed. Do not repeat the same failed action; "
                "change or re-check the named diagnostic variable first."
                if repeated
                else None
            ),
        )
