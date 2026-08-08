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


def evaluate_guider(raw: Any) -> list[DiagnosticFinding]:
    component = "guider"
    if telemetry_missing(raw):
        return [
            unknown_finding(
                component,
                "response",
                "Guider telemetry is unavailable; guiding readiness is unknown.",
                "Refresh telemetry or inspect the NINA guider panel.",
            )
        ]

    connected = get_value(raw, "Connected")
    if not isinstance(connected, bool):
        return [
            unknown_finding(
                component,
                "Connected",
                "Guider connection state was not reported as a boolean.",
                "Refresh guider telemetry before diagnosing guiding.",
            )
        ]
    if not connected:
        return [
            DiagnosticFinding(
                code="guider.disconnected",
                component=component,
                issue="The guider is disconnected.",
                evidence=[evidence(component, "Connected", connected)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Connect the configured guider in NINA.",
                retry_variable="guider_connection",
            )
        ]

    findings: list[DiagnosticFinding] = []
    reported_error = reported_error_finding(component, raw)
    if reported_error:
        findings.append(reported_error)

    state = get_value(raw, "State")
    if not isinstance(state, str) or not state.strip():
        findings.append(
            unknown_finding(
                component,
                "State",
                "Guider state is missing; active guiding cannot be confirmed.",
                "Refresh guider telemetry before declaring imaging readiness.",
                code="guider.state_unknown",
            )
        )
        return findings

    normalized = state.strip().casefold()
    if normalized in {"guiding", "guided"}:
        return findings
    if normalized in {"calibrating", "settling", "dithering"}:
        findings.append(
            DiagnosticFinding(
                code="guider.transitional_state",
                component=component,
                issue=f"The guider is {normalized}; guiding is not yet settled.",
                evidence=[evidence(component, "State", state)],
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
                impact=FindingImpact.WARNING,
                recommended_action="Wait for the guider to reach the guiding state.",
                retry_variable="guider_state",
            )
        )
    elif normalized in {"looping", "selecting", "starselect"}:
        findings.append(
            DiagnosticFinding(
                code="guider.no_guide_star",
                component=component,
                issue="The guider is looping but has not started guiding.",
                evidence=[evidence(component, "State", state)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Select a guide star in the guider.",
                retry_variable="guider_star_selection",
            )
        )
    elif normalized in {"stopped", "idle", "connected"}:
        findings.append(
            DiagnosticFinding(
                code="guider.not_guiding",
                component=component,
                issue="The guider is connected but not guiding.",
                evidence=[evidence(component, "State", state)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Start guiding after confirming a guide star is selected.",
                retry_variable="guider_running_state",
            )
        )
    elif normalized in {"lost", "lostlock", "error", "failed"} and reported_error is None:
        findings.append(
            DiagnosticFinding(
                code="guider.failed_state",
                component=component,
                issue=f"The guider reports the state '{state}'.",
                evidence=[evidence(component, "State", state)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Inspect the guider for its current failure before retrying.",
                retry_variable="guider_failure_condition",
            )
        )
    else:
        findings.append(
            unknown_finding(
                component,
                "State",
                f"The guider state '{state}' is not recognized by the reviewed rule set.",
                "Inspect the NINA guider panel and record this state before adding a rule.",
                code="guider.unrecognized_state",
            )
        )
    return findings
