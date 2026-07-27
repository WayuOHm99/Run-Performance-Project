# TASK-008: Identity, Teams, and Membership RLS Foundation

Status: Complete

Writer: Claude Code

Reviewer: ChatGPT/Codex (read-only)

No AGY reviewer is assigned to this task.

## Goal and user value

Create the minimum authorization foundation for the two-role app so an
authenticated user can access only their own identity and the teams where they
hold an active membership. This must exist and be proven by tests before any
training or health data is introduced.

## In scope

- One timestamped migration under `platform/supabase/migrations/` that creates
  `public.profiles`, `public.teams`, and `public.team_memberships`.
- Automatic minimal profile creation after an `auth.users` insert.
- Row Level Security on all three tables, with read-only policies for the
  `authenticated` role and no access for `anon`.
- `SECURITY DEFINER` RLS helper functions in a non-exposed `private` schema.
- Synthetic, transaction-scoped pgTAP tests under
  `platform/supabase/tests/database/` covering positive controls, negative
  authorization, grants, constraints, and indexes.
- A short local database-test instruction in `platform/README.md` if needed.

## Out of scope

- Login UI or mobile authentication flow
- Invitations or email
- Client-side team or member administration
- Training plans
- RPE, feeling, pain/injury
- Workout or sleep data
- Sharing grants
- Monitoring flags
- Generated TypeScript database types
- Hosted Supabase login, link, pull, or push
- Remote migration
- Production or real athlete data
- Service-role or secret keys
- Deployment or push

## Owned paths

- `docs/app/tasks/TASK-008-identity-teams-membership-rls.md`
- `platform/supabase/migrations/`
- `platform/supabase/tests/database/`
- `platform/README.md`, only if a short local database-test instruction is
  necessary

## Forbidden paths

- `platform/supabase/config.toml`
- `platform/supabase/seed.sql`
- `platform/package.json`
- `platform/pnpm-lock.yaml`
- `platform/apps/`
- `platform/packages/`
- every `docs/app/architecture/` file
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
- `docs/app/AI-WORKING-AGREEMENT.md`
- `docs/app/architecture/ADR-0001-platform-boundary.md`
- `docs/app/SUPABASE-ENVIRONMENT.md`
- `docs/app/tasks/TASK-007-supabase-local-foundation.md`

## Approved schema

### `public.profiles`

- `id uuid` primary key referencing `auth.users(id)` on delete cascade
- `display_name text` nullable, with a non-empty and bounded-length constraint
  when set
- `created_at timestamptz not null default now()`
- A minimal profile row is created automatically after an `auth.users` insert.
- Auth metadata is never copied into `display_name`.
- No client update or delete access in this task.

### `public.teams`

- `id uuid` primary key default `gen_random_uuid()`
- `name text not null` with a non-empty and bounded-length constraint
- `created_at timestamptz not null default now()`

### `public.team_memberships`

- `id uuid` primary key default `gen_random_uuid()`
- `team_id uuid not null` referencing `teams(id)` on delete cascade
- `profile_id uuid not null` referencing `profiles(id)` on delete cascade
- `role text not null` restricted to `coach` or `athlete`
- `status text not null` restricted to `active` or `revoked`
- `created_at timestamptz not null default now()`
- `revoked_at timestamptz` nullable
- `unique (team_id, profile_id)`
- `active` requires `revoked_at is null`
- `revoked` requires `revoked_at is not null`
- Indexes supporting membership and RLS lookups

## Approved product and security decisions

1. One user may belong to multiple teams with a different role in each
   membership.
2. An athlete sees only their own profile and membership, and the row and name
   of a team where they hold an active membership. An athlete sees no roster and
   no other profile, including coach profiles.
3. An active coach sees only active membership rows and profiles in teams where
   that user holds an active coach membership.
4. A revoked user may still read their own profile and their revoked membership
   record, but loses access to the team and all other members immediately.
5. No authenticated client, including a coach, may create, update, revoke,
   promote, move, or delete teams or memberships in TASK-008.
