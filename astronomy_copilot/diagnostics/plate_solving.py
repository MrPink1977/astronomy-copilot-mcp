from __future__ import annotations

from typing import Any

from astronomy_copilot.diagnostics.common import (
    evidence,
    get_value,
    reported_error_finding,
    telemetry_missing,
    unknown_finding,
)
from astronomy_copilot.models.diagnostics import (
    Confidence,
    DiagnosticFinding,
    FindingImpact,
    Severity,
)


def evaluate_plate_solving(raw: Any) -> list[DiagnosticFinding]:
    component = "plate_solving"
    if telemetry_missing(raw):
        return [
            unknown_finding(
                component,
                "response",
                "Plate-solving telemetry is unavailable; solver readiness is unknown.",
                "Verify the configured plate solver and refresh telemetry.",
            )
        ]

    findings: list[DiagnosticFinding] = []
    reported_error = reported_error_finding(component, raw)
    if reported_error:
        findings.append(reported_error)

    running = get_value(raw, "Running")
    operation = get_value(raw, "CurrentOperation", "State")
    if not isinstance(running, bool):
        findings.append(
            unknown_finding(
                component,
                "Running",
                "Plate-solve running state is missing or malformed.",
                "Refresh plate-solving telemetry before declaring readiness.",
                code="plate_solving.state_unknown",
            )
        )
        return findings

    if running:
        findings.append(
            DiagnosticFinding(
                code="plate_solving.running",
                component=component,
                issue="A plate-solving operation is currently running.",
                evidence=[
                    evidence(component, "Running", running),
                    evidence(component, "CurrentOperation", operation),
                ],
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
                impact=FindingImpact.WARNING,
                recommended_action="Wait for the current plate solve to finish.",
                retry_variable="plate_solve_running_state",
            )
        )
    elif (
        isinstance(operation, str)
        and any(token in operation.casefold() for token in ("error", "failed", "failure"))
        and reported_error is None
    ):
        findings.append(
            DiagnosticFinding(
                code="plate_solving.failed_state",
                component=component,
                issue=f"Plate solving reports '{operation}'.",
                evidence=[evidence(component, "CurrentOperation", operation)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Inspect the plate-solver result before changing solve settings.",
                retry_variable="plate_solve_failure_condition",
            )
        )
    return findings
