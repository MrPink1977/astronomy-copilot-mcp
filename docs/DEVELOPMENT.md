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

All default tests use in-memory data or a loopback mock HTTP server. They do not require NINA,
observatory hardware, external network access, secrets, or a local `.env` file.

## Running the MCP servers

Run the curated server (read tools plus dry-run-by-default controlled actions):

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
