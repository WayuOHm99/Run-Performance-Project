# Platform Workspace Instructions

These instructions apply to every file under `platform/` and extend the root
`AGENTS.md`.

## Isolation

- Treat `platform/` as the root of the new product workspace.
- Do not import code, configuration, databases, or data from protected legacy
  paths at the repository root.
- The app backend is `platform/supabase/`; root `supabase/` is a different live
  system.
- Do not create new app files outside `platform/` unless the active task explicitly
  owns documentation under `docs/app/`.

## Engineering

- Use pnpm and TypeScript strict mode.
- Pin dependency versions through `platform/pnpm-lock.yaml`.
- Keep mobile, contracts, domain logic, and database authorization independently
  testable.
- Add only the structure required by the active task.
- Use synthetic fixtures only; never add real names or health measurements.
- Do not log RPE, pain, sleep, heart rate, workout values, credentials, or tokens.

## Ownership and safety

- Read the active `docs/app/tasks/TASK-*.md` before editing.
- Exactly one AI writer owns a task.
- Stay within the task's owned paths.
- Do not deploy, push, submit a store build, or run a remote migration without
  explicit Product Owner approval.
