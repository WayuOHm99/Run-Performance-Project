# Feature Cycle

Description: Review or execute one approved app task without scope drift or
conflicting writers.

1. Read `AGENTS.md`, `docs/app/PRODUCT-CHARTER.md`,
   `docs/app/AI-WORKING-AGREEMENT.md`, and the requested `TASK-*.md`.
2. Confirm the task names one writer and that the current agent matches that role.
   If not, remain read-only.
3. Confirm the task's owned and forbidden paths. Check Git status before any work.
4. Review the acceptance criteria for ambiguity, security gaps, and unverifiable
   wording. Report blockers; do not invent product rules.
5. If acting as the main AGY reviewer, inspect the diff and run only commands
   explicitly permitted by the task and local permission policy. If delegating to
   the read-only `app-reviewer`, provide it the relevant changed files and existing
   verification results; that subagent cannot run commands. Neither reviewer edits
   implementation files.
6. If explicitly assigned as writer, use an isolated worktree, implement only the
   task scope, and add relevant tests.
7. Check for real athlete data, credentials, health values in logs, cross-team
   authorization gaps, and accidental legacy-path changes.
8. The assigned writer or main AGY runner runs every verification command in the
   task packet before the read-only subagent review.
9. Return the handoff format in `docs/app/AI-WORKING-AGREEMENT.md`.
10. Stop before merge, remote migration, deployment, notification send, or
    production-data access and request Product Owner approval.
