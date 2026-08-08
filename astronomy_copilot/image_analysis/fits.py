from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

MAX_FITS_BYTES = 128 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
FITS_EXTENSIONS = {".fit", ".fits", ".fts"}


class FitsUnavailableError(RuntimeError):
    """The requested local FITS evidence cannot be safely read."""


@dataclass(frozen=True, slots=True)
class LoadedFits:
    path: Path
    hdu_index: int
    data: np.ndarray
    header: fits.Header
    shape: tuple[int, ...]
    bitpix: int | None


def _select_hdu(hdul: fits.HDUList, requested_index: int | None) -> int:
    if requested_index is not None:
        if requested_index >= len(hdul):
            raise FitsUnavailableError("The requested FITS HDU does not exist.")
        if hdul[requested_index].data is None:
            raise FitsUnavailableError("The requested FITS HDU has no image data.")
        return requested_index
    for index, hdu in enumerate(hdul):
        if hdu.data is not None and getattr(hdu.data, "ndim", 0) >= 2:
            return index
    raise FitsUnavailableError("The FITS file contains no image HDU.")


def load_fits_read_only(file_path: str, hdu_index: int | None = None) -> LoadedFits:
    path = Path(file_path).expanduser()
    try:
        path = path.resolve(strict=True)
        stat = path.stat()
    except (OSError, RuntimeError) as exc:
        raise FitsUnavailableError("The local FITS file is unavailable.") from exc
    if not path.is_file():
        raise FitsUnavailableError("The local FITS path is not a regular file.")
    if path.suffix.casefold() not in FITS_EXTENSIONS:
        raise FitsUnavailableError("Only uncompressed .fit, .fits, and .fts files are supported.")
    if stat.st_size > MAX_FITS_BYTES:
        raise FitsUnavailableError("The FITS file exceeds the 128 MiB analysis limit.")

    try:
        with fits.open(
            path,
            mode="readonly",
            memmap=False,
            lazy_load_hdus=False,
            ignore_missing_simple=False,
        ) as hdul:
            selected = _select_hdu(hdul, hdu_index)
            hdu = hdul[selected]
            header = hdu.header.copy()
            raw = np.asarray(hdu.data)
            shape = tuple(int(size) for size in raw.shape)
            if raw.size > MAX_IMAGE_PIXELS:
                raise FitsUnavailableError("The FITS image exceeds the 50-million-pixel limit.")
            try:
                data = np.asarray(raw, dtype=np.float64)
            except (TypeError, ValueError, MemoryError) as exc:
                raise FitsUnavailableError(
                    "The FITS image pixels could not be normalized."
                ) from exc
    except FitsUnavailableError:
        raise
    except (OSError, ValueError, TypeError, MemoryError) as exc:
        raise FitsUnavailableError("The local file is not a readable FITS image.") from exc

    bitpix_value: Any = header.get("BITPIX")
    bitpix = int(bitpix_value) if isinstance(bitpix_value, (int, np.integer)) else None
    return LoadedFits(path, selected, data, header, shape, bitpix)


def header_value(header: fits.Header, keys: tuple[str, ...]) -> str | int | float | None:
    for key in keys:
        value = header.get(key)
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and not np.isfinite(value):
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            return value
    return None


def representable_range(header: fits.Header, bitpix: int | None) -> tuple[float, float] | None:
    saturation = header_value(header, ("SATURATE", "DATAMAX"))
    floor = header_value(header, ("DATAMIN",))
    if isinstance(saturation, (int, float)) and float(saturation) > 0:
        return float(floor or 0.0), float(saturation)
    if bitpix is None or bitpix <= 0 or bitpix > 64:
        return None
    bscale = float(header.get("BSCALE", 1.0))
    bzero = float(header.get("BZERO", 0.0))
    raw_floor = -(2 ** (bitpix - 1))
    raw_ceiling = 2 ** (bitpix - 1) - 1
    return raw_floor * bscale + bzero, raw_ceiling * bscale + bzero
