from __future__ import annotations

from copy import deepcopy

import pytest

from astronomy_copilot.adapters.nina import NinaUnavailableError
from astronomy_copilot.diagnostics.guider import evaluate_guider
from astronomy_copilot.diagnostics.mount import evaluate_mount
from astronomy_copilot.diagnostics.plate_solving import evaluate_plate_solving
from astronomy_copilot.models.diagnostics import FindingImpact, LatestErrorState
from astronomy_copilot.services.readiness import ImagingReadinessService


pytestmark = pytest.mark.unit


class FixtureAdapter:
    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error

    async def get_diagnostic_snapshot(self):
        if self.error:
            raise self.error
        return deepcopy(self.snapshot)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "expected_state"),
    [
        ("ready.json", "READY"),
        ("degraded.json", "DEGRADED"),
        ("blocked.json", "BLOCKED"),
        ("unknown.json", "UNKNOWN"),
    ],
)
async def test_recorded_scenarios_produce_all_online_readiness_states(
    diagnostic_fixture, fixture_name, expected_state
):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture(fixture_name)))

    result = await service.get_readiness()

    assert result.state == expected_state
    assert result.ready is (expected_state == "READY")


@pytest.mark.asyncio
async def test_offline_readiness_is_distinct():
    service = ImagingReadinessService(FixtureAdapter(error=NinaUnavailableError()))

    result = await service.get_readiness()

    assert result.state == "OFFLINE"
    assert result.ready is False
    assert result.blocking_issues[0].code == "nina.offline"


@pytest.mark.asyncio
async def test_every_finding_has_reviewable_evidence_and_one_retry_variable(diagnostic_fixture):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture("blocked.json")))

    result = await service.get_readiness()

    for finding in [*result.blocking_issues, *result.warnings, *result.unknowns]:
        assert finding.component
        assert finding.issue
        assert finding.evidence
        assert finding.severity
        assert finding.confidence
        assert finding.recommended_action
        assert finding.retry_variable
        assert "," not in finding.retry_variable


def test_mount_rules_are_deterministic_and_change_one_condition():
    raw = {"Connected": True, "AtPark": True, "Slewing": False, "Tracking": False}

    first = evaluate_mount(raw)
    second = evaluate_mount(raw)

    assert first == second
    assert [finding.code for finding in first] == ["mount.parked"]
    assert first[0].retry_variable == "mount_park_state"


def test_guider_looping_recommends_star_selection_before_starting_guiding():
    findings = evaluate_guider({"Connected": True, "State": "Looping"})

    assert [finding.code for finding in findings] == ["guider.no_guide_star"]
    assert findings[0].recommended_action == "Select a guide star in the guider."
    assert findings[0].retry_variable == "guider_star_selection"


def test_plate_solve_error_references_reported_evidence():
    findings = evaluate_plate_solving(
        {
            "Running": False,
            "CurrentOperation": "Failed",
            "Error": "ASTAP plate solve failed",
        }
    )

    assert [finding.code for finding in findings] == ["plate_solving.reported_error"]
    assert findings[0].evidence[0].observed == "ASTAP plate solve failed"


@pytest.mark.asyncio
async def test_missing_telemetry_reports_unknown_without_inventing_fault(diagnostic_fixture):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture("unknown.json")))

    result = await service.get_readiness()

    assert result.state == "UNKNOWN"
    assert result.blocking_issues == []
    assert result.unknowns[0].impact == FindingImpact.UNKNOWN
    assert "unknown" in result.unknowns[0].issue.casefold() or "missing" in result.unknowns[0].issue.casefold()


@pytest.mark.asyncio
async def test_latest_error_uses_timestamp_and_sanitizes_sensitive_context(diagnostic_fixture):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture("latest_error.json")))

    result = await service.get_latest_error()

    assert result.state == LatestErrorState.FOUND
    assert result.error is not None
    assert result.error.component == "camera"
    assert "[redacted_path]" in result.error.issue
    assert "secret-value" not in result.error.issue


@pytest.mark.asyncio
async def test_no_current_error_is_reported_for_ready_scenario(diagnostic_fixture):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture("ready.json")))

    result = await service.get_latest_error()

    assert result.state == LatestErrorState.NONE
    assert result.error is None


@pytest.mark.asyncio
async def test_recommendation_references_triggering_evidence(diagnostic_fixture):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture("blocked.json")))

    result = await service.recommend_next_action()

    assert result.recommendation is not None
    assert result.recommendation.code == "camera.disconnected"
    assert result.recommendation.evidence[0].field == "Connected"
    assert result.recommendation.evidence[0].observed is False
    assert result.recommendation_id
    assert result.should_retry is True


@pytest.mark.asyncio
async def test_unchanged_failed_recommendation_is_warned_and_not_retried(diagnostic_fixture):
    service = ImagingReadinessService(FixtureAdapter(diagnostic_fixture("blocked.json")))
    first = await service.recommend_next_action()

    repeated = await service.recommend_next_action(first.recommendation_id)

    assert repeated.recommendation_id == first.recommendation_id
    assert repeated.should_retry is False
    assert "evidence has not changed" in repeated.repeat_warning


@pytest.mark.asyncio
async def test_changed_condition_produces_a_new_recommendation_id(diagnostic_fixture):
    camera_blocked = diagnostic_fixture("blocked.json")
    mount_blocked = diagnostic_fixture("ready.json")
    mount_blocked["equipment"]["mount"]["AtPark"] = True

    first = await ImagingReadinessService(FixtureAdapter(camera_blocked)).recommend_next_action()
    changed = await ImagingReadinessService(FixtureAdapter(mount_blocked)).recommend_next_action(
        first.recommendation_id
    )

    assert changed.recommendation_id != first.recommendation_id
    assert changed.should_retry is True
    assert changed.repeat_warning is None
