from __future__ import annotations

import hashlib
import socket

import numpy as np
import pytest
from astropy.io import fits

from astronomy_copilot.models.image_analysis import (
    AnalysisState,
    EvidenceState,
    FitsAnalysisInput,
    IndicatorState,
)
from astronomy_copilot.services.image_analysis import FitsAnalysisService
from tests.support.fits_factory import controlled_image_recipe, write_controlled_fits

pytestmark = pytest.mark.integration


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze_fixture(tmp_path, name):
    path = tmp_path / f"{name}.fits"
    pixels = write_controlled_fits(path, controlled_image_recipe(name))
    report = FitsAnalysisService().analyze(FitsAnalysisInput(file_path=str(path)))
    return path, pixels, report


def test_controlled_round_star_fixture_matches_expected_measurements_without_network_or_writes(
    tmp_path, monkeypatch
):
    path = tmp_path / "round-star-field.fits"
    pixels = write_controlled_fits(path, controlled_image_recipe("round_star_field"))
    original_hash = sha256(path)
    original_mtime = path.stat().st_mtime_ns

    def forbidden_network(*args, **kwargs):
        raise AssertionError("local FITS analysis attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    report = FitsAnalysisService().analyze(FitsAnalysisInput(file_path=str(path)))

    assert report.state == AnalysisState.COMPLETE
    assert report.file_name == "round-star-field.fits"
    assert report.hdu_index == 0
    assert report.metadata["image_width"].value == 96
    assert report.metadata["image_height"].value == 80
    assert report.metadata["bit_depth"].value == 16
    assert report.metadata["exposure"].value == 30.0
    assert report.metadata["gain"].value == 120
    assert report.metadata["sensor_temperature"].value == -10.5
    assert report.metadata["filter"].value == "L"
    assert report.measurements["minimum"].value == float(np.min(pixels))
    assert report.measurements["maximum"].value == float(np.max(pixels))
    assert report.measurements["mean"].value == pytest.approx(float(np.mean(pixels)), abs=1e-5)
    assert report.measurements["median"].value == float(np.median(pixels))
    assert 12 <= report.measurements["detected_star_count"].value <= 16
    assert 1.0 <= report.measurements["median_hfr"].value <= 2.0
    assert 2.5 <= report.measurements["median_fwhm"].value <= 4.0
    assert report.measurements["median_ellipticity"].value < 0.1
    assert report.measurements["hot_pixel_count"].value == 12
    assert 1.0 < report.measurements["background_gradient"].value < 4.0
    assert sha256(path) == original_hash
    assert path.stat().st_mtime_ns == original_mtime
    assert all(item.method and item.unit for item in report.measurements.values())
    assert all(item.method and item.threshold and item.limitations for item in report.indicators)


def test_controlled_trailed_fixture_detects_aligned_elongation(tmp_path):
    _, _, report = analyze_fixture(tmp_path, "trailed_star_field")
    indicators = {item.code: item for item in report.indicators}

    assert report.measurements["detected_star_count"].value == 10
    assert report.measurements["median_ellipticity"].value > 0.5
    assert report.measurements["trailing_score"].value > 0.5
    assert indicators["likely_trailing"].state == IndicatorState.DETECTED


def test_controlled_saturated_gradient_fixture_has_expected_percentages(tmp_path):
    _, _, report = analyze_fixture(tmp_path, "saturated_gradient")
    indicators = {item.code: item for item in report.indicators}

    assert report.measurements["saturation_percentage"].value == pytest.approx(5.208333, abs=1e-6)
    assert indicators["saturation"].state == IndicatorState.DETECTED
    assert indicators["clipping"].state == IndicatorState.DETECTED
    assert indicators["severe_background_gradient"].state == IndicatorState.DETECTED


def test_unavailable_headers_and_ceiling_are_not_negative_findings(tmp_path):
    _, _, report = analyze_fixture(tmp_path, "float_low_signal")
    indicators = {item.code: item for item in report.indicators}

    assert report.state == AnalysisState.PARTIAL
    assert report.metadata["exposure"].state == EvidenceState.UNAVAILABLE
    assert report.metadata["gain"].state == EvidenceState.UNAVAILABLE
    assert report.measurements["saturation_percentage"].state == EvidenceState.UNAVAILABLE
    assert report.measurements["median_hfr"].state == EvidenceState.UNAVAILABLE
    assert indicators["saturation"].state == IndicatorState.UNAVAILABLE
    assert indicators["severe_defocus"].state == IndicatorState.UNAVAILABLE
    assert indicators["low_usable_signal"].state == IndicatorState.DETECTED


def test_non_2d_fits_returns_metadata_and_unavailable_pixel_evidence(tmp_path):
    path = tmp_path / "cube.fits"
    fits.PrimaryHDU(np.zeros((2, 8, 8), dtype=np.uint16)).writeto(path)

    report = FitsAnalysisService().analyze(FitsAnalysisInput(file_path=str(path)))

    assert report.state == AnalysisState.PARTIAL
    assert report.metadata["axis_count"].value == 3
    assert report.measurements == {}
    assert "two-dimensional" in report.warnings[0]


def test_invalid_local_path_returns_typed_unavailable_without_echoing_path(tmp_path):
    missing = tmp_path / "private-observatory-name.fits"

    report = FitsAnalysisService().analyze(FitsAnalysisInput(file_path=str(missing)))

    assert report.state == AnalysisState.UNAVAILABLE
    assert report.file_name is None
    assert str(missing) not in report.summary
    assert report.measurements == {}
