# Phase 7: Complete Supervised Imaging Workflow

`prepare_for_imaging` composes the proven status, readiness, session-state, controlled-action,
approval, and local FITS-analysis primitives. It is resumable and supervised; it is not autonomous
scheduling or unattended operation.

## Input and plan

The target is explicit local evidence: a display name, RA in hours, and declination in degrees.
The input also bounds test exposure, gain, solve attempts, guiding-settle time, telemetry age, and
action timeout. An optional `image_file_path` can identify a NINA-managed local FITS file for Phase 6
read-only image-quality analysis.

The default `dry_run=true` call creates an immutable ten-minute workflow proposal and sends no NINA
request. Execution requires `dry_run=false`, `approved=true`, the returned `workflow_id`, and exactly
the same operational parameters.

## Execution boundaries

Approved execution performs only these steps before pausing:

1. Require fresh, non-contradictory session telemetry and a connected safety monitor reporting
   `IsSafe=true`.
2. Connect the required configured camera, mount, and optional guider through the existing Level 1
   action.
3. Recheck safety and readiness.
4. Capture one bounded solve frame, analyze supplied local pixel evidence, and plate solve it.
5. On solve failure, change only `solve_exposure_seconds`, recapture, and retry up to the configured
   hard limit of one to three attempts.
6. Create an existing `center_target` Level 2 action plan and return `AWAITING_APPROVAL` without
   sending mount motion.

Resumption requires the exact `center_approval_plan_id`. The workflow refreshes safety before
consuming it, centers, optionally starts guiding, captures one final bounded test frame, and returns
final scoped readiness plus workflow and session timelines. Guiding is polled only for reviewed
transitional/not-guiding states and stops at the bounded settle timeout or any non-guider failure.

When a local FITS path is supplied, an unreadable frame or a detected blocking condition such as
saturation, clipping, too few stars, severe defocus, likely trailing, severe gradient, or low usable
signal stops the workflow in a reported state. If no path is supplied, the workflow reports that
pixel-quality evidence was omitted instead of treating it as known-good.

No Level 3 operation is part of this workflow. If a later workflow adds one, it must pause at that
boundary under the same server-enforced policy.

## Failure behavior

Unsafe, missing-safety, contradictory, stale, offline, busy, or invalid state stops the workflow.
Failed actions and exhausted solve recovery also stop. A failed workflow cannot silently resume or
repeat completed actions. Its response includes attempted action results, changed variables, final
readiness, and the reconciled known session timeline.

## Hardware acceptance

Hosted CI runs the unit, MCP contract, and complete mock NINA workflow only. Live validation is
separately gated by `ALLOW_HARDWARE_TESTS`, `ALLOW_PHYSICAL_MOTION`, and
`ALLOW_PHASE7_WORKFLOW`, plus explicit target variables. The automated live harness performs only
the approved pre-motion slice and must stop at the centering plan. A human must inspect and submit
that exact plan before any Level 2 motion.

Current checkpoint: a local read-only NINA snapshot was reachable and internally consistent on
2026-08-08, with session state `CONNECTED`, but its safety monitor reported disconnected and
`IsSafe=false`. All three live workflow opt-ins were also unset. The workflow would stop before any
write under those conditions, so no live camera write or mount motion was performed. Full daylight
hardware acceptance remains blocked until the safety signal is positive and the separate opt-ins
and exact motion approval are supplied; it is never inferred from a green hosted CI result.

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

Phase 8 operating-skill work is not included.
