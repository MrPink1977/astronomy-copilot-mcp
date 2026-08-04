# Upstream and Fork Workflow

## Baseline

- Upstream repository: `https://github.com/michelebergo/nina_mcp_server.git`
- Preserved commit: `5c94276c84b71f4821df167270b6f2a441a15dd9`
- Local tag: `upstream-baseline-5c94276`
- Stable local branch: `main`
- Baseline documentation branch: `agent/phase-0-baseline`

## Current remotes

`upstream` is configured for the original project:

```text
https://github.com/michelebergo/nina_mcp_server.git
```

`origin` is configured for the user's public fork:

```text
https://github.com/MrPink1977/astronomy-copilot-mcp.git
```

Do not point `origin` at the upstream repository. `origin` must be the user's fork.

## Published baseline

The fork was created on 2026-08-04. These refs have been pushed to `origin`:

```text
agent/phase-0-baseline
upstream-baseline-5c94276
```

Git HTTPS push authentication succeeded through the configured Windows credential path. GitHub CLI remains separately unauthenticated; run the following before any workflow that specifically requires `gh`:

```powershell
gh auth login
gh auth status
```

## Regular upstream sync

Keep local `main` as the stable integration base:

```powershell
git fetch upstream --tags
git switch main
git merge --ff-only upstream/main
git push origin main
```

If `main` contains product commits and cannot fast-forward, stop and inspect the divergence. Use a reviewed merge branch instead of force-pushing:

```powershell
git switch -c agent/sync-upstream-YYYY-MM-DD main
git merge upstream/main
```

Resolve conflicts, run the baseline and contract tests, then open a pull request into the fork's `main`.

## Feature workflow

Create short-lived branches from updated `main`:

```powershell
git switch main
git pull --ff-only origin main
git switch -c agent/short-description
```

Each pull request should contain one acceptance gate. Do not mix upstream synchronization with a feature refactor unless the change is inseparable and explicitly reviewed.

## Safety rules

- Never force-push `main` or rewrite the baseline tag.
- Never commit `.env`, access tokens, Discord webhooks, local image paths, or unsanitized NINA payloads.
- Review recorded fixtures for coordinates, filenames, usernames, and observatory details before committing.
- Keep raw upstream behavior available until the curated Copilot server has equivalent characterization coverage.
