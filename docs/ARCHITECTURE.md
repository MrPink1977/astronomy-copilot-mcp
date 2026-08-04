# Upstream Architecture

Baseline commit: `5c94276c84b71f4821df167270b6f2a441a15dd9`

## System context

```text
MCP client
    |
    | stdio / MCP
    v
nina_advanced_mcp.py (FastMCP server)
    |
    | HTTP JSON and image streams
    v
NINA Advanced API at /v2/api
    |
    v
NINA equipment, plugins, sequencer, and guider
```

Two additional local/external paths exist:

- `events.py` opens NINA's `/v2/api/event-websocket` and buffers events in memory.
- `ts_db.py` reads the Target Scheduler SQLite database directly in read-only mode.
- `alerter.py` sends optional Discord webhook notifications.

## Repository components

| Component | Responsibility | Baseline concerns |
|---|---|---|
| `nina_advanced_mcp.py` | Configuration, logging, FastMCP instance, API client, Pydantic inputs, and 181 decorated tool definitions | 8,161-line monolith; 179 unique names; import-time side effects |
| `events.py` | Websocket subscriber, reconnect loop, bounded in-memory event store, polling envelope | No persistence; buffer overflow can drop unseen events; no explicit gap signal |
| `ts_db.py` | Read-only Target Scheduler project/target/exposure-plan queries | Schema/version coupling; local Windows path assumption |
| `alerter.py` | Discord webhook formatting and delivery | External write; accepts file attachment path; must remain outside unattended V1 behavior |
| `nina_help.json` | Large help/catalog data | Can drift from effective runtime registration |
| `API_COVERAGE_ANALYSIS.md` | Claimed Advanced API coverage | Must be checked against the installed plugin version |
| `tests/` | Unit tests for events, scheduler DB, and alerts | No coverage of the NINA API client or most MCP tools |
| `test_weather.py` | Manual live weather probe | Accidentally collected by pytest; hard-coded private address |

## Startup and configuration

At import time, `nina_advanced_mcp.py`:

1. Loads `.env`.
2. Reads `NINA_HOST`, `NINA_PORT`, `LOG_LEVEL`, and `IMAGE_SAVE_DIR`.
3. Creates `logs/` and a file logger.
4. Initializes global server state.
5. Creates the global FastMCP server.
6. Registers decorated tools while importing the module.

This makes simple imports write a log file and emit configuration logs. Tests for future modules should avoid depending on these import-time effects.

## NINA API client layer

`NinaAPIClient` is the central HTTP adapter.

- `connect()` creates an `aiohttp.ClientSession` with a ten-second timeout and probes `/v2/api`.
- `_send_request()` builds `/v2/api/{endpoint}` URLs, sends JSON or reads image streams, validates the upstream `Success` field, and raises `NinaError` on API failures.
- Several camera helpers live directly on the client.
- Most other endpoint calls are assembled directly inside MCP tool handlers rather than represented as adapter methods.
- Many equipment-changing Advanced API operations use HTTP `GET`, so HTTP method alone cannot classify safety.

The future Copilot adapter should normalize responses and expose typed domain operations. It should not infer read/write risk from the HTTP verb.

## Tool registration and request flow

Typical flow:

```text
MCP tool call
  -> Pydantic input model
  -> get_client() / NinaAPIClient
  -> endpoint-specific handler logic
  -> Advanced API request
  -> upstream Success/Error interpretation
  -> dictionary response envelope
```

Response shapes are only partially standardized. Some tools return upstream payloads, some create custom `Details`, and some save files before returning paths.

## Event path

The first `nina_poll_events_since` call lazily starts a background subscriber. Events are appended to a ring buffer with monotonically increasing cursors. The subscriber reconnects with exponential backoff up to 60 seconds.

Important constraints for later state modeling:

- Events are lost when the MCP process restarts.
- Old events can be dropped when the buffer reaches its maximum size.
- A consumer is not explicitly told that its cursor fell behind the retained buffer.
- Reconnect does not automatically reconcile state with a complete NINA status snapshot.

The Copilot state layer must use events for responsiveness and live status snapshots for authority/reconciliation.

## Test architecture

Current tests exercise:

- Event buffer and polling behavior
- Discord alert formatting/delivery envelopes
- Target Scheduler SQLite reads and selection

Missing characterization coverage includes:

- `NinaAPIClient` request, timeout, image-stream, and error behavior
- MCP tool schemas and effective registration
- Camera, mount, guider, plate-solving, and sequence handlers
- Duplicate tool registration behavior
- Filesystem path validation and image saving
- Websocket reconnect/state reconciliation
- Safety or confirmation policy

## Safe extension boundary

The first feature should use a separate FastMCP instance in `astronomy_copilot/server.py`. The upstream `nina_advanced_mcp.py` remains the raw compatibility entrypoint.

The curated server should expose services that call a typed NINA adapter internally. Importing raw helpers is acceptable temporarily only if their global `mcp` instance is never served by the curated entrypoint. Characterization tests must cover any code moved out of the monolith before the move.

## Immediate architectural risks

1. Large monolithic module with limited regression tests.
2. Import-time filesystem and logging side effects.
3. Incomplete and unpinned dependency declarations.
4. Duplicate tool definitions and documentation/tool-count drift.
5. Raw tool surface far larger than the intended supervised product surface.
6. No server-enforced approval model.
7. Event history is transient and can silently omit dropped history.
8. Live integration script is mixed into normal pytest discovery.

These are baseline observations, not authorization for a broad refactor. They should be addressed in small, gated changes after the live baseline is completed.
