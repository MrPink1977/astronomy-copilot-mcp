from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from astronomy_copilot.models.diagnostics import (
    Confidence,
    DiagnosticFinding,
    Evidence,
    FindingImpact,
    Severity,
)

MISSING = object()
ERROR_FIELDS = ("LastError", "Error", "ErrorMessage")
ERROR_TIME_FIELDS = ("LastErrorTime", "ErrorTime", "Timestamp", "Time")


def get_value(record: dict[str, Any], *names: str) -> Any:
    """Return a field using case-insensitive aliases without guessing its meaning."""
    lowered = {str(key).casefold(): value for key, value in record.items()}
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return MISSING


def telemetry_missing(raw: Any) -> bool:
    return isinstance(raw, Exception) or not isinstance(raw, dict)


def evidence(component: str, field: str, observed: Any) -> Evidence:
    if observed is MISSING:
        observed = None
    if not isinstance(observed, (str, int, float, bool)) and observed is not None:
        observed = str(observed)
    return Evidence(
        field=field,
        observed=observed,
        source=f"nina_advanced_api.{component}",
    )


def unknown_finding(
    component: str,
    field: str,
    issue: str,
    action: str,
    *,
    code: str | None = None,
) -> DiagnosticFinding:
    return DiagnosticFinding(
        code=code or f"{component}.telemetry_unknown",
        component=component,
        issue=issue,
        evidence=[evidence(component, field, None)],
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        impact=FindingImpact.UNKNOWN,
        recommended_action=action,
        retry_variable=f"{component}_telemetry",
    )


def sanitize_error_message(message: str) -> str:
    """Bound and redact common local-path and credential patterns from NINA errors."""
    sanitized = re.sub(
        r"(?i)\b(token|password|api[_-]?key|secret)\s*[=:]\s*[^\s,;]+",
        r"\1=[redacted]",
        message,
    )
    sanitized = re.sub(
        r"(?i)([?&](?:token|password|api[_-]?key|secret)=)[^&\s]+",
        r"\1[redacted]",
        sanitized,
    )
    sanitized = re.sub(r"\b[A-Za-z]:\\[^\r\n]+", "[redacted_path]", sanitized)
    return sanitized.strip()[:500]


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def reported_error_finding(component: str, raw: dict[str, Any]) -> DiagnosticFinding | None:
    error_value = get_value(raw, *ERROR_FIELDS)
    if not isinstance(error_value, str) or not error_value.strip():
        return None

    occurred_value = get_value(raw, *ERROR_TIME_FIELDS)
    return DiagnosticFinding(
        code=f"{component}.reported_error",
        component=component,
        issue=sanitize_error_message(error_value),
        evidence=[evidence(component, "reported_error", sanitize_error_message(error_value))],
        severity=Severity.ERROR,
        confidence=Confidence.HIGH,
        impact=FindingImpact.BLOCKING,
        recommended_action=f"Inspect the reported {component} error in NINA before retrying.",
        retry_variable=f"{component}_error_condition",
        occurred_at=parse_datetime(occurred_value),
    )
