from __future__ import annotations

import numpy as np

from astronomy_copilot.image_analysis.fits import (
    FitsUnavailableError,
    LoadedFits,
    header_value,
    load_fits_read_only,
    representable_range,
)
from astronomy_copilot.image_analysis.quality import PixelAnalysis, analyze_pixels
from astronomy_copilot.models.image_analysis import (
    AnalysisState,
    EvidenceState,
    FitsAnalysisInput,
    FitsAnalysisReport,
    ImageMeasurement,
    ImageQualityIndicator,
    IndicatorState,
)

POINT_SOURCE_LIMITATIONS = [
    "Detections are thresholded point-source candidates, not confirmed stars.",
    "Crowding, color mosaics, hot pixels, undersampling, and defocus can change the count.",
]
SHAPE_LIMITATIONS = [
    "HFR, FWHM, and ellipticity are approximate pixel-domain estimates from detected candidates.",
    "No plate scale or seeing correction is applied.",
]


def _number(value: float) -> float:
    return round(float(value), 6)


def available(
    value: str | int | float | bool,
    unit: str,
    method: str,
    *,
    threshold: str | None = None,
    limitations: list[str] | None = None,
) -> ImageMeasurement:
    if isinstance(value, float):
        value = _number(value)
    return ImageMeasurement(
        state=EvidenceState.AVAILABLE,
        value=value,
        unit=unit,
        method=method,
        threshold=threshold,
        limitations=limitations or [],
    )


def unavailable(
    unit: str,
    method: str,
    limitation: str,
    *,
    threshold: str | None = None,
) -> ImageMeasurement:
    return ImageMeasurement(
        state=EvidenceState.UNAVAILABLE,
        unit=unit,
        method=method,
        threshold=threshold,
        limitations=[limitation],
    )


def _header_measurement(
    loaded: LoadedFits,
    keys: tuple[str, ...],
    unit: str,
) -> ImageMeasurement:
    value = header_value(loaded.header, keys)
    method = f"FITS header keyword lookup: {', '.join(keys)}"
    if value is None:
        return unavailable(unit, method, "None of the reviewed FITS keywords is present.")
    return available(value, unit, method)


def metadata_measurements(loaded: LoadedFits) -> dict[str, ImageMeasurement]:
    width = loaded.shape[-1] if loaded.shape else 0
    height = loaded.shape[-2] if len(loaded.shape) >= 2 else 0
    bit_depth = abs(loaded.bitpix) if loaded.bitpix is not None else None
    metadata = {
        "image_width": available(width, "pixels", "FITS NAXIS1 image dimension"),
        "image_height": available(height, "pixels", "FITS NAXIS2 image dimension"),
        "axis_count": available(len(loaded.shape), "axes", "FITS image array dimensionality"),
        "exposure": _header_measurement(loaded, ("EXPTIME", "EXPOSURE"), "seconds"),
        "gain": _header_measurement(loaded, ("GAIN", "EGAIN"), "camera gain units"),
        "sensor_temperature": _header_measurement(
            loaded, ("CCD-TEMP", "SENSORT", "SET-TEMP"), "degrees Celsius"
        ),
        "filter": _header_measurement(loaded, ("FILTER",), "name"),
    }
    metadata["bit_depth"] = (
        available(bit_depth, "bits per stored sample", "Absolute FITS BITPIX value")
        if bit_depth is not None
        else unavailable(
            "bits per stored sample",
            "FITS BITPIX header lookup",
            "BITPIX is absent or malformed.",
        )
    )
    return metadata


def _metric(
    value: float | int | None,
    unit: str,
    method: str,
    *,
    threshold: str | None = None,
    limitations: list[str] | None = None,
    unavailable_reason: str = "Required evidence was unavailable.",
) -> ImageMeasurement:
    if value is None:
        return unavailable(unit, method, unavailable_reason, threshold=threshold)
    return available(
        value,
        unit,
        method,
        threshold=threshold,
        limitations=limitations,
    )


