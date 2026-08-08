from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from astronomy_copilot.adapters.nina import NinaUnavailableError


class NinaEventAdapter:
    """One-connection NINA websocket adapter; reconnect policy belongs to the service."""

    def __init__(self, host: str = "127.0.0.1", port: int = 1888, timeout_seconds: float = 5.0):
        self.url = f"ws://{host}:{port}/v2/api/event-websocket"
        self.timeout_seconds = timeout_seconds

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=None, connect=self.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.ws_connect(self.url, heartbeat=30.0) as websocket:
                    async for message in websocket:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            payload = message.json()
                            if isinstance(payload, dict):
                                yield payload
                        elif message.type in {
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.ERROR,
                        }:
                            break
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise NinaUnavailableError("NINA event websocket is unavailable") from exc
