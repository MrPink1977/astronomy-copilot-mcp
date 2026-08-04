# Upstream and Fork Workflow

## Baseline

- Upstream repository: `https://github.com/michelebergo/nina_mcp_server.git`
- Preserved commit: `5c94276c84b71f4821df167270b6f2a441a15dd9`
- Local tag: `upstream-baseline-5c94276`
- Stable local branch: `main`
- Baseline documentation branch: `agent/phase-0-baseline`

## Current remotes

`upstream` is configured for the original project. `origin` is intentionally not configured yet because GitHub CLI is installed but not authenticated and the connected GitHub app does not expose an accessible fork.

Do not point `origin` at the upstream repository. `origin` must be the user's fork.

## Create the fork

Authenticate GitHub CLI interactively:

```powershell
gh auth login
gh auth status
```

Then create or connect the fork:

```powershell
gh repo fork michelebergo/nina_mcp_server --clone=false --remote=false
git remote add origin https://github.com/YOUR_USERNAME/astronomy-copilot-mcp.git
git remote -v
```

If GitHub creates the fork as `nina_mcp_server`, either keep that name or rename it on GitHub before adding `origin`. Confirm the exact repository URL rather than guessing the account name.

Push the preserved tag and baseline branch only after verifying `origin`:

```powershell
git push origin upstream-baseline-5c94276
git push -u origin agent/phase-0-baseline
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