def pixel_measurements(
    pixels: PixelAnalysis,
    request: FitsAnalysisInput,
) -> dict[str, ImageMeasurement]:
    statistics_method = "Finite pixels in the selected two-dimensional FITS HDU"
    point_method = (
        f"Local maxima above median + {request.star_detection_sigma:g} robust sigma; "
        "minimum four-pixel footprint and five-pixel peak separation"
    )
    shape_method = "Background-subtracted 9x9 candidate moments and radial flux integration"
    return {
        "minimum": available(pixels.minimum, "ADU", statistics_method),
        "maximum": available(pixels.maximum, "ADU", statistics_method),
        "mean": available(pixels.mean, "ADU", statistics_method),
        "median": available(pixels.median, "ADU", statistics_method),
        "valid_pixel_count": available(pixels.valid_pixels, "pixels", statistics_method),
        "noise_sigma": available(
            pixels.noise_sigma,
            "ADU",
            "1.4826 times median absolute deviation; standard deviation fallback",
        ),
        "saturation_percentage": _metric(
            pixels.saturation_percent,
            "percent of valid pixels",
            "Pixels at or above the reviewed representable-range threshold",
            threshold=f">= {request.saturation_fraction:.3f} of representable range",
            unavailable_reason="No integer range, SATURATE, or DATAMAX evidence was available.",
        ),
        "low_clipping_percentage": _metric(
            pixels.low_clipping_percent,
            "percent of valid pixels",
            "Pixels in the lowest one percent of the reviewed representable range",
            threshold="<= 1% of representable range",
            unavailable_reason="The representable pixel range was unavailable.",
        ),
        "high_clipping_percentage": _metric(
            pixels.high_clipping_percent,
            "percent of valid pixels",
            "Pixels at or above the saturation threshold",
            threshold=f">= {request.saturation_fraction:.3f} of representable range",
            unavailable_reason="The representable pixel range was unavailable.",
        ),
        "detected_star_count": available(
            pixels.detected_stars,
            "candidates",
            point_method,
            threshold=f"peak > median + {request.star_detection_sigma:g} robust sigma",
            limitations=POINT_SOURCE_LIMITATIONS,
        ),
        "median_hfr": _metric(
            pixels.hfr,
            "pixels",
            shape_method,
            limitations=SHAPE_LIMITATIONS,
            unavailable_reason="No qualifying point-source candidates were detected.",
        ),
        "median_fwhm": _metric(
            pixels.fwhm,
            "pixels",
            shape_method,
            limitations=SHAPE_LIMITATIONS,
            unavailable_reason="No qualifying point-source candidates were detected.",
        ),
        "median_ellipticity": _metric(
            pixels.ellipticity,
            "unitless; 0 round to 1 elongated",
            "Eigenvalues of background-subtracted candidate second moments",
            limitations=SHAPE_LIMITATIONS,
            unavailable_reason="No qualifying point-source candidates were detected.",
        ),
        "background_gradient": available(
            pixels.background_gradient_percent,
            "percent of median background",
            "Least-squares plane over an 8x8 grid of block medians",
            threshold=">= 20% indicates a severe gradient",
            limitations=[
                "Extended nebulosity or a bright target can resemble a background gradient."
            ],
        ),
        "hot_pixel_count": available(
            pixels.hot_pixel_count,
            "candidate pixels",
            "Isolated local maxima above median + 8 robust sigma",
            threshold="at most one adjacent pixel above median + 3 robust sigma",
            limitations=["Cosmic rays and undersampled stars can resemble hot pixels."],
        ),
        "trailing_score": _metric(
            pixels.trailing_score,
            "unitless",
            "Median ellipticity multiplied by doubled-angle orientation coherence",
            threshold=">= 0.21 with at least three candidates",
            limitations=SHAPE_LIMITATIONS,
            unavailable_reason="At least three qualifying candidates are required.",
        ),
        "signal_span": available(
            pixels.signal_span_sigma,
            "robust sigma",
            "99.5th percentile minus median, divided by robust noise sigma",
            threshold="< 5 sigma with no candidates indicates low usable signal",
        ),
    }


def _indicator(
    code: str,
    state: IndicatorState,
    summary: str,
    method: str,
    threshold: str,
    evidence: list[str],
    limitations: list[str],
) -> ImageQualityIndicator:
    return ImageQualityIndicator(
        code=code,
        state=state,
        summary=summary,
        method=method,
        threshold=threshold,
        evidence=evidence,
        limitations=limitations,
    )


