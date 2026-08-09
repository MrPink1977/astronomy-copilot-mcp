# Phase 7: Complete Supervised Imaging Workflow

`prepare_for_imaging` composes the proven status, readiness, session-state, controlled-action,
approval, and local FITS-analysis primitives. It is resumable and supervised; it is not autonomous
scheduling or unattended operation.

## Input and plan

The target is explicit local evidence: a display name, RA in hours, and declination in degrees.
The input also bounds test exposure, gain, solve attempts, guiding-settle time, telemetry age, and
action timeout. `cloudy_weather_retry=true` retains the same solve exposure, waits five minutes,
and repeats the complete preflight before the next bounded attempt. An optional `image_file_path`
can identify a NINA-managed local FITS file for Phase 6 read-only image-quality analysis.

The default `dry_run=true` call creates an immutable ten-minute workflow proposal and sends no NINA
request. Execution requires `dry_run=false`, `approved=true`, the returned `workflow_id`, and exactly
the same operational parameters.

## Execution boundaries

Approved execution performs only these steps before pausing:

1. Require fresh, non-contradictory session telemetry. A connected safety monitor must report
   `IsSafe=true`. When the read-only active profile explicitly reports
   `SafetyMonitorSettings.Id=No_Device`, execution may instead use the exact
   `OPERATOR_CONFIRMS_SAFE` attestation with a timestamp no more than five minutes old.
2. Connect the required configured camera, mount, and optional guider through the existing Level 1
   action.
3. Recheck safety and readiness.
4. Capture one bounded solve frame, analyze supplied local pixel evidence, and plate solve it.
5. Accept the solve only when NINA's nested result explicitly reports success and supplies finite,
   in-range RA and declination. Malformed optional rotation or pixel-scale values also fail it. An
   outer successful HTTP/API envelope is not a successful plate solution.
6. In normal recovery, change only `solve_exposure_seconds`, recapture, and retry up to the hard
   limit. In cloudy-weather mode, retain the three-second exposure, wait five minutes, and rerun the
   full safety, contradiction, connection, tracking, guiding, and readiness preflight before every
   retry. The live harness permits at most three attempts.
7. Create an existing `center_target` Level 2 action plan only after a valid solution, then return
   `AWAITING_APPROVAL` without sending mount motion.

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

Unsafe, unproved safety-monitor absence, missing or expired operator attestation, contradictory,
stale, offline, busy, or invalid state stops the workflow. A disconnected configured monitor,
unknown monitor configuration, or connected monitor reporting unsafe cannot be overridden by an
operator attestation.
Failed actions and exhausted solve recovery also stop. A failed workflow cannot silently resume or
repeat completed actions. Its response includes attempted action results, changed variables, final
readiness, and the reconciled known session timeline.

Cloudy-weather retries never weaken the five-minute operator-attestation limit. With no configured
safety monitor, an attestation that expires during the wait stops the workflow before another
capture and explicitly requests a fresh attestation. A new authorized run is then required. A
connected monitor that becomes unsafe, a configured monitor that disconnects, lost required
tracking or guiding, contradictory telemetry, or another failed preflight likewise stops
immediately.

Advanced API 2.2.15.2 does not implement the previously assumed `plate-solve/status` route.
Readiness uses its supported read-only `profile/show?active=true` endpoint and sanitizes the active
`PlateSolveSettings`. The actual solve remains the bounded, blocking `prepared-image/solve` action,
so configuration readiness is never reported as a successful solve.

## Hardware acceptance

Hosted CI runs the unit, MCP contract, and complete mock NINA workflow only. Live validation is
separately gated by `ALLOW_HARDWARE_TESTS`, `ALLOW_PHYSICAL_MOTION`, and
`ALLOW_PHASE7_WORKFLOW`, plus explicit target variables. The automated live harness performs only
the approved pre-motion slice, uses exactly three-second solve frames, enables the five-minute
cloudy-weather retry policy with a three-attempt maximum, and must stop at the centering plan. A
human must inspect and submit that exact plan before any Level 2 motion. A failed or malformed solve
must finish without any centering plan.

Live finding on 2026-08-09 UTC: the authorized Altair pre-motion run captured one three-second frame
and NINA returned an outer successful response containing a nested `success=false` solve result
with no solution coordinates. The earlier workflow incorrectly created a centering plan. Strict
nested-result validation now prevents that plan, and live acceptance remains pending until a fresh
authorized run obtains a valid solution. The post-run read-only state showed the mount connected,
tracking sidereal, and not slewing; the camera connected and idle; and PHD2 guiding. No centering or
subsequent mount motion occurred.

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
