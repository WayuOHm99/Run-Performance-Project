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
- `platform/.prettierignore`

`platform/.prettierignore` was added to this list by Product Owner approval during
implementation. Ownership is limited to ignoring `platform/supabase/.temp/` and
`platform/supabase/.branches/`. Any other formatter-ignore rule needs its own task.

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
docker version --format '{{.Server.Os}}'

corepack pnpm db:start *> $null
"start exit: $LASTEXITCODE"

docker ps --format '{{.Names}} {{.Status}}'

corepack pnpm db:stop *> $null
"stop exit: $LASTEXITCODE"

docker ps -a --filter 'name=supabase_' --format '{{.Names}} {{.Status}}'
```

`*> $null` redirects every PowerShell stream, so the API URL, anon key,
service-role key, JWT secret, and database URL printed by `supabase start` and
`supabase stop` never reach the terminal, the session transcript, or a log.

Judge success only by the reported exit codes and by the container names and
status from `docker ps`. Every listed container must read `Up` and, where the
image defines a health check, `(healthy)`. No container may read `Restarting` or
`(unhealthy)`. The final `docker ps -a` must return nothing, confirming a clean
stop.

Never run bare `supabase start`, `supabase stop`, or `supabase status` while an AI
session or any transcript is capturing terminal output. `corepack pnpm db:status`
is for local human inspection only; its output is credential-bearing and must not
be pasted into a task packet, review artifact, commit, or AI prompt.

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
  `supabase start`, `supabase stop`, or `supabase status` credential output was
  printed or persisted.
- Local Analytics is disabled in `platform/supabase/config.toml`
  (`[analytics] enabled = false`). Logflare and its Vector log collector are not
  required for TASK-007 or for future database and RLS tests, and the Vector
  container restart-looped on Docker Desktop's WSL 2 backend. With Analytics off,
  the stack starts fully clean. Re-enable only in a task that actually needs local
  log aggregation.
- `git status --short` while the stack was running showed only the intended file
  modifications, confirming no local runtime state reaches the repository.
- Added `platform/.prettierignore`. Running the stack generates
  `platform/supabase/.temp/`, which Git already ignores through
  `platform/supabase/.gitignore`, but Prettier reads only top-level ignore files
  and therefore failed `format:check` after every `supabase start`. This keeps the
  in-scope item "keep generated local runtime state ignored" true for the formatter
  as well as for Git. The Product Owner approved adding this path to the owned-path
  list, limited to the two generated Supabase directories; the file contains no
  other rule.

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

### Resolved review finding M1 — Vector restart loop

Codex independently reproduced `supabase_vector_platform` sitting in
`Restarting (0)` on this Windows/WSL 2 host while every other service was healthy
and start/stop both exited 0.

Fixed by setting `[analytics] enabled = false` in `platform/supabase/config.toml`,
which removes the Logflare and Vector containers from the local stack entirely
rather than tolerating a restart loop.

After the change the stack starts with ten containers — `db`, `auth`, `rest`,
`kong`, `storage`, `realtime`, `pg_meta`, `studio`, `edge_runtime`, `inbucket` —
all reporting `Up`, with `(healthy)` on every image that defines a health check.
No container reports `Restarting` or `(unhealthy)`. `rest` and `edge_runtime`
expose no health check, which is normal for those images. Container logs were
never dumped, because the Vector configuration carries a generated local analytics
key.

### Resolved review finding M2 — unsafe verification example

The Verification block previously showed bare `supabase start` and `supabase stop`,
which would print the API URL, anon key, service-role key, JWT secret, and database
URL into any capturing terminal or transcript. The block now redirects both with
`*> $null`, checks `$LASTEXITCODE`, and judges health from `docker ps` container
names and status. It also states explicitly that `db:status` output is
credential-bearing and must never be pasted into a packet, review artifact, commit,
or AI prompt.

### Known limitation

Local log aggregation is unavailable while Analytics is disabled. Supabase Studio's
Logs section will be empty locally. This does not affect the hosted project, and
nothing in TASK-007 or the planned schema/RLS work depends on it.

## Required handoff

- Clean commit SHA
- Changed files and pinned CLI version
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
