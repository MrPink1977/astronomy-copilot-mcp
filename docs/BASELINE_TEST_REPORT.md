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
| NINA host | `127.0.0.1` |
| NINA port | `1888` |
| NINA version | Not available through this API version |
| Advanced API version | 2.2.11.1 |
| Equipment profile | `NEWForTOMIE` |
| Configured camera | ZWO ASI224MC |
| Configured mount | ASCOM iOptron 2017 telescope driver |
| Configured focuser | ASCOM Celestron USB Motor Focuser |
| Configured guider | PHD2 Single |
| Configured plate solver | ASTAP |

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

The API became available later on 2026-08-04. Read-only check:

```powershell
curl.exe --max-time 3 http://127.0.0.1:1888/v2/api/version
```

Observed result:

```text
HTTP 200
{"Response":"2.2.11.1","StatusCode":200,"Success":true,"Type":"API"}
```

The root `/v2/api` endpoint also returned HTTP 200. The installed API is older than the upstream README's stated requirement of Advanced API 2.2.13 or later.

## Live read-only MCP validation

An in-process FastMCP client connected to the live API and called the raw read tools. No equipment-changing request was sent.

| Tool | Result |
|---|---|
| `nina_connect` | Connected the software HTTP client to `127.0.0.1:1888`; this did not connect hardware |
| `nina_get_version` | Failed because `/v2/api/application/version` returned HTTP 404 |
| `nina_show_profile(active=true)` | Loaded the intended `NEWForTOMIE` profile and configured device identifiers |
| `nina_get_status` | Succeeded; all ten equipment categories were disconnected |
| `nina_get_camera_info` | Succeeded; camera disconnected |
| `nina_get_mount_info` | Succeeded; mount disconnected |
| `nina_get_guider_info` | Succeeded; guider disconnected |
| `nina_get_safetymonitor_info` | Succeeded; monitor disconnected and raw wrapper reported `UNSAFE` |
| `nina_get_weather_info` | Succeeded; weather device disconnected and measurements unavailable |
| `nina_sequence_json` | Succeeded; start, targets, and end containers were `CREATED` with zero items |
| `nina_sequence_state` | Succeeded; same empty/created sequence state |
| `nina_disconnect` | Closed the MCP software HTTP session |

The Advanced API `application/plugins` endpoint listed Advanced API, BahtiFocus, Ground Station, Hocus Focus, Phd2 Tools, PixInsight Tools, Point3D, Scope Control, Three Point Polar Alignment, and Touch 'N' Stars. Application version/start-time/tab endpoints used by newer handlers were unavailable.

The profile response contains sensitive and observatory-specific settings, including credentials. The raw response was not written to the repository. Only the sanitized identifiers above are retained.

## Baseline findings

1. The isolated automated suite is healthy: 54 tests pass.
2. Full pytest discovery is not clean because a live weather script is collected as a test.
3. The declared requirements are incomplete: `requests` is required at import time.
4. Broad unpinned dependency ranges resolve to 89 packages and should be locked after the unchanged baseline is preserved.
5. FastMCP 3.4.5 can import the server and complete a client handshake.
6. The effective public surface is 179 tools, not the README badge's 176.
7. Duplicate definitions make two effective handlers dependent on source order.
8. The installed Advanced API 2.2.11.1 is below upstream's stated 2.2.13 minimum and lacks endpoints used by effective runtime handlers.
9. `nina_get_version` is broken on this installation because the later duplicate handler replaces the compatible `/version` handler and calls unavailable `/application/version`.
10. `nina_get_status` reports “1 devices connected” when all equipment is disconnected because it includes the MCP server connection in the count.
11. A disconnected safety monitor is rendered as `UNSAFE`; the Copilot layer must distinguish `UNKNOWN` or `UNAVAILABLE` from an authoritative unsafe reading.
12. Profile reads require mandatory sanitization before logging, fixture capture, or model exposure.

## Remaining Phase 1 live checklist

The read-only checklist is complete. Remaining controlled writes:

- Prefer upgrading the Advanced API plugin to 2.2.13 or later, then rerun the read-only compatibility check.
- With the rig in a safe state and user approval, connect the camera.
- With a covered or otherwise safe optical setup and user approval, capture one short test exposure.
- Record exact responses, saved-file behavior, and errors.

The baseline branch and preservation tag are published. The baseline remains incomplete only for the controlled camera connection and test exposure.
