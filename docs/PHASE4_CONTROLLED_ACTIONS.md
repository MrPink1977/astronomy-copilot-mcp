# Phase 4 Controlled Actions and Approval Enforcement

## Scope

Phase 4 adds a reviewed write surface to the curated MCP while preserving the raw 179-tool
compatibility server unchanged. The new tools are:

| Tool | Level | Controlled effect |
|---|---:|---|
| `connect_observatory` | 1 | Connect selected configured camera, mount, or guider devices |
| `capture_test_frame` | 1 | Capture exactly one exposure of at most 30 seconds |
| `plate_solve_current_frame` | 1 | Solve the current prepared image without requesting motion |
| `center_target` | 2 | Slew and plate-solve center the mount at bounded coordinates |
| `start_guiding` | 1/2 | Start guiding; calibration requires a Level 2 plan |
| `start_existing_sequence` | 2 | Start the validated loaded sequence, which may contain motion |
| `stop_sequence_safely` | 3 | Stop the running sequence |
| `park_observatory` | 3 | Park the connected mount at its configured park position |
| `get_action_audit` | 0 | Read the bounded action-attempt audit log |

The verified Advanced API exposes sequence start and stop but no pause route. Phase 4 therefore
does not invent a pause operation or approximate it with sequence skipping.

The reviewed routes match the Advanced API source for
[`Connection.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Connection.cs),
[`Camera.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Camera.cs),
[`Mount.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Mount.cs),
[`Guider.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Guider.cs),
[`Image.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Application/Image.cs),
and
[`Sequence.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Application/Sequence.cs).

## Server-enforced policy

Every action input defaults to `dry_run=true`. A dry run performs no NINA request and returns the
exact proposed effect. Setting `dry_run=false` is insufficient by itself: all writes also require
`approved=true`.

Level 2 physical motion and Level 3 session-ending operations add a stronger boundary:

1. Call the tool in dry-run mode with the exact action parameters.
2. Review the returned short-lived `approval_plan`.
3. Call the same tool with unchanged action parameters, `dry_run=false`, `approved=true`, and its
   `approval_plan_id`.

Plans expire after two minutes and are single-use. Unknown, expired, reused, wrong-action, or
parameter-altered plans are rejected before any NINA request. Approval state is held in memory, so
a server restart invalidates every outstanding plan.

Level 1 actions accept an optional idempotency key. A successful repeated request with the same
action, parameters, and key sends no second write. Reusing a key with altered parameters is
rejected. Connect and park also inspect current telemetry and skip writes when the requested state
is already satisfied.

## Bounds, timeouts, and cancellation

- Test exposures must be greater than zero and no longer than 30 seconds.
- Gain is optional and limited to `0..1000`.
- Center coordinates are limited to RA `0..<24` hours and Dec `-90..90` degrees.
- Action timeouts are limited to `0.05..600` seconds.
- The service makes one execution attempt; it never automatically repeats a physical or
  session-ending write.
- A timed-out capture, center, guiding start, or sequence start triggers its reviewed abort/stop
  endpoint once. The result reports whether that cancellation request was sent.

## Audit behavior

Every dry run, rejection, execution, idempotent replay, failure, and timeout produces a sanitized
audit event. Events include the action, level, status, timestamp, parameter hash, approval plan ID,
and bounded summary. The in-memory log retains the latest 200 events and returns at most 100; it is
an action-policy audit, not the persistent session timeline planned for Phase 5.

## Testing and hardware boundary

Unit, MCP contract, and mock HTTP integration tests cover the complete Phase 4 gate. Dry-run tests
assert that no request reaches even the loopback mock. Motion and session-ending execution tests
use only sanitized mock responses in CI.

Hosted CI excludes the `hardware` marker. Local hardware tests require both
`ALLOW_HARDWARE_TESTS=true` and `ALLOW_PHYSICAL_MOTION=true`; neither flag bypasses an approval
plan.

## Phase boundary

Phase 5 session states, websocket reconciliation, persistent timelines, restart reconciliation, and
state-transition command guards are not implemented here. No autonomous workflow, scheduling,
hardware acceptance run, or merge is part of Phase 4.
