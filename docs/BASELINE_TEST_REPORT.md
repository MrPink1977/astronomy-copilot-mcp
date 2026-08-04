# Baseline Test Report

Date: 2026-08-04

Baseline commit: `5c94276c84b71f4821df167270b6f2a441a15dd9`

Scope: upstream behavior only. No production source files were modified.

## Environment

| Item | Observed value |
|---|---|
| Operating system | Windows |
| Repository branch | `agent/phase-0-baseline` |
| Python | 3.11.11 in `.venv` |
| uv | 0.9.17 |
| FastMCP | 3.4.5 |
| NINA host | `localhost` |
| NINA port | `1888` |
| NINA version | Not available; NINA API was offline |
| Advanced API version | Not available; NINA API was offline |
| Equipment profile | Not available; NINA API was offline |
| Equipment inventory | Not available; NINA API was offline |

The exact dependency resolution is recorded in `docs/BASELINE_DEPENDENCIES.txt`.

## Installation

Commands used:

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
uv pip install --python .venv\Scripts\python.exe requests
```

`requests` had to be installed separately because `nina_advanced_mcp.py` imports it but upstream `requirements.txt` does not declare it. The upstream README launch example does include `requests`.

## Automated test results

### Isolated automated suite

```text
54 passed in 1.08s
```

Command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

### Full repository discovery

```text
1 failed, 54 passed in 1.56s
FAILED test_weather.py::test_weather_endpoints
async def functions are not natively supported
```

`test_weather.py` is a manually runnable live-network script with a hard-coded private address, but its name causes pytest to collect it. It has no pytest marker or fixture isolation. It should be moved out of automated discovery or explicitly marked as a hardware/live integration test in a later phase.

## MCP smoke test

An in-process FastMCP client completed the MCP handshake and listed tools successfully:

```text
mcp_handshake=ok
mcp_client_tools=179
```

Runtime registration emitted warnings for duplicate tool names:

```text
Component already exists: tool:nina_get_version@
Component already exists: tool:nina_get_image_history@
```

Static inspection found 181 decorated definitions and 179 unique names. Later definitions replace earlier ones in the tested FastMCP version.

## NINA connectivity

Read-only check:

```powershell
curl.exe --max-time 3 http://localhost:1888/v2/api/version
```

Observed result:

```text
curl: (7) Failed to connect to localhost:1888: Could not connect to server
```

Because NINA or its Advanced API was not listening, no live status, equipment, image, plate-solving, guiding, sequence, or event calls were attempted. No equipment-changing request was sent.

## Baseline findings

1. The isolated automated suite is healthy: 54 tests pass.
2. Full pytest discovery is not clean because a live weather script is collected as a test.
3. The declared requirements are incomplete: `requests` is required at import time.
4. Broad unpinned dependency ranges resolve to 89 packages and should be locked after the unchanged baseline is preserved.
5. FastMCP 3.4.5 can import the server and complete a client handshake.
6. The effective public surface is 179 tools, not the README badge's 176.
7. Duplicate definitions make two effective handlers dependent on source order.
8. Live hardware validation remains pending until NINA and Advanced API are running locally.

## Remaining Phase 1 live checklist

Run these only with NINA open and the intended profile loaded:

- Record NINA and Advanced API versions.
- Record the active profile and connected equipment.
- Call version, overall status, camera info, mount info, guider info, sequence JSON/state, safety monitor, and weather status.
- Confirm no read operation moves or reconfigures equipment.
- With the rig in a safe state and user approval, connect the camera.
- With a covered or otherwise safe optical setup and user approval, capture one short test exposure.
- Record exact responses, saved-file behavior, and errors.

The baseline branch and preservation tag are published. The baseline remains incomplete only for this live NINA checklist.
