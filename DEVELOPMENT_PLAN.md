# Astronomy Copilot MCP Development Plan

Updated: 2026-08-03

## 1. Outcome

Build a safety-conscious Codex operator for a NINA-controlled observatory by extending, not replacing, `michelebergo/nina_mcp_server`.

The first production-worthy release must support this supervised workflow:

1. Inspect NINA and the active equipment profile.
2. Report camera, mount, guider, solver, sequence, and safety status in plain language.
3. Explain blocking issues and recommend one next action.
4. Connect equipment and capture a test exposure with approval.
5. Plate solve and center a target with explicit approval for mount motion.
6. Start an existing NINA sequence.
7. Stop safely and park with explicit approval.

Autonomous overnight operation, scheduling, APT, Home Assistant, weather automation, and a public dashboard are outside the first release.

## 2. Verified starting point

The local folder currently contains the project brief but is not yet a Git repository.

Upstream was inspected at:

- Repository: `https://github.com/michelebergo/nina_mcp_server`
- Main commit: `5c94276c84b71f4821df167270b6f2a441a15dd9`
- Commit date: 2026-07-23
- Runtime: Python 3.10+, FastMCP over stdio, NINA Advanced API at `localhost:1888/v2/api`
- Current structure: one 8,161-line `nina_advanced_mcp.py` module plus event, alert, and scheduler helpers
- Registered tools: 181 `@mcp.tool()` decorators; the README badge still says 176
- Automated tests: three test modules, focused on events, alerts, and the scheduler database
- Automation: no GitHub Actions workflow
- Packaging: `requirements.txt` only; no lockfile or `pyproject.toml`

This means the first engineering risk is regression in the large raw-tool module. Characterization and protocol tests must come before refactoring it.

## 3. Architecture direction

Keep two distinct surfaces:

- **Raw compatibility server:** the upstream MCP behavior, kept available for debugging and upstream merges.
- **Copilot server:** a new entrypoint exposing only a small, reviewed set of high-level tools.

The Copilot server may reuse upstream client code internally, but importing the raw implementation must not expose its 181 tools through the public Copilot MCP instance.

Target structure after the first few releases:

```text
astronomy-copilot-mcp/
|-- nina_advanced_mcp.py          # upstream-compatible raw server
|-- astronomy_copilot/
|   |-- server.py                 # curated FastMCP entrypoint
|   |-- adapters/
|   |   |-- nina.py
|   |   `-- phd2.py               # later, only if needed
|   |-- models/
|   |   |-- equipment.py
|   |   |-- readiness.py
|   |   `-- actions.py
|   |-- services/
|   |   |-- status.py
|   |   |-- readiness.py
|   |   `-- timeline.py
|   |-- diagnostics/
|   |   |-- camera.py
|   |   |-- mount.py
|   |   |-- guider.py
|   |   `-- plate_solving.py
|   |-- policy/
|   |   |-- approvals.py
|   |   `-- limits.py
|   |-- workflows/
|   |   |-- test_frame.py
|   |   |-- center_target.py
|   |   `-- prepare_for_imaging.py
|   `-- image_analysis/
|       |-- fits.py
|       `-- quality.py
|-- tests/
|   |-- unit/
|   |-- contract/
|   |-- mocked_nina/
|   `-- hardware_integration/
|-- docs/
`-- skills/astronomy-copilot/
```

Rules and policy stay out of MCP tool handlers. Tool handlers validate inputs, call a service or workflow, and return a stable typed response.

## 4. Build phases and acceptance gates

### Phase 0 - Repository and upstream baseline

Work:

- Fork upstream as `astronomy-copilot-mcp`.
- Initialize this non-empty local folder from upstream without losing the existing project brief.
- Configure `origin` as the fork and `upstream` as the original repository.
- Preserve commit `5c94276...` with a baseline tag.
- Use `main` for stable work and short-lived feature branches; avoid a long-lived `develop` branch unless release management later requires it.
- Record all upstream-local differences before making product changes.

Deliverables:

- Working local Git repository
- `docs/UPSTREAM_SYNC.md`
- Baseline tag such as `upstream-baseline-5c94276`

Gate:

- `git status` is clean except for intentionally added planning documentation.
- `origin` and `upstream` resolve to the correct repositories.
- Upstream can be fetched without rewriting local history.

### Phase 1 - Run and characterize upstream unchanged

Work:

- Create a reproducible Python environment and pin a tested dependency set.
- Run all existing tests.
- Verify the MCP starts and lists tools without NINA connected.
- On the observatory laptop, verify `GET /v2/api/version` and then exercise read-only calls.
- Perform one controlled camera connection and short exposure only after read-only checks pass.
- Inventory all raw tools and classify risk, reversibility, affected equipment, and first-release relevance.
- Capture representative NINA HTTP responses and websocket events with secrets and local paths sanitized.

Deliverables:

