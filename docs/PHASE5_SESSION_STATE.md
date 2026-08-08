# Phase 5: Session State and Event Timeline

Phase 5 adds a curated, in-memory state machine without changing the raw 179-tool
compatibility server. It models the planned 13 session states and exposes one new
read-only MCP tool, `get_session_timeline`.

## Authority and reconciliation

- NINA websocket events provide responsive transition hints.
- A full reviewed HTTP snapshot is authoritative at process start and after websocket
  reconnects.
- Consecutive duplicate websocket payloads are ignored by content identity.
- A snapshot can recover a transition whose event was missed.
- Internally contradictory telemetry produces `ERROR` rather than a safety claim.
- A new process starts in non-authoritative `STARTING`. It cannot inherit a prior
  process's `SAFE` state, and `SAFE` requires positive parked, inactive-camera, inactive-
  sequence telemetry.

The timeline retains at most 500 events by default. Consumers poll with a cursor and a
limit of 1-100. `history_gap=true` explicitly reports that the requested cursor predates
the retained history.

## Command guards

Approved writes reconcile an authoritative snapshot before consuming a motion approval.
Rules are deterministic and separate from endpoint handlers. Among the Phase 5 gates:

- parking while slewing, centering, or already parking is rejected;
- starting a second active sequence is rejected;
- guiding cannot start without a connected guider;
- busy camera, mount, and sequence combinations reject conflicting operations.

Dry runs remain network- and hardware-free. A state rejection is audited and does not
consume a single-use approval plan.

## Local gate

```powershell
uv sync --locked --all-groups --python 3.11
uv run ruff check .
uv run ruff format --check .
uv run pytest -m unit
uv run pytest -m contract
uv run pytest -m integration
uv run pytest -m "not hardware"
```

The mock suite covers HTTP snapshot reconciliation, real loopback websocket delivery,
disconnect/reconnect behavior, missing and duplicate events, contradictory telemetry,
restart safety, bounded history, and command rejection. It requires no live NINA or
observatory hardware.
