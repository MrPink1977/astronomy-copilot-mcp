from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp


class NinaUnavailableError(RuntimeError):
    """NINA cannot be reached within the configured deadline."""


class NinaResponseError(RuntimeError):
    """NINA returned an unsuccessful or malformed response."""


class NinaActionTimeoutError(NinaUnavailableError):
    """A controlled NINA action exceeded its server-enforced deadline."""


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
    SESSION_ENDPOINTS = {
        "sequence": "sequence/state",
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 1888, timeout_seconds: float = 5.0):
        self.base_url = f"http://{host}:{port}/v2/api"
        self.timeout_seconds = timeout_seconds

    async def _get(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
    ) -> Any:
        encoded_params = {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in (params or {}).items()
        }
        try:
            async with session.get(
                f"{self.base_url}/{endpoint}", params=encoded_params
            ) as response:
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

    @staticmethod
    def _value(mapping: Any, name: str) -> Any:
        if not isinstance(mapping, dict):
            return None
        for key, value in mapping.items():
            if str(key).casefold() == name.casefold():
                return value
        return None

    @classmethod
    def _configuration_from_profile(cls, profile: Any) -> dict[str, Any]:
        if not isinstance(profile, dict):
            raise NinaResponseError("profile/show returned malformed active-profile data")

        safety_settings = cls._value(profile, "SafetyMonitorSettings")
        safety_id = cls._value(safety_settings, "Id")
        if not isinstance(safety_id, str) or not safety_id.strip():
            raise NinaResponseError("profile/show omitted safety-monitor configuration")
        safety_configured = safety_id.strip().casefold() != "no_device"

        plate_settings = cls._value(profile, "PlateSolveSettings")
        plate_solver = cls._value(plate_settings, "PlateSolverType")
        blind_solver = cls._value(plate_settings, "BlindSolverType")
        plate_configured = isinstance(plate_solver, str) and bool(plate_solver.strip())
        telescope_settings = cls._value(profile, "TelescopeSettings")

        return {
            "safety_monitor": {
                "Configured": safety_configured,
                "ConfigurationState": "configured" if safety_configured else "not_configured",
            },
            "plate_solving": {
                "Configured": plate_configured,
                "PlateSolverType": plate_solver,
                "BlindSolverType": blind_solver,
                "ExposureTime": cls._value(plate_settings, "ExposureTime"),
                "Binning": cls._value(plate_settings, "Binning"),
                "FocalLength": cls._value(telescope_settings, "FocalLength"),
                "Source": "active_profile",
            },
        }

    async def _get_snapshot(
        self,
        *,
        include_diagnostics: bool,
        include_session: bool = False,
    ) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            version = await self._get(session, "version")
            if not isinstance(version, str) or not version.strip():
                raise NinaResponseError("version returned a malformed response")

            async def read_component(
                name: str,
                endpoint: str,
                *,
                params: dict[str, str | int | float | bool] | None = None,
            ) -> tuple[str, Any]:
                try:
                    return name, await self._get(session, endpoint, params=params)
                except NinaResponseError as exc:
                    return name, exc

            equipment_results = await asyncio.gather(
                *(
                    read_component(name, endpoint)
                    for name, endpoint in self.EQUIPMENT_ENDPOINTS.items()
                )
            )
            snapshot = {"version": version, "equipment": dict(equipment_results)}
            if include_diagnostics:
                _, active_profile = await read_component(
                    "active_profile",
                    "profile/show",
                    params={"active": True},
                )
                if isinstance(active_profile, Exception):
                    configuration: dict[str, Any] | Exception = active_profile
                else:
                    try:
                        configuration = self._configuration_from_profile(active_profile)
                    except NinaResponseError as exc:
                        configuration = exc
                snapshot["configuration"] = configuration
                snapshot["diagnostics"] = {
                    "plate_solving": (
                        configuration.get("plate_solving")
                        if isinstance(configuration, dict)
                        else configuration
                    )
                }
            if include_session:
                session_results = await asyncio.gather(
                    *(
                        read_component(name, endpoint)
                        for name, endpoint in self.SESSION_ENDPOINTS.items()
                    )
                )
                snapshot["session"] = dict(session_results)
            snapshot["observed_at"] = datetime.now(timezone.utc).isoformat()
        return snapshot

    async def get_snapshot(self) -> dict[str, Any]:
        return await self._get_snapshot(include_diagnostics=False)

    async def get_diagnostic_snapshot(self) -> dict[str, Any]:
        """Return status plus reviewed read-only telemetry used by Phase 3 rules."""
        return await self._get_snapshot(include_diagnostics=True)

    async def get_session_snapshot(self) -> dict[str, Any]:
        """Return the full reviewed snapshot used to reconcile Phase 5 state."""
        return await self._get_snapshot(include_diagnostics=True, include_session=True)


class NinaActionAdapter(NinaReadOnlyAdapter):
    """Reviewed Phase 4 action endpoints kept separate from status reads."""

    CANCEL_ENDPOINTS = {
        "capture_test_frame": "equipment/camera/abort-exposure",
        "center_target": "equipment/mount/slew/stop",
        "start_guiding": "equipment/guider/stop",
        "start_existing_sequence": "sequence/stop",
    }

    async def execute(
        self,
        endpoint: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        timeout_seconds: float,
    ) -> Any:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        encoded_params = {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in (params or {}).items()
        }
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/{endpoint}", params=encoded_params
                ) as response:
                    if response.status != 200:
                        raise NinaResponseError(f"{endpoint} returned HTTP {response.status}")
                    payload = await response.json()
        except asyncio.TimeoutError as exc:
            raise NinaActionTimeoutError(f"{endpoint} exceeded its action timeout") from exc
        except (aiohttp.ContentTypeError, ValueError) as exc:
            raise NinaResponseError(f"{endpoint} returned invalid JSON") from exc
        except aiohttp.ClientError as exc:
            raise NinaUnavailableError("NINA Advanced API is unavailable") from exc

        if not isinstance(payload, dict) or payload.get("Success") is not True:
            raise NinaResponseError(f"{endpoint} returned an unsuccessful response")
        return payload.get("Response")

    async def get_equipment_info(
        self,
        component: str,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        response = await self.execute(
            f"equipment/{component}/info",
            timeout_seconds=timeout_seconds,
        )
        if not isinstance(response, dict):
            raise NinaResponseError(f"equipment/{component}/info returned malformed telemetry")
        return response

    async def cancel(self, action: str) -> bool:
        endpoint = self.CANCEL_ENDPOINTS.get(action)
        if endpoint is None:
            return False
        try:
            await self.execute(endpoint, timeout_seconds=5.0)
        except (NinaUnavailableError, NinaResponseError):
            return False
        return True
