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


def evaluate_mount(raw: Any) -> list[DiagnosticFinding]:
    component = "mount"
    if telemetry_missing(raw):
        return [
            unknown_finding(
                component,
                "response",
                "Mount telemetry is unavailable; mount health is unknown.",
                "Refresh telemetry or inspect the NINA mount panel.",
            )
        ]

    connected = get_value(raw, "Connected")
    if not isinstance(connected, bool):
        return [
            unknown_finding(
                component,
                "Connected",
                "Mount connection state was not reported as a boolean.",
                "Refresh mount telemetry before diagnosing the mount.",
            )
        ]
    if not connected:
        return [
            DiagnosticFinding(
                code="mount.disconnected",
                component=component,
                issue="The mount is disconnected.",
                evidence=[evidence(component, "Connected", connected)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Connect the mount in NINA, then refresh readiness.",
                retry_variable="mount_connection",
            )
        ]

    findings: list[DiagnosticFinding] = []
    reported_error = reported_error_finding(component, raw)
    if reported_error:
        findings.append(reported_error)

    parked = get_value(raw, "AtPark", "IsParked")
    slewing = get_value(raw, "Slewing", "IsSlewing")
    tracking = get_value(raw, "Tracking", "IsTracking", "TrackingEnabled")

    missing_fields = [
        field
        for field, value in (("parked", parked), ("slewing", slewing), ("tracking", tracking))
        if not isinstance(value, bool)
    ]
    if missing_fields:
        findings.append(
            unknown_finding(
                component,
                ",".join(missing_fields),
                "Required mount park, slew, or tracking telemetry is missing.",
                "Refresh mount telemetry before declaring imaging readiness.",
                code="mount.readiness_state_unknown",
            )
        )
        return findings

    if parked:
        findings.append(
            DiagnosticFinding(
                code="mount.parked",
                component=component,
                issue="The mount is parked.",
                evidence=[evidence(component, "AtPark", parked)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Prepare an approved unpark action before imaging.",
                retry_variable="mount_park_state",
            )
        )
    if slewing:
        findings.append(
            DiagnosticFinding(
                code="mount.slewing",
                component=component,
                issue="The mount is currently slewing.",
                evidence=[evidence(component, "Slewing", slewing)],
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Wait for the current slew to finish.",
                retry_variable="mount_slew_state",
            )
        )
    if not tracking and not parked:
        findings.append(
            DiagnosticFinding(
                code="mount.tracking_disabled",
                component=component,
                issue="Mount tracking is disabled.",
                evidence=[evidence(component, "Tracking", tracking)],
                severity=Severity.ERROR,
                confidence=Confidence.HIGH,
                impact=FindingImpact.BLOCKING,
                recommended_action="Enable sidereal tracking in NINA before imaging.",
                retry_variable="mount_tracking",
            )
        )
    return findings
