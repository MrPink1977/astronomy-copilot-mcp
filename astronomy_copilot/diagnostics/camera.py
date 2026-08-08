from __future__ import annotations

from typing import Any

from astronomy_copilot.diagnostics.common import (
    MISSING,
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


def evaluate_camera(raw: Any) -> list[DiagnosticFinding]:
    component = "camera"
    if telemetry_missing(raw):
        return [
            unknown_finding(
                component,
                "response",
                "Camera telemetry is unavailable; camera health is unknown.",
                "Refresh telemetry or inspect the NINA camera panel.",
            )
        ]

    findings: list[DiagnosticFinding] = []
    connected = get_value(raw, "Connected")
    if not isinstance(connected, bool):
        return [
            unknown_finding(
                component,
                "Connected",
                "Camera connection state was not reported as a boolean.",
                "Refresh camera telemetry before diagnosing the camera.",
            )
        ]
    if not connected:
        findings.append(
            DiagnosticFinding(
                code="camera.disconnected",
                component=component,
                issue="The imaging camera is disconnected.",
                evidence=[evidence(component, "Connected", connected)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Connect the imaging camera in NINA, then refresh readiness.",
                retry_variable="camera_connection",
            )
        )
        return findings

    reported_error = reported_error_finding(component, raw)
    if reported_error:
        findings.append(reported_error)

    state = get_value(raw, "CameraState", "State")
    exposing = get_value(raw, "IsExposing")
    normalized_state = state.casefold() if isinstance(state, str) else None
    if exposing is True or normalized_state in {"exposing", "downloading", "download"}:
        findings.append(
            DiagnosticFinding(
                code="camera.busy",
                component=component,
                issue="The camera is busy with an exposure or image download.",
                evidence=[
                    evidence(component, "IsExposing", exposing),
                    evidence(component, "CameraState", state),
                ],
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Wait for the current camera operation to finish.",
                retry_variable="camera_activity",
            )
        )
    elif normalized_state in {"error", "failed"} and reported_error is None:
        findings.append(
            DiagnosticFinding(
                code="camera.error_state",
                component=component,
                issue="The camera reports an error state without a specific error message.",
                evidence=[evidence(component, "CameraState", state)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Inspect the NINA camera panel for the current error.",
                retry_variable="camera_error_condition",
            )
        )
    elif state is MISSING and exposing is MISSING:
        findings.append(
            unknown_finding(
                component,
                "CameraState",
                "Camera activity state is missing; readiness cannot be confirmed.",
                "Refresh camera telemetry before starting an imaging operation.",
                code="camera.activity_unknown",
            )
        )
    return findings
