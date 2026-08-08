from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from astronomy_copilot.image_analysis.fits import representable_range
from astronomy_copilot.image_analysis.quality import analyze_pixels
from astronomy_copilot.models.image_analysis import IndicatorState
from astronomy_copilot.services.image_analysis import quality_indicators

pytestmark = pytest.mark.unit


def test_unsigned_16_bit_fits_range_is_reconstructed_from_bzero():
    header = fits.Header({"BITPIX": 16, "BZERO": 32768, "BSCALE": 1})

    assert representable_range(header, 16) == (0.0, 65535.0)


def test_float_pixels_without_ceiling_keep_saturation_evidence_unavailable():
    data = np.arange(100, dtype=float).reshape(10, 10)

    result = analyze_pixels(
        data,
        representable=None,
        saturation_fraction=0.98,
        star_detection_sigma=5.0,
    )
    saturation = {item.code: item for item in quality_indicators(result)}["saturation"]

    assert result.saturation_percent is None
    assert saturation.state == IndicatorState.UNAVAILABLE
    assert "ceiling" in saturation.summary


def test_missing_star_candidates_is_not_reported_as_zero_focus_or_trailing():
    data = np.full((32, 32), 1000.0)

    result = analyze_pixels(
        data,
        representable=(0.0, 65535.0),
        saturation_fraction=0.98,
        star_detection_sigma=5.0,
    )
    indicators = {item.code: item for item in quality_indicators(result)}

    assert result.detected_stars == 0
    assert result.hfr is None
    assert result.fwhm is None
    assert result.ellipticity is None
    assert result.trailing_score is None
    assert indicators["severe_defocus"].state == IndicatorState.UNAVAILABLE
    assert indicators["likely_trailing"].state == IndicatorState.UNAVAILABLE


def test_nonfinite_only_image_is_unavailable_for_pixel_measurements():
    with pytest.raises(ValueError, match="no finite pixel evidence"):
        analyze_pixels(
            np.full((8, 8), np.nan),
            representable=None,
            saturation_fraction=0.98,
            star_detection_sigma=5.0,
        )
