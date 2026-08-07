# Architecture map

This file is a compact orientation guide for maintainers and coding agents. It is intentionally shorter than the README.

## Runtime flow

```text
MCP client
   |
   | stdio / MCP
   v
nina_advanced_mcp.py
   |
   | HTTP REST
   v
NINA Advanced API (:1888 by default)
   |
   v
NINA devices and imaging workflows
```

Optional support paths:

```text
nina_advanced_mcp.py
   +--> ts_db.py   --> Target Scheduler SQLite database (read-only)
   +--> events.py  --> NINA event websocket --> bounded in-memory event store
   +--> alerter.py --> human alert channel
```

## Main components

### `nina_advanced_mcp.py`

Primary MCP server. It contains:

- environment/config loading;
- the shared NINA HTTP client;
- error response helpers;
- Pydantic input models;
- MCP tool registrations covering NINA Advanced API operations;
- integration hooks for scheduler, events, and alerts.

This file is intentionally treated as legacy/monolithic code for now. Avoid broad decomposition during unrelated feature or bug-fix work because a large refactor creates unnecessary regression risk and consumes significant agent context.

### `ts_db.py`

Read-only access to the NINA Target Scheduler plugin SQLite database. Changes here should preserve read-only behavior and should be tested with the synthetic SQLite fixtures in `tests/`.

### `events.py`

Maintains a background subscription to NINA events and stores recent events behind a monotonic cursor. Tests should cover reconnect/buffering behavior without requiring a live observatory.

### `alerter.py`

Human notification support. Automated tests should mock network delivery and must not send real alerts.

### `nina_help.json`

Structured help metadata for MCP tools. Treat it as part of the public interface: tool changes may require synchronized metadata changes.

### `API_COVERAGE_ANALYSIS.md`

Reference describing Advanced API coverage. Do not change coverage counts speculatively.

## Testing layers

### Offline automated tests

Located under `tests/`. These are the default validation layer and should run without a NINA instance or observatory hardware.

```bash
pytest
```

### Live integration probes

`test_weather.py` is currently a manual live probe. It contains a concrete NINA host and performs real HTTP requests. It is deliberately excluded from normal pytest discovery by repository configuration.

Live integration tests should remain explicit and opt-in.

## Change strategy

Prefer this order:

1. Locate the existing MCP tool/client pattern.
2. Add or modify the smallest implementation surface.
3. Add an offline regression test where practical.
4. Run the narrow test.
5. Run the full offline suite.
6. Update help/coverage/README only when behavior or public usage changed.
7. Perform live-NINA validation only when specifically requested.
