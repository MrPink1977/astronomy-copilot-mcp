# Development Guide

## Supported environment

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) 0.9 or newer

The committed `uv.lock` is the authoritative dependency resolution for development and CI.
`requirements.txt` remains as an unlocked runtime-only compatibility path for existing pip users.

## Reproducible setup

From the repository root:

```powershell
uv sync --locked --all-groups
```

On macOS or Linux, the same command applies.

To prove that the lockfile is current without changing it:

```powershell
uv lock --check
```

## Validation commands

The complete hardware-free validation is:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest -m unit
uv run pytest -m contract
uv run pytest -m integration
uv run pytest -m "not hardware"
```

All default tests use in-memory data or a loopback mock HTTP/websocket server. They do not require NINA,
observatory hardware, external network access, secrets, or a local `.env` file.

## Running the MCP servers

Run the curated server (read tools, local FITS analysis, and dry-run-by-default controlled actions):

```powershell
uv run python -m astronomy_copilot.server
```

The upstream compatibility server remains available separately:

```powershell
uv run python nina_advanced_mcp.py
```

The compatibility server retains upstream import/startup behavior and should only be launched when
live NINA access is intended. Automated validation inspects it without importing it into the test
process.

## Manual weather probe

`test_weather.py` is retained as an explicitly invoked, read-only diagnostic script. It is not part
of pytest discovery and requires an explicit base URL:

```powershell
uv run python test_weather.py --base-url http://127.0.0.1:1888/v2/api
```

Do not use manual probes as CI evidence. Record any approved live checks separately in the baseline
or hardware-acceptance report.

## Hardware test gate

Hosted CI always excludes the `hardware` marker. A local hardware test is eligible to run only
when both independent opt-ins are set:

```powershell
$env:ALLOW_HARDWARE_TESTS="true"
$env:ALLOW_PHYSICAL_MOTION="true"
uv run pytest -m hardware
```

The flags enable test selection; they are not approval-plan IDs and do not bypass the server's
Phase 4 approval policy. Keep them unset during routine development.

The Phase 7 live pre-motion acceptance harness requires a third opt-in plus an explicit target:

```powershell
$env:ALLOW_PHASE7_WORKFLOW="true"
$env:PHASE7_TARGET_NAME="Approved daylight target"
$env:PHASE7_RA_HOURS="10.0"
$env:PHASE7_DEC_DEGREES="20.0"
uv run pytest tests/hardware_integration/test_phase7_workflow_gate.py -m hardware
```

This harness may connect configured equipment, capture at most three three-second frames, and plate
solve. After a failed solve it waits five minutes and reruns the complete preflight before another
attempt. It must stop at the Level 2 centering approval boundary; the flags are not a centering plan
ID. A failed or malformed nested solve result cannot create that plan.

If and only if the active NINA profile has no configured Safety Monitor, add a fresh, explicit
operator attestation immediately before running the harness:

```powershell
$env:PHASE7_OPERATOR_SAFETY_ATTESTATION="OPERATOR_CONFIRMS_SAFE"
$env:PHASE7_OPERATOR_SAFETY_ATTESTED_AT=(Get-Date).ToUniversalTime().ToString("o")
```

The server accepts this attestation for at most five minutes. It is rejected when a monitor is
configured but disconnected, and it can never override a connected monitor reporting unsafe.
The retry delay does not extend the attestation. On a rig with no configured monitor, expiry during
the delay stops before the next capture and requires a fresh attestation and newly authorized run.
