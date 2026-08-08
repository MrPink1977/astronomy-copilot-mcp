from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class StarShape:
    hfr: float
    fwhm: float
    ellipticity: float
    orientation_radians: float


@dataclass(frozen=True, slots=True)
class PixelAnalysis:
    minimum: float
    maximum: float
    mean: float
    median: float
    valid_pixels: int
    noise_sigma: float
    saturation_percent: float | None
    low_clipping_percent: float | None
    high_clipping_percent: float | None
    detected_stars: int
    hfr: float | None
    fwhm: float | None
    ellipticity: float | None
    trailing_score: float | None
    background_gradient_percent: float
    hot_pixel_count: int
    signal_span_sigma: float


def _robust_background(values: np.ndarray) -> tuple[float, float]:
    background = float(np.median(values))
    mad = float(np.median(np.abs(values - background)))
    sigma = 1.4826 * mad
    if sigma <= 0:
        sigma = float(np.std(values))
    return background, max(sigma, np.finfo(float).eps)


def _local_maxima(data: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    center = data[1:-1, 1:-1]
    mask = np.isfinite(center) & (center > threshold)
    strictly_greater = np.zeros(center.shape, dtype=bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            neighbor = data[1 + dy : data.shape[0] - 1 + dy, 1 + dx : data.shape[1] - 1 + dx]
            mask &= center >= neighbor
            strictly_greater |= center > neighbor
    y, x = np.nonzero(mask & strictly_greater)
    return y + 1, x + 1


def _select_separated_peaks(
    data: np.ndarray,
    y: np.ndarray,
    x: np.ndarray,
    minimum_separation: float = 5.0,
    maximum_peaks: int = 1000,
) -> list[tuple[int, int]]:
    if not len(y):
        return []
    order = np.argsort(data[y, x])[::-1][:5000]
    selected: list[tuple[int, int]] = []
    minimum_squared = minimum_separation**2
    for index in order:
        candidate = (int(y[index]), int(x[index]))
        if all(
            (candidate[0] - prior[0]) ** 2 + (candidate[1] - prior[1]) ** 2 >= minimum_squared
            for prior in selected
        ):
            selected.append(candidate)
            if len(selected) >= maximum_peaks:
                break
    return selected


def _measure_star(
    data: np.ndarray,
    y: int,
    x: int,
    noise_sigma: float,
    radius: int = 4,
) -> StarShape | None:
    if y < radius or x < radius or y + radius >= data.shape[0] or x + radius >= data.shape[1]:
        return None
    patch = data[y - radius : y + radius + 1, x - radius : x + radius + 1]
    border = np.concatenate((patch[0], patch[-1], patch[1:-1, 0], patch[1:-1, -1]))
    local_background = float(np.nanmedian(border))
    signal = np.clip(patch - local_background, 0.0, None)
    if np.count_nonzero(patch > local_background + 2.0 * noise_sigma) < 4:
        return None
    flux = float(np.sum(signal))
    if not np.isfinite(flux) or flux <= 0:
        return None

    yy, xx = np.indices(patch.shape, dtype=float)
    centroid_x = float(np.sum(signal * xx) / flux)
    centroid_y = float(np.sum(signal * yy) / flux)
    dx = xx - centroid_x
    dy = yy - centroid_y
    radius_values = np.sqrt(dx**2 + dy**2)
    order = np.argsort(radius_values, axis=None)
    cumulative = np.cumsum(signal.ravel()[order])
    half_index = int(np.searchsorted(cumulative, flux / 2.0, side="left"))
    hfr = float(radius_values.ravel()[order[min(half_index, len(order) - 1)]])

    covariance = np.array(
        [
            [np.sum(signal * dx * dx) / flux, np.sum(signal * dx * dy) / flux],
            [np.sum(signal * dx * dy) / flux, np.sum(signal * dy * dy) / flux],
        ]
    )
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    minor_variance = max(float(eigenvalues[0]), 0.0)
    major_variance = max(float(eigenvalues[1]), np.finfo(float).eps)
    ellipticity = 1.0 - np.sqrt(minor_variance / major_variance)
    fwhm = 2.35482 * np.sqrt((minor_variance + major_variance) / 2.0)
    major_axis = eigenvectors[:, 1]
    orientation = float(np.arctan2(major_axis[1], major_axis[0]))
    return StarShape(hfr, float(fwhm), float(ellipticity), orientation)


def _gradient_percent(data: np.ndarray, background: float, noise_sigma: float) -> float:
    height, width = data.shape
    rows = np.array_split(np.arange(height), min(8, height))
    columns = np.array_split(np.arange(width), min(8, width))
    samples: list[tuple[float, float, float]] = []
    for row in rows:
        for column in columns:
            block = data[np.ix_(row, column)]
            finite = block[np.isfinite(block)]
            if finite.size:
                samples.append(
                    (float(np.mean(column)), float(np.mean(row)), float(np.median(finite)))
                )
    if len(samples) < 3:
        return 0.0
    design = np.array([[x, y, 1.0] for x, y, _ in samples], dtype=float)
    values = np.array([value for _, _, value in samples], dtype=float)
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    corners = np.array(
        [
            [0.0, 0.0, 1.0],
            [width - 1.0, 0.0, 1.0],
            [0.0, height - 1.0, 1.0],
            [width - 1.0, height - 1.0, 1.0],
        ]
    )
    modeled = corners @ coefficients
    denominator = max(abs(background), noise_sigma, np.finfo(float).eps)
    return float(100.0 * np.ptp(modeled) / denominator)


def analyze_pixels(
    data: np.ndarray,
    *,
    representable: tuple[float, float] | None,
    saturation_fraction: float,
    star_detection_sigma: float,
) -> PixelAnalysis:
    if data.ndim != 2:
        raise ValueError("Pixel-quality measurements require a two-dimensional image.")
    finite_mask = np.isfinite(data)
    values = data[finite_mask]
    if not values.size:
        raise ValueError("The image contains no finite pixel evidence.")
    background, noise_sigma = _robust_background(values)

    saturation_percent = None
    low_clipping_percent = None
    high_clipping_percent = None
    if representable is not None:
        floor, ceiling = representable
        span = ceiling - floor
        if np.isfinite(span) and span > 0:
            high_threshold = floor + saturation_fraction * span
            low_threshold = floor + 0.01 * span
            saturation_percent = float(
                100.0 * np.count_nonzero(values >= high_threshold) / values.size
            )
            low_clipping_percent = float(
                100.0 * np.count_nonzero(values <= low_threshold) / values.size
            )
            high_clipping_percent = saturation_percent

    peak_y, peak_x = _local_maxima(data, background + star_detection_sigma * noise_sigma)
    if representable is not None:
        floor, ceiling = representable
        span = ceiling - floor
        if np.isfinite(span) and span > 0:
            below_saturation = data[peak_y, peak_x] < floor + saturation_fraction * span
            peak_y = peak_y[below_saturation]
            peak_x = peak_x[below_saturation]
    peaks = _select_separated_peaks(data, peak_y, peak_x)
    shapes = [
        shape for y, x in peaks if (shape := _measure_star(data, y, x, noise_sigma)) is not None
    ]
    hfr = float(np.median([shape.hfr for shape in shapes])) if shapes else None
    fwhm = float(np.median([shape.fwhm for shape in shapes])) if shapes else None
    ellipticity = float(np.median([shape.ellipticity for shape in shapes])) if shapes else None
    trailing_score = None
    if len(shapes) >= 3:
        orientation_vectors = np.exp(
            2j * np.array([shape.orientation_radians for shape in shapes], dtype=float)
        )
        orientation_coherence = float(abs(np.mean(orientation_vectors)))
        trailing_score = float((ellipticity or 0.0) * orientation_coherence)

    hot_threshold = background + 8.0 * noise_sigma
    hot_y, hot_x = _local_maxima(data, hot_threshold)
    hot_pixels = 0
    for y, x in zip(hot_y, hot_x, strict=True):
        patch = data[y - 1 : y + 2, x - 1 : x + 2]
        neighbors = np.delete(patch.ravel(), 4)
        if np.count_nonzero(neighbors > background + 3.0 * noise_sigma) <= 1:
            hot_pixels += 1

    return PixelAnalysis(
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        valid_pixels=int(values.size),
        noise_sigma=float(noise_sigma),
        saturation_percent=saturation_percent,
        low_clipping_percent=low_clipping_percent,
        high_clipping_percent=high_clipping_percent,
        detected_stars=len(shapes),
        hfr=hfr,
        fwhm=fwhm,
        ellipticity=ellipticity,
        trailing_score=trailing_score,
        background_gradient_percent=_gradient_percent(data, background, noise_sigma),
        hot_pixel_count=hot_pixels,
        signal_span_sigma=float(
            (np.percentile(values, 99.5) - background) / max(noise_sigma, np.finfo(float).eps)
        ),
    )
