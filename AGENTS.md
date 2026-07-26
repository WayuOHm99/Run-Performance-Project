# Run Performance App — AI Engineering Contract

## Scope

This file governs engineering work for the new athlete-and-coach mobile app.

- New app code belongs under `platform/`.
- Product and engineering decisions belong under `docs/app/`.
- The existing Garmin, LINE, Streamlit, Notion, and scheduled-task system is a live
  legacy operation. Do not refactor it as part of app work.
- Coaching and training-plan tasks continue to follow `CLAUDE.md` and
  `.agents/AGENTS.md`.

## Sources of truth

Use this order when instructions disagree:

1. The human Product Owner's explicit decision in the active task.
2. The active `docs/app/tasks/TASK-*.md` task packet.
3. Accepted records in `docs/app/architecture/`.
4. `docs/app/PRODUCT-CHARTER.md`.
5. Existing code and automated tests.
6. AI chat history is context only, never the final source of truth.

Product requirements live in Git. Notion and the Garmin database remain sources of
truth for current coaching operations, not for app requirements.

## Protected legacy areas

Treat these paths as read-only unless the active task explicitly names them:

- `athletes/`
- `team_data/`
- `garmin/`
- `scripts/`
- `supabase/`
- `CLAUDE.md`
- `.agents/AGENTS.md`
- `.claude/settings.json`
- `.claude/settings.local.json`

The root `supabase/` directory contains the existing LINE webhook. The new app
backend must live at `platform/supabase/`.

Never copy production athlete data, Garmin tokens, environment files, database
dumps, or service-role credentials into `platform/`, tests, prompts, screenshots,
logs, commits, or AI review artifacts.

## Task ownership

- Every code change requires a task packet.
- Every task names exactly one writer: `ChatGPT`, `Claude Code`, or `AGY`.
- A reviewer does not edit the implementation being reviewed.
- Claude Code app sessions must use the isolated launch procedure in
  `docs/app/CLAUDE-CODE-SETUP.md`; do not start a plain app session from the
  repository root.
- If ownership changes, first create a clean commit and record its SHA in the task.
- Parallel writers must use separate Git worktrees and may not own the same
  migration, contract, dependency file, or lockfile.
- Never auto-resolve a semantic merge conflict.

Reviewers may write findings only under `docs/app/reviews/` when the task requests
a persisted report.

## Required workflow

1. Read the task packet and referenced decisions.
2. Inspect before editing and preserve unrelated user changes.
3. Implement only the stated scope.
4. Run the task's verification commands.
5. Report changed files, checks run, remaining risks, and rollback notes.
6. Obtain human approval before merge, remote migration, deployment, notification
   send, or production-data operation.

Use the canonical handoff format in
`docs/app/AI-WORKING-AGREEMENT.md`.

## Health-data rules

- Use synthetic fixtures only, such as `athlete-a`; never use a real athlete's name
  or measurements in app development.
- OS health permission is separate from consent to upload and share with a coach.
- Enforce coach access on the backend with RLS and authorization tests.
- Treat pain/injury status, RPE, subjective feeling, sleep, heart rate, and workout
  measurements as protected health data.
- Do not place protected health values in analytics, push payloads, crash context,
  session replay, or application logs.
- Store summaries when summaries are sufficient. Avoid raw GPS and raw
  heart-rate/sleep-stage series in the MVP.
- Support revoked sharing, deletion, stale data, partial permission, and missing
  wearable data.
- Flags are decision support, not diagnosis.

## New app conventions

- The JavaScript workspace will be rooted at `platform/`, not the repository root.
- Use TypeScript strict mode and pnpm. Pin versions in the lockfile.
- Keep mobile, shared contracts, and Supabase migrations independently testable.
- No runtime AI feature is part of the MVP. ChatGPT, Claude, and Antigravity are
  development tools only.
- Prefer a small vertical slice with tests over broad scaffolding without a user
  outcome.

## Definition of done

A task is complete only when:

- its acceptance criteria are satisfied;
- formatting, lint, typecheck, and relevant tests pass;
- authorization-negative tests pass for any protected data;
- no secret or real athlete data was added;
- documentation and contracts match the implementation;
- the handoff records known limitations and how to roll back.
