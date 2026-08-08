"""Explicitly invoked, read-only NINA weather diagnostic.

This module intentionally contains no pytest tests and performs no work when imported. Normal test
discovery is restricted to ``tests/``; running this file requires an explicit NINA base URL.
"""

from __future__ import annotations

import argparse
import asyncio
import json

import aiohttp

READ_ONLY_ENDPOINTS = (
    "equipment/weather/info",
    "equipment/weather/list-devices",
)


async def probe_weather_endpoints(base_url: str) -> int:
    """Print read-only weather responses from an explicitly selected NINA server."""
    failures = 0
    async with aiohttp.ClientSession() as session:
        for endpoint in READ_ONLY_ENDPOINTS:
            print(f"GET {endpoint}")
            try:
                async with session.get(f"{base_url.rstrip('/')}/{endpoint}") as response:
                    print(f"Status: {response.status}")
                    data = await response.json()
                    print(json.dumps(data, indent=2))
                    failures += response.status != 200
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                failures += 1
                print(f"Error: {exc}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        required=True,
        help="Explicit NINA API root, for example http://127.0.0.1:1888/v2/api",
    )
    args = parser.parse_args()
    return asyncio.run(probe_weather_endpoints(args.base_url))


if __name__ == "__main__":
    raise SystemExit(main())
