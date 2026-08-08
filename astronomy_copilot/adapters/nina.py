from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class NinaUnavailableError(RuntimeError):
    """NINA cannot be reached within the configured deadline."""


class NinaResponseError(RuntimeError):
    """NINA returned an unsuccessful or malformed response."""


class NinaReadOnlyAdapter:
    """Small NINA adapter containing only reviewed, read-only endpoints."""

    EQUIPMENT_ENDPOINTS = {
        "camera": "equipment/camera/info",
        "mount": "equipment/mount/info",
        "focuser": "equipment/focuser/info",
        "filter_wheel": "equipment/filterwheel/info",
        "guider": "equipment/guider/info",
        "dome": "equipment/dome/info",
        "flat_panel": "equipment/flatdevice/info",
        "safety_monitor": "equipment/safetymonitor/info",
        "weather": "equipment/weather/info",
        "switch": "equipment/switch/info",
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 1888, timeout_seconds: float = 5.0):
        self.base_url = f"http://{host}:{port}/v2/api"
        self.timeout_seconds = timeout_seconds

    async def _get(self, session: aiohttp.ClientSession, endpoint: str) -> Any:
        try:
            async with session.get(f"{self.base_url}/{endpoint}") as response:
                if response.status != 200:
                    raise NinaResponseError(f"{endpoint} returned HTTP {response.status}")
                payload = await response.json()
        except (aiohttp.ContentTypeError, ValueError) as exc:
            raise NinaResponseError(f"{endpoint} returned invalid JSON") from exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise NinaUnavailableError("NINA Advanced API is unavailable") from exc

        if not isinstance(payload, dict) or payload.get("Success") is not True:
            raise NinaResponseError(f"{endpoint} returned an unsuccessful response")
        return payload.get("Response")

    async def get_snapshot(self) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            version = await self._get(session, "version")
            if not isinstance(version, str) or not version.strip():
                raise NinaResponseError("version returned a malformed response")

            async def read_component(name: str, endpoint: str) -> tuple[str, Any]:
                try:
                    return name, await self._get(session, endpoint)
                except NinaResponseError as exc:
                    return name, exc

            results = await asyncio.gather(
                *(
                    read_component(name, endpoint)
                    for name, endpoint in self.EQUIPMENT_ENDPOINTS.items()
                )
            )
        return {"version": version, "equipment": dict(results)}