- `docs/BASELINE_TEST_REPORT.md`
- `docs/EXISTING_TOOL_INVENTORY.md`
- `docs/ARCHITECTURE.md`
- Sanitized fixtures under `tests/fixtures/nina/`

Gate:

- Existing tests pass in a clean environment.
- MCP handshake, tool listing, and at least five read-only NINA calls work.
- The exact outcome of a short test exposure is recorded.
- No upstream production behavior has been intentionally changed.

### Phase 2 - Test harness and first read-only vertical slice

Work:

- Add `pyproject.toml`, a lockfile, formatting/lint configuration, and GitHub Actions.
- Build a mock NINA HTTP server and event fixture player.
- Add the separate curated Copilot MCP entrypoint.
- Implement one tool: `get_observatory_status`.
- Normalize upstream data into stable component objects instead of passing raw responses through.

Minimum response contract:

```json
{
  "overall_state": "DEGRADED",
  "summary": "NINA is available; the camera is connected and the mount is parked.",
  "components": [],
  "blocking_issues": [],
  "warnings": [],
  "observed_at": "RFC3339 timestamp",
  "source": "nina_advanced_api"
}
```

Gate:

- The Copilot server exposes `get_observatory_status` and no physical-action tools.
- Tests cover healthy, partially connected, NINA-offline, malformed-response, and timeout cases.
- Raw upstream tools remain available through the compatibility server.
- CI passes without NINA or observatory hardware.

### Phase 3 - Imaging readiness and deterministic diagnostics

Work:

- Add `get_imaging_readiness`, `get_latest_error`, and `recommend_next_action`.
- Implement small, data-backed rule sets for camera, mount, guider, and plate solving.
- Give every finding a component, evidence, severity, confidence, and recommended first action.
- Change only one diagnostic variable per suggested retry.
- Do not infer a hardware fault when required telemetry is absent; report `UNKNOWN`.

Gate:

- Recorded scenarios produce deterministic, reviewed diagnoses.
- Readiness distinguishes `READY`, `DEGRADED`, `BLOCKED`, `OFFLINE`, and `UNKNOWN`.
- A recommendation references the evidence that triggered it.
- Repeating the same failed action without a changed condition is prevented or warned against.

### Phase 4 - Controlled actions and approval enforcement

Work:

- Add `connect_observatory`, `capture_test_frame`, `plate_solve_current_frame`, `center_target`, `start_guiding`, sequence controls, and `park_observatory` incrementally.
- Default every write workflow to `dry_run=true`.
- Enforce action levels inside the server, not only through client-side MCP approval prompts.
- For physical or session-ending operations, generate a short-lived action plan with an ID and require that ID for execution.
- Add timeouts, cancellation, bounded retries, input limits, idempotency where possible, and an audit event for every attempted action.

Policy:

| Level | Examples | Requirement |
|---|---|---|
| 0 | status, logs, metadata | automatic |
| 1 | test exposure, preview settings, connect device | dry run by default; general approval to execute |
| 2 | slew, unpark, large focuser move | explicit action-plan approval |
| 3 | stop sequence, park, disconnect, shutdown | explicit action-plan approval; no assumed emergency authority |

Gate:

- Dry runs send no write requests to NINA.
- Expired, reused, mismatched, or altered approval plans are rejected.
- Motion and session-ending tests run only against the mock server in CI.
- Hardware tests require both `ALLOW_HARDWARE_TESTS=true` and a separate physical-motion opt-in.

### Phase 5 - Session state and event timeline

Work:

- Model `OFFLINE`, `STARTING`, `CONNECTED`, `PREVIEWING`, `SLEWING`, `CENTERING`, `GUIDING`, `IMAGING`, `PAUSED`, `RECOVERING`, `PARKING`, `SAFE`, and `ERROR`.
- Derive transitions from upstream websocket events and reconcile with a full status snapshot at startup and after reconnects.
- Add `get_session_timeline` with bounded, structured event history.
- Reject operations invalid for the current state.

Gate:

- Transition tests cover normal flow, duplicate events, missing events, reconnects, and contradictory telemetry.
- Restarting the MCP does not falsely claim an unsafe state is safe.
- Commands such as parking during a slew or starting a second sequence are rejected deterministically.

### Phase 6 - FITS and image-quality analysis

Work:

- Add FITS metadata and pixel-statistics support first.
- Then add saturation, clipping, detected-star count, HFR/FWHM estimate, ellipticity, gradient, hot-pixel, and trailing indicators.
- Preserve the original image; analysis is read-only.
- Maintain small fixture images with known expected measurements and tolerances.

Gate:

- Measurements are validated against controlled FITS fixtures.
- The tool distinguishes unavailable evidence from a negative finding.
- Results include method, units, thresholds, and limitations.
- No image files are uploaded or transmitted outside the local machine.

### Phase 7 - Complete supervised imaging workflow

Work:

