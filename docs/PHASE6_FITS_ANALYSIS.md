# Phase 6: Local FITS and Image-Quality Analysis

Phase 6 exposes one additional reviewed tool, `analyze_fits_image`. It accepts a path to one local,
uncompressed `.fit`, `.fits`, or `.fts` file and opens it read-only. The response contains only
normalized scalar evidence; the original image is not modified, uploaded, or transmitted.

## Evidence contract

Every metadata field and measurement reports:

- `state`: `AVAILABLE` or `UNAVAILABLE`;
- `value` and `unit`;
- the measurement `method`;
- any applicable `threshold`;
- method-specific `limitations`.

Quality indicators separately report `DETECTED`, `NOT_DETECTED`, or `UNAVAILABLE`. In particular,
missing FITS keywords, a floating-point image without `SATURATE` or `DATAMAX`, and a frame without
enough measurable point-source candidates are unavailable evidence rather than zero-valued or
negative findings.

## Measurements and defaults

| Evidence | Method | Reviewed threshold or interpretation |
|---|---|---|
| Dimensions and bit depth | FITS shape and `BITPIX` | Metadata only |
| Exposure, gain, temperature, filter | Reviewed FITS keyword lookup | Missing keyword is unavailable |
| Min, max, mean, median | All finite pixels in selected 2-D HDU | ADU |
| Saturation | Pixels above 98% of integer/header range | Indicator at 1% of valid pixels |
| Clipping | Lowest 1% and saturation-range fractions | Indicator at 1% on either boundary |
| Detected-star count | Local maxima above median plus five robust sigma | Candidates, not confirmed stars |
| HFR/FWHM | Background-subtracted 9x9 candidate flux/moments | Approximate pixels |
| Ellipticity | Candidate covariance eigenvalues | 0 round to 1 elongated |
| Likely trailing | Ellipticity times common-orientation coherence | Score at least 0.21, three candidates |
| Background gradient | Plane over 8x8 block medians | Severe at 20% of median background |
| Hot pixels | Isolated peaks above eight robust sigma | Elevated above max(10, 0.01% of pixels) |
| Low usable signal | 99.5th-percentile span and candidate count | Below five sigma with zero candidates |

These are screening indicators. They do not by themselves confirm a hardware fault, a lens cap,
tracking error, or focus error. Instrument calibration, plate scale, seeing, Bayer layout, extended
targets, and multi-frame persistence are outside these single-frame estimates.

## Controlled fixtures and validation

`tests/fixtures/fits/controlled_images.json` defines deterministic small FITS image recipes for a
round-star field with hot pixels, aligned elongated candidates, saturation plus a gradient, and a
floating-point low-signal frame. Tests materialize those images only inside pytest temporary
directories and validate measurements with explicit tolerances. SHA-256 and modification-time
checks verify that analysis preserves the source file.

Run the Phase 6 hardware-free gate:

```powershell
uv sync --locked --all-groups --python 3.11
uv run ruff check .
uv run ruff format --check .
uv run pytest -m unit
uv run pytest -m contract
uv run pytest -m integration
uv run pytest -m "not hardware"
```

Phase 6 does not compose imaging workflows or issue hardware actions. That remains the separate
Phase 7 gate.