def quality_indicators(pixels: PixelAnalysis) -> list[ImageQualityIndicator]:
    indicators: list[ImageQualityIndicator] = []
    if pixels.saturation_percent is None:
        saturation_state = IndicatorState.UNAVAILABLE
        saturation_summary = "Saturation could not be evaluated without a pixel ceiling."
    else:
        saturation_state = (
            IndicatorState.DETECTED
            if pixels.saturation_percent >= 1.0
            else IndicatorState.NOT_DETECTED
        )
        saturation_summary = (
            "Material saturation was detected."
            if saturation_state == IndicatorState.DETECTED
            else "Material saturation was not detected."
        )
    indicators.append(
        _indicator(
            "saturation",
            saturation_state,
            saturation_summary,
            "Percentage of pixels above the configured saturation level",
            ">= 1% saturated pixels",
            ["saturation_percentage"],
            ["A reliable integer range or SATURATE/DATAMAX header is required."],
        )
    )

    if pixels.low_clipping_percent is None or pixels.high_clipping_percent is None:
        clipping_state = IndicatorState.UNAVAILABLE
        clipping_summary = "Clipping could not be evaluated without a representable range."
    else:
        clipping_state = (
            IndicatorState.DETECTED
            if max(pixels.low_clipping_percent, pixels.high_clipping_percent) >= 1.0
            else IndicatorState.NOT_DETECTED
        )
        clipping_summary = (
            "Low- or high-end clipping was detected."
            if clipping_state == IndicatorState.DETECTED
            else "Material low- or high-end clipping was not detected."
        )
    indicators.append(
        _indicator(
            "clipping",
            clipping_state,
            clipping_summary,
            "Low- and high-range pixel fractions",
            ">= 1% at either reviewed range boundary",
            ["low_clipping_percentage", "high_clipping_percentage"],
            ["Astronomical backgrounds near the detector floor can trigger low clipping."],
        )
    )

    too_few = pixels.detected_stars < 10
    indicators.append(
        _indicator(
            "too_few_stars",
            IndicatorState.DETECTED if too_few else IndicatorState.NOT_DETECTED,
            (
                "Too few point-source candidates were detected for a robust solve-quality claim."
                if too_few
                else "At least ten point-source candidates were detected."
            ),
            "Thresholded point-source candidate count",
            "< 10 candidates",
            ["detected_star_count"],
            POINT_SOURCE_LIMITATIONS,
        )
    )

    if pixels.hfr is None:
        focus_state = IndicatorState.UNAVAILABLE
        focus_summary = "Focus quality is unavailable because no candidates were measurable."
    else:
        focus_state = IndicatorState.DETECTED if pixels.hfr >= 5.0 else IndicatorState.NOT_DETECTED
        focus_summary = (
            "A severe-defocus indicator was detected."
            if focus_state == IndicatorState.DETECTED
            else "The severe-defocus threshold was not reached."
        )
    indicators.append(
        _indicator(
            "severe_defocus",
            focus_state,
            focus_summary,
            "Median candidate half-flux radius",
            ">= 5 pixels",
            ["median_hfr"],
            SHAPE_LIMITATIONS,
        )
    )

    if pixels.trailing_score is None:
        trailing_state = IndicatorState.UNAVAILABLE
        trailing_summary = (
            "Trailing is unavailable because fewer than three candidates were measured."
        )
    else:
        trailing_state = (
            IndicatorState.DETECTED
            if pixels.trailing_score >= 0.21
            else IndicatorState.NOT_DETECTED
        )
        trailing_summary = (
            "Aligned elongation consistent with likely trailing was detected."
            if trailing_state == IndicatorState.DETECTED
            else "The likely-trailing threshold was not reached."
        )
    indicators.append(
        _indicator(
            "likely_trailing",
            trailing_state,
            trailing_summary,
            "Ellipticity and common orientation score",
            ">= 0.21 with at least three candidates",
            ["trailing_score", "median_ellipticity", "detected_star_count"],
            ["Optical aberrations and wind can resemble tracking trails."],
        )
    )

    severe_gradient = pixels.background_gradient_percent >= 20.0
    indicators.append(
        _indicator(
            "severe_background_gradient",
            IndicatorState.DETECTED if severe_gradient else IndicatorState.NOT_DETECTED,
            (
                "A severe background gradient was detected."
                if severe_gradient
                else "The severe background-gradient threshold was not reached."
            ),
            "Fitted plane peak-to-peak range relative to median background",
            ">= 20%",
            ["background_gradient"],
            ["Extended targets and bright stars can bias the background model."],
        )
    )

    hot_limit = max(10, int(np.ceil(pixels.valid_pixels * 0.0001)))
    hot_detected = pixels.hot_pixel_count > hot_limit
    indicators.append(
        _indicator(
            "hot_pixels",
            IndicatorState.DETECTED if hot_detected else IndicatorState.NOT_DETECTED,
            (
                "An elevated isolated hot-pixel population was detected."
                if hot_detected
                else "The elevated hot-pixel threshold was not reached."
            ),
            "Isolated high-sigma local maxima count",
            f"> {hot_limit} candidates",
            ["hot_pixel_count", "valid_pixel_count"],
            ["A single frame cannot distinguish persistent hot pixels from cosmic rays."],
        )
    )

    low_signal = pixels.detected_stars == 0 and pixels.signal_span_sigma < 5.0
    indicators.append(
        _indicator(
            "low_usable_signal",
            IndicatorState.DETECTED if low_signal else IndicatorState.NOT_DETECTED,
            (
                "Very low usable signal was detected."
                if low_signal
                else "The low-usable-signal threshold was not reached."
            ),
            "High-percentile signal span and point-source candidate count",
            "signal span < 5 robust sigma and zero candidates",
            ["signal_span", "detected_star_count"],
            [
                "This does not prove a lens cap is on; clouds, short exposure, or a blank field can look similar."
            ],
        )
    )
    return indicators


