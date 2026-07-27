# TASK-007: Supabase local development foundation

Status: In Progress

Writer: ChatGPT/Codex

Reviewer: AGY (`app-reviewer`, read-only)

## Goal and user value

Create a reproducible, project-local Supabase development environment so database
and authorization work can be tested safely before any remote migration or
protected athlete data is introduced.

## In scope

- Pin the Supabase CLI as a `platform/` development dependency.
- Add minimal root scripts for starting, stopping, and checking the local stack.
- Initialize Supabase only at `platform/supabase/`.
- Verify the local stack can start against Docker Desktop's WSL 2 Linux engine.
- Keep generated local runtime state ignored.
- Document the Windows prerequisites and safe local commands.

## Out of scope

- Supabase login, project linking, Management API calls, or remote migrations.
- Tables, schemas, seed data, RLS policies, authorization tests, or generated
  database types.
- Reading or changing the hosted Supabase project.
- Authentication UI or calls from the mobile client.
- Production or real athlete data.
- Service-role, secret, database-password, or personal-access-token handling.

## Owned paths

- `docs/app/tasks/TASK-007-supabase-local-foundation.md`
- `docs/app/reviews/TASK-007-AGY.md`
- `platform/package.json`
- `platform/pnpm-lock.yaml`
- `platform/supabase/`
- `platform/README.md`

## Forbidden paths

- `platform/apps/mobile/.env.local`
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
- `platform/AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/architecture/ADR-0001-platform-boundary.md`
- `docs/app/SUPABASE-ENVIRONMENT.md`
- Supabase CLI local-development documentation
- Docker Desktop WSL 2 documentation

## Technical decisions

- Pin `supabase` in the platform root rather than installing a global CLI.
- Local Supabase files belong at `platform/supabase/`; root `supabase/` remains
  protected legacy infrastructure.
- Do not install a user Linux distribution. Docker Desktop uses its own WSL 2
  backend and exposes Docker commands to Windows.
- Local-stack verification must not print generated local keys or credentials into
  AI output or persisted logs.

## Acceptance criteria

- [ ] Supabase CLI is pinned in `platform/package.json` and the pnpm lockfile.
- [ ] `platform/supabase/config.toml` exists and belongs only to the new app.
- [ ] Local runtime state is ignored and no credential is committed.
- [ ] Docker Desktop reports a Linux engine.
- [ ] The local Supabase stack starts successfully without linking a hosted
      project.
- [ ] The local stack can be stopped cleanly.
- [ ] Existing format, lint, typecheck, and unit tests pass.
- [ ] No protected legacy path, real athlete data, or remote Supabase resource is
      read or modified.
- [ ] AGY returns no blocker, high, or medium finding.

## Privacy classification

No user or health data. No hosted-project secret is needed. Local services may
generate development-only credentials at runtime; verification must suppress
their values and must not persist them in logs or review artifacts.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm exec supabase --version
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

Local-stack checks run with Docker Desktop active. Suppress `supabase start` and
`supabase status` credential output; verify success by exit code and container
health only:

```powershell
docker version
corepack pnpm exec supabase start
docker ps
corepack pnpm exec supabase stop
```

Repository checks:

```powershell
git diff --check
git status --short
git diff --name-only
```

## Dependencies and open decisions

- Docker Desktop 4.83.0 and WSL 2.7.11 are installed and verified.
- Database schema and RLS design will be a separate task with independent
  authorization-negative tests.

## Required handoff

- Clean commit SHA
- Changed files and pinned CLI version
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
