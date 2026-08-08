# Astronomy Copilot MCP: Read-Only Status Slice

## Value Proposition

Give an astrophotographer a trustworthy answer to “Check my observatory” without exposing NINA's large raw control surface or changing equipment state.

Today, the operator must inspect several NINA panels or interpret many low-level MCP tools. The first curated slice combines those observations into one concise report while preserving uncertainty and identifying blockers.

**Core action:** Read and summarize current NINA and equipment status through one MCP tool, `get_observatory_status`.

## Why an LLM Client?

**Conversational win:** The operator can ask a natural question instead of navigating multiple equipment tabs and translating raw device responses.

**LLM contribution:** Explain the normalized status, warnings, and blocking issues in context and help the operator understand what to inspect next.

**What the LLM lacks:** Direct, reliable observatory telemetry. This MCP server supplies a narrow and typed read-only status contract from the local NINA Advanced API.

## Interaction Overview

1. The user asks the MCP client to check the observatory.
2. The client calls `get_observatory_status` with no arguments.
3. The tool queries approved read-only NINA endpoints and returns a compact normalized report.
4. The client explains `READY`, `DEGRADED`, `BLOCKED`, `OFFLINE`, or `UNKNOWN` conditions without performing a corrective action.

There is no embedded application UI in this slice. The MCP response is designed for a conversational client and structured-data inspection.

## Product Context

- **Existing product:** Local NINA installation with Advanced API 2.2.15.2 on `127.0.0.1:1888`.
- **Compatibility surface:** The upstream raw MCP server remains available separately and unchanged.
- **New surface:** A separate curated FastMCP entrypoint exposing exactly one public tool.
- **Transport:** Local MCP over stdio; local NINA HTTP API.
- **Authentication:** None added in this local-only phase.
- **Data handling:** Do not return or log raw profiles, credentials, secrets, or local image contents.

## Tool Contract

`get_observatory_status()` returns:

```json
{
  "overall_state": "DEGRADED",
  "summary": "NINA is available; one or more configured components are unavailable.",
  "components": [],
  "blocking_issues": [],
  "warnings": [],
  "observed_at": "RFC3339 timestamp",
  "source": "nina_advanced_api"
}
```

Each component contains a stable name, connection state, normalized state, and sanitized details when useful. Missing or contradictory telemetry is reported as `UNKNOWN`; it is never silently treated as safe or healthy.

## UX Flow and Architecture

**Check observatory:** Ask for status, fetch one normalized snapshot, and explain the returned state. The flow needs no custom UI because the output is a short textual summary plus structured component data.

**Tool: `get_observatory_status`**

- **Input:** None
- **Output:** `ObservatoryStatus`
- **Behavior:** Calls a dedicated read-only NINA adapter, normalizes equipment responses in a status service, and returns the stable contract above.
- **Separation:** The curated FastMCP instance does not import or serve the upstream raw FastMCP instance.

## Safety and Interpretation Rules

- Make HTTP `GET` requests only. Do not connect, disconnect, slew, expose, cool, guide, solve, start a sequence, or alter settings.
- Do not call device-list/rescan endpoints that may produce side effects.
- Do not count the MCP HTTP session as connected observatory equipment.
- A disconnected safety monitor is `UNKNOWN` or `UNAVAILABLE`, not `UNSAFE`.
- Obtain the Advanced API version from `/version`; do not use the unavailable `/application/version` route.
- Preserve source distinctions when upstream measurements disagree.
- A detector count from a dark/noisy preview is not proof of real stars. HFR is not considered reliable without valid star detections from a suitable light frame.

## Acceptance Criteria

- The curated server lists `get_observatory_status` and no physical-action tools.
- Tests cover healthy, partially connected, NINA-offline, malformed-response, and timeout scenarios using mocks only.
- Output follows the stable response contract and contains no raw secrets.
- The raw upstream MCP server remains behaviorally unchanged.
- Existing upstream automated tests continue to pass.

## Out of Scope

- Equipment connection or any other write action
- Capture, motion, guiding, cooling, plate solving, and sequence control
- Readiness recommendations and automated diagnostics beyond status normalization
- Image-quality analysis or claims that detected points are genuine stars
- Autonomous operation, scheduling, public UI, or remote deployment
