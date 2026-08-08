from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "fits" / "controlled_images.json"


def controlled_image_recipe(name: str) -> dict[str, Any]:
    scenarios = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return scenarios[name]


def write_controlled_fits(destination: Path, recipe: dict[str, Any]) -> np.ndarray:
    width = int(recipe["width"])
    height = int(recipe["height"])
    rng = np.random.default_rng(int(recipe["seed"]))
    data = rng.normal(
        float(recipe["background"]),
        float(recipe["noise_sigma"]),
        size=(height, width),
    )
    data += float(recipe["gradient_x"]) * np.arange(width, dtype=float)[None, :]
    yy, xx = np.indices(data.shape, dtype=float)
    for x, y, amplitude, sigma_x, sigma_y, angle in recipe["stars"]:
        dx = xx - float(x)
        dy = yy - float(y)
        cosine = np.cos(float(angle))
        sine = np.sin(float(angle))
        major = cosine * dx + sine * dy
        minor = -sine * dx + cosine * dy
        data += float(amplitude) * np.exp(
            -0.5 * ((major / float(sigma_x)) ** 2 + (minor / float(sigma_y)) ** 2)
        )
    for x, y in recipe["hot_pixels"]:
        data[int(y), int(x)] = 60000.0
    rectangle = recipe.get("saturated_rectangle")
    if rectangle:
        x0, y0, x1, y1 = (int(value) for value in rectangle)
        data[y0:y1, x0:x1] = 65535.0

    if recipe["dtype"] == "uint16":
        output = np.rint(np.clip(data, 0, 65535)).astype(np.uint16)
    else:
        output = data.astype(np.float32)
    hdu = fits.PrimaryHDU(output)
    for key, value in recipe["header"].items():
        hdu.header[key] = value
    hdu.writeto(destination, overwrite=False, checksum=True)
    return output