class FitsAnalysisService:
    def analyze(self, request: FitsAnalysisInput) -> FitsAnalysisReport:
        try:
            loaded = load_fits_read_only(request.file_path, request.hdu_index)
        except FitsUnavailableError as exc:
            return FitsAnalysisReport(
                state=AnalysisState.UNAVAILABLE,
                summary=str(exc),
                warnings=["No image pixels or FITS metadata were analyzed."],
                limitations=["Analysis accepts local, uncompressed FITS files only."],
            )

        metadata = metadata_measurements(loaded)
        if loaded.data.ndim != 2:
            return FitsAnalysisReport(
                state=AnalysisState.PARTIAL,
                summary="FITS metadata was read, but pixel-quality evidence is unavailable.",
                file_name=loaded.path.name,
                hdu_index=loaded.hdu_index,
                metadata=metadata,
                warnings=["Pixel-quality analysis requires a two-dimensional FITS image."],
                limitations=["The original local image was opened read-only and was not modified."],
            )

        try:
            pixels = analyze_pixels(
                loaded.data,
                representable=representable_range(loaded.header, loaded.bitpix),
                saturation_fraction=request.saturation_fraction,
                star_detection_sigma=request.star_detection_sigma,
            )
        except (ValueError, TypeError, MemoryError) as exc:
            return FitsAnalysisReport(
                state=AnalysisState.PARTIAL,
                summary="FITS metadata was read, but pixel-quality evidence is unavailable.",
                file_name=loaded.path.name,
                hdu_index=loaded.hdu_index,
                metadata=metadata,
                warnings=[str(exc)[:300]],
                limitations=["The original local image was opened read-only and was not modified."],
            )

        measurements = pixel_measurements(pixels, request)
        indicators = quality_indicators(pixels)
        missing = [
            name for name, item in measurements.items() if item.state == EvidenceState.UNAVAILABLE
        ]
        detected = [item.code for item in indicators if item.state == IndicatorState.DETECTED]
        state = AnalysisState.PARTIAL if missing else AnalysisState.COMPLETE
        summary = (
            f"Local FITS analysis completed; detected indicators: {', '.join(detected)}."
            if detected
            else "Local FITS analysis completed with no reviewed quality indicator detected."
        )
        warnings = [f"Unavailable measurements: {', '.join(missing)}."] if missing else []
        return FitsAnalysisReport(
            state=state,
            summary=summary,
            file_name=loaded.path.name,
            hdu_index=loaded.hdu_index,
            metadata=metadata,
            measurements=measurements,
            indicators=indicators,
            warnings=warnings,
            limitations=[
                "Analysis is local and read-only; no image bytes are uploaded or transmitted.",
                "Single-frame indicators are screening evidence, not confirmed hardware diagnoses.",
                "Thresholds are pixel-domain defaults and may require instrument-specific calibration.",
            ],
        )
