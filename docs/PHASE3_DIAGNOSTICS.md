# Phase 3 Readiness and Diagnostics

## Scope

Phase 3 adds three read-only tools to the curated server:

- `get_imaging_readiness()`
- `get_latest_error()`
- `recommend_next_action(previous_recommendation_id=None)`

Together with `get_observatory_status()`, these are the only curated tools. Phase 3 sends HTTP
`GET` requests only and does not connect equipment, capture images, guide, solve, slew, alter
settings, or execute the returned recommendations.

## Evidence sources

Rules consume reviewed fields from the existing NINA status endpoints:

- Camera: `Connected`, `CameraState`/`State`, `IsExposing`, and an explicitly reported error.
- Mount: `Connected`, `AtPark`/`IsParked`, `Slewing`/`IsSlewing`,
  `Tracking`/`IsTracking`/`TrackingEnabled`, and an explicitly reported error.
- Guider: `Connected`, `State`, and an explicitly reported error.
- Plate solving: the primary and blind solver selections from the active profile's
  `PlateSolveSettings`.

The camera, mount, and guider fields match the Advanced API response models in
[`Camera.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Camera.cs),
[`Mount.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Mount.cs),
and
[`Guider.cs`](https://github.com/christian-photo/ninaAPI/blob/dev/ninaAPI/WebService/V2/Equipment/Guider.cs).
Advanced API 2.2.x does not publish the previously assumed `plate-solve/status` route. Readiness
uses the supported read-only `profile/show?active=true` route instead. Missing or malformed profile
data becomes `UNKNOWN`; an explicitly empty primary-solver selection is blocking. Configuration
evidence does not claim that a solve has run or will succeed. The blocking
`prepared-image/solve` action remains the authoritative execution result.

## Deterministic rule set

| Component | Reviewed condition | Impact | First action / one variable |
|---|---|---|---|
| Camera | disconnected | `BLOCKING` | connect camera / `camera_connection` |
| Camera | exposing or downloading | `BLOCKING` | wait / `camera_activity` |
| Camera | explicit error | `BLOCKING` | inspect error / `camera_error_condition` |
| Mount | disconnected | `BLOCKING` | connect mount / `mount_connection` |
| Mount | parked | `BLOCKING` | prepare approved unpark / `mount_park_state` |
| Mount | slewing | `BLOCKING` | wait / `mount_slew_state` |
| Mount | tracking disabled | `BLOCKING` | enable tracking / `mount_tracking` |
| Guider | disconnected | `BLOCKING` | connect guider / `guider_connection` |
| Guider | looping without guiding | `BLOCKING` | select guide star / `guider_star_selection` |
| Guider | stopped | `BLOCKING` | start guiding / `guider_running_state` |
| Guider | calibrating, settling, or dithering | `WARNING` | wait / `guider_state` |
| Plate solving | no configured primary solver | `BLOCKING` | configure solver / `plate_solver_configuration` |
| Any required signal | absent or malformed | `UNKNOWN` | refresh/inspect telemetry only |

Every finding includes a stable code, component, issue, source-anchored evidence, severity,
confidence, impact, one recommended first action, and exactly one named retry variable. The rules do
not diagnose USB congestion, focus, saturation, RMS quality, solver installation, or other causes
without the required evidence.

## Readiness states

State selection uses this precedence:

1. NINA transport unavailable: `OFFLINE`.
2. Any explicit blocking condition: `BLOCKED`.
3. No blocker but required telemetry is missing: `UNKNOWN`.
4. No blocker/unknown but a transitional warning exists: `DEGRADED`.
5. All reviewed conditions satisfied: `READY`.

Recorded, sanitized scenarios under `tests/fixtures/diagnostics/` cover every state.

## Latest error

`get_latest_error` considers explicit `LastError`, `Error`, or `ErrorMessage` fields only. When
timestamps are present, the newest timestamp wins. Without a current explicit error it returns
`NONE`, or `UNKNOWN` when incomplete telemetry prevents confirmation. Error text is bounded and
redacts common credential assignments, credential query parameters, and Windows file paths.

## Repeat protection

`recommend_next_action` returns one finding and a deterministic `recommendation_id` derived from its
code, evidence, action, and retry variable. After an unsuccessful attempt, the caller passes that ID
as `previous_recommendation_id`. If the same evidence still produces the same ID, the response sets
`should_retry=false` and warns against repeating the action until the named condition changes or is
re-checked.

This mechanism is deliberately stateless. Persistent session history and command enforcement remain
outside Phase 3.

## Phase boundary

Phase 4 controlled actions, approval plans, dry runs, motion, capture, guiding control, plate-solving
execution, sequence control, and parking are not implemented here.