6. A profile is created automatically, but profile editing is deferred.
7. One membership row is retained per user and team; `revoked_at` records the
   revocation. No audit-history table is part of this task.
8. Trusted deletion of `auth.users` or `teams` cascades to dependent identity and
   membership rows. No actual user or team deletion is performed outside
   transactional tests.
9. Active membership alone must never be described as sufficient for future
   health access. Future health policies must additionally require sharing
   grants.

## RLS design

- RLS is enabled on all three public tables.
- `anon` receives no access at all.
- `authenticated` receives only the minimum `SELECT` table grants.
- `authenticated` receives no `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE`.
- No permissive write policy is created.
- Authorization roles and status live in the database, not in JWT or user
  metadata, so a revocation takes effect on the next query.
- `SECURITY DEFINER` RLS helper functions live in the non-exposed `private`
  schema, never in `public` or `graphql_public`.
- Helper functions use a fixed empty `search_path` and fully-qualified object
  names.
- Unnecessary `PUBLIC` and `anon` function access is revoked; only what the
  policies need is granted.
- `team_memberships` policies are non-recursive: membership lookups run inside
  `SECURITY DEFINER` helpers.
- The exposed schemas in `config.toml` remain `public` and `graphql_public`;
  `config.toml` is not modified.
- Policies use the `select auth.uid()` form.
- No broad health-data authorization helper is created.

### Required visibility

- `profiles`: self; or the target holds an active membership in a team where the
  caller holds an active coach membership.
- `teams`: the caller holds an active membership in that team.
- `team_memberships`: the caller's own rows, including revoked; or active rows in
  a team where the caller holds an active coach membership.

## Acceptance criteria

- [x] One timestamped migration creates all three tables with the approved
      columns, constraints, and indexes.
- [x] An `auth.users` insert automatically creates a linked minimal profile, and
      no auth metadata is copied into `display_name`.
- [x] RLS is enabled on `public.profiles`, `public.teams`, and
      `public.team_memberships`.
- [x] `anon` holds no table privilege on the three tables.
- [x] `authenticated` holds `SELECT` only, with no `INSERT`, `UPDATE`, `DELETE`,
      or `TRUNCATE` on the three tables.
- [x] Helper functions are `SECURITY DEFINER`, use a fixed empty `search_path`,
      and live outside the exposed schemas.
- [x] Required visibility for `profiles`, `teams`, and `team_memberships`
      behaves exactly as specified.
- [x] A revoked user retains read access to their own profile and their own
      revoked membership row, and loses everything else on the next query.
- [x] A user who is a coach in one team and an athlete in another receives coach
      visibility only in the coached team.
- [x] No authenticated write to teams or memberships succeeds, including
      self-insert, role change, status change, `team_id` or `profile_id` change,
      and cross-team update or delete.
- [x] The pgTAP suite passes with positive controls and all listed negative
      assertions, using synthetic transaction-scoped fixtures only.
- [x] `supabase db lint` reports no warning or error for `public` and `private`.
- [x] Format, lint, typecheck, and unit tests pass.
- [x] No credential, API URL, JWT secret, database URL, container log containing
      keys, or real user data is printed or persisted.
- [x] No forbidden path is modified.

## Privacy classification

No real user data and no health data. Identity structure only: profile id,
optional display name, team name, and membership role and status. All fixtures
are synthetic and transaction-scoped, use `example.test` addresses, and are
rolled back. No service-role key is used or printed. Local Supabase credentials
must never be printed or persisted; `supabase status` and `db:status` are not run
in this task.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm exec supabase --version
docker version --format '{{.Server.Os}}'
```

Start the local stack while suppressing credential output and report only the
exit code:

```powershell
corepack pnpm db:start *> $null
"start exit: $LASTEXITCODE"

docker ps --format '{{.Names}} {{.Status}}'
```

Rebuild only the local database, then run the database checks:

```powershell
corepack pnpm exec supabase db reset --local --no-seed
corepack pnpm exec supabase test db --local
corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning
```

Run the workspace checks:

```powershell
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

