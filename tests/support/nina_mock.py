from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from aiohttp import web


@dataclass(slots=True)
class MockResponse:
    """One deterministic response from the local mock NINA API."""

    payload: Any | None = None
    status: int = 200
    text: str | None = None
    content_type: str | None = None
    delay_seconds: float = 0.0


@dataclass(slots=True)
class MockRequest:
    method: str
    endpoint: str
    query: dict[str, str]


class NinaMockServer:
    """Small loopback-only HTTP server implementing configured NINA API routes."""

    def __init__(self) -> None:
        self._responses: dict[str, MockResponse] = {}
        self._response_sequences: dict[str, list[MockResponse]] = {}
        self._side_effects: dict[str, tuple[str, MockResponse]] = {}
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self.host = "127.0.0.1"
        self.port: int | None = None
        self.requests: list[str] = []
        self.request_details: list[MockRequest] = []
        self.websocket_events: list[dict[str, Any]] = []
        self.websocket_connections = 0

    def set_json(
        self,
        endpoint: str,
        payload: Any,
        *,
        status: int = 200,
        delay_seconds: float = 0.0,
    ) -> None:
        self._responses[endpoint.strip("/")] = MockResponse(
            payload=payload,
            status=status,
            delay_seconds=delay_seconds,
        )

    def set_text(
        self,
        endpoint: str,
        text: str,
        *,
        status: int = 200,
        content_type: str = "application/json",
        delay_seconds: float = 0.0,
    ) -> None:
        self._responses[endpoint.strip("/")] = MockResponse(
            status=status,
            text=text,
            content_type=content_type,
            delay_seconds=delay_seconds,
        )

    def set_scenario(self, scenario: dict[str, Any]) -> None:
        for endpoint, payload in scenario.items():
            self.set_json(endpoint, payload)

    def set_json_sequence(self, endpoint: str, payloads: list[Any]) -> None:
        if not payloads:
            raise ValueError("payloads must not be empty")
        self._response_sequences[endpoint.strip("/")] = [
            MockResponse(payload=payload) for payload in payloads
        ]

    def set_json_side_effect(
        self,
        trigger_endpoint: str,
        target_endpoint: str,
        payload: Any,
    ) -> None:
        self._side_effects[trigger_endpoint.strip("/")] = (
            target_endpoint.strip("/"),
            MockResponse(payload=payload),
        )

    def set_websocket_events(self, events: list[dict[str, Any]]) -> None:
        """Configure sanitized events sent in order on each websocket connection."""
        self.websocket_events = list(events)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/v2/api/event-websocket", self._handle_websocket)
        app.router.add_get("/v2/api/{endpoint:.*}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.host, port=0)
        await self._site.start()

        server = self._site._server
        if server is None or not server.sockets:
            raise RuntimeError("Mock NINA server did not bind a socket")
        self.port = int(server.sockets[0].getsockname()[1])

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        self.websocket_connections += 1
        for event in self.websocket_events:
            await websocket.send_json(event)
        await websocket.close()
        return websocket

    async def _handle(self, request: web.Request) -> web.Response:
        endpoint = request.match_info["endpoint"]
        self.requests.append(endpoint)
        self.request_details.append(
            MockRequest(
                method=request.method,
                endpoint=endpoint,
                query=dict(request.query),
            )
        )
        sequence = self._response_sequences.get(endpoint)
        if sequence:
            response = sequence.pop(0) if len(sequence) > 1 else sequence[0]
        else:
            response = self._responses.get(endpoint)
        if response is None:
            return web.json_response(
                {"error": f"No sanitized mock configured for {endpoint}"}, status=404
            )

        side_effect = self._side_effects.get(endpoint)
        if side_effect is not None:
            target, replacement = side_effect
            self._responses[target] = replacement

        if response.delay_seconds:
            await asyncio.sleep(response.delay_seconds)
        if response.text is not None:
            return web.Response(
                text=response.text,
                status=response.status,
                content_type=response.content_type,
            )
        return web.json_response(response.payload, status=response.status)
