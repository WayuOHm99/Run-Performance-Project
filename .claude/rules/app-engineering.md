---
paths:
  - "AGENTS.md"
  - "platform/**/*"
  - "docs/app/**/*"
  - ".agents/rules/**/*"
  - ".agents/workflows/**/*"
  - ".agents/agents/**/*"
  - ".claude/rules/**/*"
---

# New Mobile App Engineering

Do not use a plain Claude Code session from the repository root for app work. Follow
`docs/app/CLAUDE-CODE-SETUP.md` so the legacy coaching `CLAUDE.md` is excluded.

Before changing a matching file, read:

- `AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/AI-WORKING-AGREEMENT.md`
- the active `docs/app/tasks/TASK-*.md`

For app work, Claude Code is the implementation engineer only when the task packet
names `Writer: Claude Code`.

- Stay inside the task's owned paths.
- Do not change product scope, accepted ADRs, shared contracts, migrations, or
  dependency files unless the task explicitly owns them.
- Treat these exact legacy paths as read-only unless the task explicitly names
  them: `athletes/`, `team_data/`, `garmin/`, `scripts/`, root `supabase/`,
  `CLAUDE.md`, `.agents/AGENTS.md`, `.claude/settings.json`, and
  `.claude/settings.local.json`.
- Never read or export real data from `athletes/`, `team_data/`, `garmin/data/`,
  `garmin/tokens/`, environment files, database dumps, or credentials.
- Use synthetic data only.
- Run all task verification commands and return the required handoff.
- Do not merge, deploy, run a remote migration, or use production secrets.