- Compose the proven primitives into `prepare_for_imaging`.
- Return a proposed plan before any equipment-changing step.
- Pause at every Level 2 or Level 3 boundary.
- Stop on unsafe, contradictory, or stale telemetry.
- Produce a final readiness report and timeline.

Gate:

- The workflow succeeds end-to-end against the mock NINA scenario.
- It is then validated on live hardware in daylight/safe conditions before a night test.
- Plate-solve recovery has a hard retry limit. Normal recovery changes one exposure variable at a
  time; supervised cloudy-weather recovery instead keeps the three-second exposure fixed, waits
  five minutes, and repeats the full preflight before each of at most three attempts.
- A successful HTTP/API envelope is insufficient: the nested solve must explicitly succeed and
  contain valid finite solution coordinates before a centering plan can exist.
- A failed step leaves the rig in a known, reported state and never silently continues.

### Phase 8 - Codex operating skill

Work:

- Create `skills/astronomy-copilot/SKILL.md` only after tool contracts stabilize.
- Document startup, shutdown, preview, centering, solve recovery, camera recovery, guider recovery, and stop conditions.
- Make the skill defer to server-enforced approvals rather than attempting to override them.

Gate:

- Scripted prompt tests choose the high-level tools rather than raw controls.
- The requested phrase "Check my observatory" produces the expected status/readiness workflow.
- Recovery prompts stop after bounded attempts and present the evidence to the user.

### Phase 9 - PHD2 direct adapter, only if justified

Work:

- Compare NINA guider telemetry with the information needed for diagnosis.
- Add direct PHD2 access only for missing data such as calibration state, detailed guide corrections, or recent log events.
- Implement `analyze_guiding(window_minutes=5)` from timestamped samples.

Gate:

- The adapter has recorded fixtures and works when PHD2 is absent.
- Calculated RMS values and directional conclusions are numerically tested.
- No duplicate control path can issue conflicting guide commands.

### Phase 10 - Beta hardening and deferred integrations

Only after the supervised NINA release is stable:

- Installer and configuration validation
- Documented NINA and Advanced API compatibility matrix
- Mock/demo mode
- Release packaging and signed checksums where practical
- Issue templates and troubleshooting bundle
- Home Assistant, all-sky camera, weather, dew risk, notifications, and dashboard

Autonomous scheduling and unattended recovery require a separate safety review and are not implied by this plan.

## 5. Test strategy

Four layers are required:

1. **Unit tests:** rules, state transitions, policy, validation, and response contracts.
2. **Contract tests:** curated MCP tool listing/calls and exact normalized schemas.
3. **Mock integration tests:** HTTP responses, websocket events, timeouts, malformed data, and failure sequences.
4. **Hardware integration tests:** explicitly enabled, initially read-only, then controlled writes, then physical motion.

CI must run the first three layers on every pull request. Hardware tests never run in hosted CI.

## 6. Delivery sequence

Use small pull requests with one acceptance gate each:

1. **PR 1 - Baseline:** upstream import, environment, existing tests, architecture and baseline reports.
2. **PR 2 - Harness:** packaging, lockfile, CI, mock NINA, MCP contract tests.
3. **PR 3 - Status slice:** curated server plus `get_observatory_status` only.
4. **PR 4 - Readiness:** readiness model, first deterministic rules, latest error, next action.
5. **PR 5 - Test frame:** approval plan, dry run, camera connect, bounded test capture.
6. **PR 6 - Solve and center:** image checks, solve failure rules, approved mount motion.
7. **PR 7 - Guiding and sequence:** guiding status/control and existing sequence control.
8. **PR 8 - State and timeline:** event reconciliation, command guards, audit history.
9. **PR 9 - Image quality:** FITS fixtures and validated quality measurements.
10. **PR 10 - Supervised workflow and skill:** `prepare_for_imaging`, operating instructions, live acceptance report.

Do not combine the monolith refactor, public-tool redesign, action policy, and live-hardware behavior into one pull request.

## 7. Definition of version-one done

Version one is done only when:

- A clean install can start both raw and curated MCP profiles.
- `Check my observatory` returns a useful normalized report.
- Offline, partial, and failed-equipment states are explained accurately.
- A test exposure can be proposed, approved, captured, and evaluated.
- A target can be plate solved and centered with explicit motion approval.
- Guiding and an existing NINA sequence can be started under validated preconditions.
- Stop and park require explicit approval and produce an auditable final state.
- All non-hardware tests pass in CI.
- Hardware acceptance results and known limitations are documented.
- No autonomous overnight control is claimed.

## 8. Immediate next action

Start Phase 0 and Phase 1 only:

> Fork and baseline the upstream project without changing its behavior. Run its tests, inventory its files and MCP tools, document the architecture, identify the NINA Advanced API client layer, and produce a baseline report. Do not refactor or add features yet.

The first feature after that gate is a single read-only `get_observatory_status` vertical slice.
