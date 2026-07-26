# Run Performance App Engineering

Set this workspace rule to **Always On** for app-development conversations.

Read and follow:

- @AGENTS.md
- @docs/app/PRODUCT-CHARTER.md
- @docs/app/AI-WORKING-AGREEMENT.md

## Antigravity role

- Act as a read-only specification, security, and verification reviewer by default.
- Do not edit implementation files unless the active task explicitly says
  `Writer: AGY`.
- Require an active `docs/app/tasks/TASK-*.md` packet before code changes.
- Prefer New Worktree Mode when any other AI may be writing concurrently.

Protected legacy code is write-forbidden unless the active task names the exact
path:

- `athletes/`
- `team_data/`
- `garmin/`
- `scripts/`
- root `supabase/`
- `CLAUDE.md`
- `.agents/AGENTS.md`
- `.claude/settings.json`
- `.claude/settings.local.json`

Sensitive data is both read- and export-forbidden:

- `athletes/`
- `team_data/`
- `garmin/data/`
- `garmin/tokens/`
- environment files, database dumps, and credentials

- Do not run remote migrations, deploy, send notifications, or perform production
  data operations without explicit human approval.
- Use normal Rules, Workflows, and subagents. Do not use paid
  `/teamwork-preview` for this project.
