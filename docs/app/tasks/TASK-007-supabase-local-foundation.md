# TASK-007: Supabase local development foundation

Status: In Progress — implementation complete, awaiting final read-only review

Writer: Claude Code

Reviewer: ChatGPT/Codex (read-only after ownership transfer)

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

- [x] Supabase CLI is pinned in `platform/package.json` and the pnpm lockfile.
- [x] `platform/supabase/config.toml` exists and belongs only to the new app.
- [x] Local runtime state is ignored and no credential is committed.
- [x] Docker Desktop reports a Linux engine.
- [x] The local Supabase stack starts successfully without linking a hosted
      project.
- [x] The local stack can be stopped cleanly.
- [x] Existing format, lint, typecheck, and unit tests pass.
- [x] No protected legacy path, real athlete data, or remote Supabase resource is
      read or modified.
- [ ] ChatGPT/Codex returns no blocker, high, or medium finding in the final
      read-only review.

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

## Ownership transfer

- ChatGPT/Codex created the task, pinned Supabase CLI 2.109.1, initialized
  `platform/supabase/`, and completed the clean checkpoint commit
  `432d229a3a5682e3810a6eb05632271368986d77`.
- Claude Code is the sole writer for all work after this checkpoint.
- ChatGPT/Codex becomes read-only for review after the transfer. Any accepted
  finding must be fixed by Claude Code.

## Implementation notes

- Pinned CLI verified at `supabase 2.109.1` via `corepack pnpm exec supabase
  --version`.
- Added `db:start`, `db:stop`, and `db:status` scripts to `platform/package.json`.
  They resolve the pinned local CLI; no global install is used.
- `platform/README.md` documents the Windows prerequisites, the safe local
  commands, and the credential-suppression pattern.
- Local-stack verification used exit codes and `docker ps` health only. No
  `supabase start` or `supabase status` credential output was printed or
  persisted.
- `git status --short` while the stack was running showed only the intended file
  modifications, confirming no local runtime state reaches the repository.
- Added `platform/.prettierignore`. Running the stack generates
  `platform/supabase/.temp/`, which Git already ignores through
  `platform/supabase/.gitignore`, but Prettier reads only top-level ignore files
  and therefore failed `format:check` after every `supabase start`. This file is
  outside the literal owned-path list; it was required to keep the in-scope item
  "keep generated local runtime state ignored" true for the formatter as well as
  for Git.

### Pre-existing formatting defect fixed

`corepack pnpm format:check` failed on all 26 workspace files before any change in
this task. The cause was line endings only: the repository sets
`core.autocrlf=true`, so the Windows checkout holds CRLF, while Prettier defaults
to `endOfLine: "lf"`. `prettier --check --end-of-line auto .` passed cleanly,
confirming no file had a real style problem.

The minimal fix was a `prettier` config block in the owned `platform/package.json`
setting `endOfLine: "auto"`. This is scoped to the platform workspace and avoids a
repository-root `.gitattributes` change, which would renormalize legacy files and
is out of scope here.

### Known limitation

`supabase_vector_platform`, the log-collector sidecar, enters a restart loop on
this Windows/WSL 2 host (repeated exit code 0). `supabase start` still returns exit
0, and every service required for database and authorization work —
`db`, `auth`, `rest`, `kong`, `storage`, `realtime`, `pg_meta`, `studio`,
`analytics`, `inbucket` — reports healthy. This affects local log aggregation
only. Container logs were not dumped, because the vector configuration carries a
generated local analytics key.

## Required handoff

- Clean commit SHA
- Changed files and pinned CLI version
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
