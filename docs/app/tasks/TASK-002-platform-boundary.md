# TASK-002: Separate the new platform workspace

Status: Complete

Writer: ChatGPT/Codex

Reviewer: AGY (`app-reviewer`, read-only)

## Goal and user value

Create an unmistakable filesystem boundary so all new mobile app and backend work
stays separate from the live coaching operation without moving or deleting legacy
files.

## In scope

- Create the new `platform/` workspace boundary.
- Document what may and may not live under `platform/`.
- Add path-scoped AI instructions for future work inside `platform/`.
- Reserve the intended top-level structure without scaffolding Expo or Supabase.

## Out of scope

- Moving, renaming, editing, archiving, or deleting legacy files.
- Installing JavaScript dependencies or creating a lockfile.
- Scaffolding Expo.
- Creating a database schema.
- Reading or copying real athlete, Garmin, token, environment, or database data.

## Owned paths

- `platform/`
- `docs/app/tasks/TASK-002-platform-boundary.md`
- `docs/app/reviews/TASK-002-AGY.md`

## Forbidden paths

- `athletes/`
- `team_data/`
- `garmin/`
- `scripts/`
- root `supabase/`
- `CLAUDE.md`
- `.agents/AGENTS.md`
- `.claude/settings.json`
- `.claude/settings.local.json`

## References

- `AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/architecture/ADR-0001-platform-boundary.md`

## Acceptance criteria

- [x] `platform/` clearly identifies itself as the only home for new app code.
- [x] Future mobile, shared-package, and app-backend locations are documented.
- [x] A nested `AGENTS.md` reinforces the boundary for AI tools.
- [x] No protected legacy path is modified.
- [x] No dependency, generated artifact, secret, or real athlete data is added.
- [x] AGY returns no blocker, high, or medium finding.

## Privacy classification

No user data. This task creates instructions and empty workspace boundaries only.
No legacy health-data path may be inspected for implementation.

## Verification

```powershell
git status --short
git diff --check
git diff --name-only HEAD
Get-ChildItem -Force -Recurse -Depth 3 platform
```

Expected changed paths must be limited to `platform/`, this task packet, and its
AGY review report.

## Dependencies and open decisions

- Expo and package versions will be selected in a later implementation task.
- Empty future directories are described, not committed, because Git does not
  track empty directories.

## Required handoff

- Clean commit SHA
- Changed files
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