Stop the local stack while suppressing credential output and report only the
exit code, then confirm no Supabase container remains:

```powershell
corepack pnpm db:stop *> $null
"stop exit: $LASTEXITCODE"

docker ps -a --filter 'name=supabase_' --format '{{.Names}} {{.Status}}'
```

Repository checks:

```powershell
git diff --check
git status --short
git diff --name-only
```

`*> $null` redirects every PowerShell stream, so the API URL, anon key,
service-role key, JWT secret, and database URL printed by `supabase start` and
`supabase stop` never reach the terminal, the session transcript, or a log.
Judge start and stop success only by exit code and by `docker ps` container names
and status. Never run bare `supabase start`, `supabase stop`, or `supabase
status` while a transcript is capturing terminal output. Never run any command
with `--linked` or a remote database URL.

## Dependencies and open decisions

- TASK-007 provides the pinned Supabase CLI 2.109.1 and the local stack.
- Local Analytics remains disabled, so Supabase Studio's Logs section is empty
  locally. This does not affect TASK-008.
- Sharing grants, health tables, and their policies are a later task. Active
  membership alone is never sufficient for health access.

## Required handoff

- Clean commit SHA
- Changed files
- Acceptance criteria status
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions

## Implementation notes

### Delivered files

- `platform/supabase/migrations/20260727120000_identity_teams_membership_rls.sql`
- `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
- `platform/README.md` — a short "Database authorization tests" subsection

### Non-recursive membership policies

The `team_memberships` policy needs to ask a question about `team_memberships`
("is the caller an active coach of this team?"). Asking it in the policy
expression itself would re-enter the same policy. The three helpers are
`SECURITY DEFINER`, so their internal lookups run as the definer and are not
subject to the policies, which removes the recursion without weakening the
outer check.

### Privilege model

Supabase default privileges grant `ALL` on a new `public` table to `anon` and
`authenticated`. The migration therefore revokes those explicitly and grants
back only `SELECT` to `authenticated`. Because `anon` holds no privilege at all,
an anonymous read fails at the privilege layer with `42501` before RLS is
consulted; the tests assert that error code rather than an empty result. For the
same reason every refused authenticated write also fails with `42501`, which is
strictly stronger than an RLS row filter.

`authenticated` receives `USAGE` on `private` plus `EXECUTE` on exactly the three
read helpers, because a policy expression is evaluated as the calling role. The
signup trigger function is not executable by `authenticated`; it is granted only
to `supabase_auth_admin`, guarded by a role-existence check so the migration
stays portable.

### Empty search_path

All four functions are declared `set search_path = ''` with fully-qualified
object names. PostgreSQL stores this canonically as `search_path=""`, so the
catalog assertion accepts both spellings. The first test run failed on this
assertion alone, which confirmed the suite reports real mismatches rather than
passing vacuously; the migration was already correct.

### pgTAP extension handling

`create extension if not exists pgtap` runs inside the test transaction and is
rolled back with everything else, so pgTAP is never introduced by a migration.
The local Supabase image already provides it, so the run emits a harmless
"already exists, skipping" notice.

### Test coverage

172 assertions in one file, all passing: structure, cascade behaviour,
constraint positive controls, automatic profile creation, anonymous denial,
athlete/coach/multi-team/revoked visibility, revocation taking effect on the
next query, every refused write path, RLS and policy catalog state, grants, and
helper-function properties. Role switching is proved to be effective by the
visibility counts themselves — the owner sees eight profiles where `athlete-a`
sees one.

### Known limitation

Local Analytics remains disabled from TASK-007, so Studio's Logs section is
empty locally. This does not affect TASK-008.

### Deliberate non-goals reconfirmed

No write policy, no client-facing administration path, no generated TypeScript
types, no sharing-grant logic, and no health-data authorization helper were
added. Active membership is an identity boundary only; a future health task must
require an explicit sharing grant in addition to it.
