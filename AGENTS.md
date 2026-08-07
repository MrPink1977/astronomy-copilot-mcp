# Codex guidance for astronomy-copilot-mcp

## Project purpose

This repository is an MCP server that exposes N.I.N.A. Advanced API capabilities to AI clients. The primary entry point is `nina_advanced_mcp.py`. Supporting modules include Target Scheduler DB access, alerting, and event buffering.

## Read this first

Before editing code:

1. Inspect the files directly related to the requested change.
2. Check `README.md` for user-facing behavior and setup assumptions.
3. Check `API_COVERAGE_ANALYSIS.md` and `nina_help.json` when changing MCP tools or API coverage.
4. Prefer small, targeted edits over broad rewrites.
5. Do not refactor the large `nina_advanced_mcp.py` file unless the task specifically requires it.

## Repository map

- `nina_advanced_mcp.py` — main MCP server and NINA Advanced API tool surface.
- `ts_db.py` — read-only Target Scheduler SQLite integration.
- `events.py` — NINA event subscriber and bounded event store.
- `alerter.py` — human alerting integration.
- `nina_help.json` — tool/help metadata.
- `API_COVERAGE_ANALYSIS.md` — API/tool coverage reference.
- `tests/` — offline automated tests that do not require a live NINA instance.
- `test_weather.py` — manual/live integration probe; it talks to a real NINA API endpoint and must not be run as part of normal automated testing.

## Safe development workflow

For non-trivial tasks:

1. Inspect and summarize the relevant implementation.
2. State the intended change briefly.
3. Make the smallest coherent edit.
4. Run the relevant offline tests.
5. Report changed files, tests run, and any live-NINA validation still needed.

## Testing

Normal safe test command:

```bash
pytest
```

The repository is configured so normal pytest discovery targets `tests/` only.

Do not run `test_weather.py` automatically. It is a live integration script that performs HTTP requests against a NINA server and can touch a real observatory environment.

When changing only one support module, run the narrow test first, for example:

```bash
pytest tests/test_events.py
pytest tests/test_alerter.py
pytest tests/test_ts_db.py
```

Then run the full offline suite before finishing when practical.

## Live NINA rules

Treat all real NINA API calls as hardware-facing integration work.

- Do not assume NINA is running.
- Do not assume `localhost:1888` or any other host is safe to call unless the user explicitly asks for live validation.
- Do not slew, move focusers, start exposures, connect/disconnect equipment, change cooling, or trigger other equipment actions merely to validate a code change.
- Prefer mocked/offline tests for development.
- If live validation is required, clearly identify the exact endpoint/tool that would be exercised before running it.

## Code conventions

- Preserve existing MCP tool names unless the task explicitly requires a breaking change.
- Preserve the response shape expected by existing clients.
- Reuse `create_error_response` and existing client helpers rather than inventing parallel patterns.
- Keep new network I/O async where the surrounding code is async.
- Avoid adding dependencies when the standard library or an existing dependency is sufficient.
- Never commit `.env`, logs, images, FITS files, local databases, credentials, webhook URLs, or access tokens.

## Documentation sync

When adding, removing, or materially changing an MCP tool, check whether all of these need updates:

- `README.md`
- `nina_help.json`
- `API_COVERAGE_ANALYSIS.md`
- tests

Do not update generated-looking counts or coverage claims unless the implementation was actually verified.

## Definition of done

A task is complete when:

- the requested behavior is implemented;
- unrelated code was not changed;
- relevant offline tests pass;
- user-facing docs/help are synchronized when behavior changes;
- any required live-NINA validation is called out separately rather than silently performed.

## Communication

Be concise. Do not narrate routine file reads or every command. During implementation, report only important discoveries, blockers, architecture decisions, and test failures. At completion report what changed, files changed, tests run, and remaining live validation if any.
