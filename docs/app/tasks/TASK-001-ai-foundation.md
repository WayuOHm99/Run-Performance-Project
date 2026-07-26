# TASK-001: Establish the Safe App Foundation

Status: Complete

Writer: ChatGPT

Reviewers: AGY app-reviewer, Product Owner

## Goal and user value

Create one shared product and AI working model before application code is generated,
so ChatGPT, Claude Code, and Antigravity do not damage the existing operation or
make conflicting product decisions.

## In scope

- Create a root AI engineering contract.
- Record the approved MVP including the sleep addition.
- Record AI roles, handoff gates, and human approvals.
- Record the repository boundary for the new app.
- Add scoped Claude Code and Antigravity instructions.
- Add a Claude Code launch profile that excludes the legacy coaching context and
  sensitive paths.
- Add a reusable Antigravity feature workflow and read-only reviewer.

## Out of scope

- Installing pnpm, Expo, EAS, or Supabase CLI.
- Creating `platform/`.
- Modifying the Garmin, LINE, Streamlit, Notion, or scheduled-task system.
- Accessing real athlete data.
- Creating or deploying a Supabase project.

## Owned paths

- `AGENTS.md`
- `docs/app/`
- `.agents/rules/`
- `.agents/workflows/`
- `.agents/agents/`
- `.claude/rules/`

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

- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/AI-WORKING-AGREEMENT.md`
- `docs/app/architecture/ADR-0001-platform-boundary.md`

## Acceptance criteria

- [x] The new app and legacy system have unambiguous directory ownership.
- [x] ChatGPT, Claude Code, AGY, and the Product Owner have named responsibilities.
- [x] One-task/one-writer and independent-review rules are recorded.
- [x] The MVP includes nightly sleep summaries and excludes other recovery metrics.
- [x] Human approval gates cover merge, deploy, remote migration, and production
      health-data operations.
- [x] No legacy runtime file, credential, or athlete-data file is changed.
- [x] Claude and AGY rules list the same protected legacy paths as `AGENTS.md`.
- [x] The read-only AGY reviewer does not claim permission to run commands or edit
      files.
- [x] Claude Code app sessions have a documented isolated-worktree launch profile
      that excludes the root coaching `CLAUDE.md`.
- [x] Markdown and Git whitespace checks pass.

## Privacy classification

Documentation only. The initial repository-instruction audit inspected the existing
root `CLAUDE.md` to identify its role and establish the boundary. No athlete folder,
Garmin database, token, environment file, or production backend was accessed, and
no real athlete detail was copied into app artifacts. All new examples are
synthetic. Future app sessions must exclude the root coaching context.

## Verification

```text
git diff --check
git status --short
```

Also inspect the changed-path list and confirm it is a subset of the owned paths.

## Dependencies and open decisions

- Assumption: `agy` means Google Antigravity. The existing `.agents/` configuration
  and current official product terminology support this assumption.
- Exact Expo and package versions remain intentionally open until TASK-002 checks
  the current compatibility matrix.

## Review evidence

- `docs/app/reviews/TASK-001-AGY.md`
- Final AGY recommendation: PASS with no blocker, high, or medium findings.

## Rollback

Delete only the files added by TASK-001 and switch back to `master`. No operational
system change is involved.
