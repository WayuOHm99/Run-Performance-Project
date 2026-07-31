# Run Performance Platform

This directory is the isolated workspace for the new athlete-and-coach product.
All new application code, app-specific backend code, shared contracts, tests, and
tooling belong here.

## Intended structure

```text
platform/
├─ apps/
│  └─ mobile/          Expo app for athlete and coach roles
├─ packages/
│  ├─ contracts/       Shared schemas and API contracts
│  ├─ domain/          Pure business rules
│  ├─ ui/              Shared presentation components
│  └─ test-fixtures/   Synthetic data only
├─ supabase/
│  ├─ migrations/      New app database migrations
│  ├─ functions/       New app edge functions
│  └─ tests/           RLS and authorization tests
└─ tooling/            App-only development tooling
```

The mobile application now lives at `apps/mobile/`. Other directories will be
created only when an accepted task needs them. This avoids empty scaffolding that
has no tested user outcome.

## Boundary

The following repository-root paths are part of the live legacy operation and
are not dependencies of this workspace:

- `athletes/`
- `team_data/`
- `garmin/`
- `scripts/`
- root `supabase/`
- root `CLAUDE.md`

Do not import from, write to, move, or copy data from those paths. If the new app
needs a legacy capability later, define a sanitized contract and adapter in a
dedicated task instead of coupling directly to legacy files.

## Data rule

Development, tests, screenshots, logs, and AI reviews use synthetic identities
such as `athlete-a` only. Secrets and real health values never belong in this
directory.

## Commands

Run JavaScript commands from `platform/` with the pinned pnpm version:

```powershell
corepack pnpm install
corepack pnpm --filter @run-performance/mobile start
```

The first mobile shell is a development preview only. It has no authentication,
backend, wearable connection, production data, deployment configuration, or store
identifier.

## Local Supabase stack

The Supabase CLI is pinned as a `platform/` development dependency. Do not install
a global CLI; the pinned version is the only supported one.

`platform/supabase/` is the new app's backend. The repository-root `supabase/`
directory is a different, live legacy system and is never touched by these
commands.

### Windows prerequisites

- Docker Desktop with the WSL 2 backend, running before any stack command.
- Node.js 22–24 with Corepack enabled.
- No user Linux distribution is required. Docker Desktop provides its own WSL 2
  backend and exposes `docker` to Windows.

Confirm Docker is up and using a Linux engine:

```powershell
docker version --format '{{.Server.Os}}'
```

The value must be `linux`.

### Safe local commands

Run from `platform/`:

```powershell
corepack pnpm db:start
corepack pnpm db:status
corepack pnpm db:stop
```

The stack is entirely local. It never links, logs in to, or migrates the hosted
Supabase project. `supabase login`, `supabase link`, `supabase db push`, and any
other remote command are out of bounds for local development work.

### Database authorization tests

Row Level Security and grant behaviour are covered by pgTAP tests in
`platform/supabase/tests/database/`. With the local stack running, run from
`platform/`:

```powershell
corepack pnpm exec supabase db reset --local --no-seed
corepack pnpm exec supabase test db --local
corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning
```

`db reset` rebuilds only the local database from `supabase/migrations/`. Every
fixture is synthetic, transaction-scoped, and rolled back, so no seed file or
persistent test data is needed. These commands are local-only; never add
`--linked` or a remote database URL.

### Local app demo

`docs/app/LOCAL-DEMO.md` is the full guide. In short, from `platform/`:

```powershell
corepack pnpm demo:reset     # rebuild the synthetic baseline (destructive, local only)
corepack pnpm demo:web       # launch Web         (resets nothing)
corepack pnpm demo:android   # launch Android Emulator (resets nothing)
corepack pnpm demo:stop      # stop this project only
```

The baseline is two `example.test` accounts, one team, one active athlete
membership, one active coach membership, and — deliberately — **zero sharing
grants and zero check-ins**. Consent is never seeded; the whole point of the demo
is to grant and revoke it yourself through the real UI.

`demo:reset` is the only destructive command, and it is destructive only to the
local Supabase project. Launching the app never resets or reseeds. None of these
commands read or modify `apps/mobile/.env.local`.

The demo tooling lives in `tooling/local-demo/` and has its own unit tests:

```powershell
corepack pnpm test:tooling
```

### Credential hygiene

`supabase start` and `supabase status` print development-only API keys and a
database URL to the terminal. Those values are generated locally and are not
hosted-project secrets, but they must not be pasted into an AI chat, a task
packet, a review artifact, a screenshot, or a committed log.

When a command's output could be captured, suppress it and check the exit code
and container health instead:

```powershell
corepack pnpm db:start *> $null
$LASTEXITCODE
docker ps
```

Generated local runtime state is ignored through `platform/supabase/.gitignore`
and `platform/.prettierignore`; Docker volumes live outside the repository.
Nothing produced by the local stack belongs in a commit.

### Disabled local services

`[analytics] enabled = false` in `platform/supabase/config.toml`. Logflare and its
Vector log collector are not needed for database or authorization work, and the
Vector container restart-loops on Docker Desktop's WSL 2 backend. The trade-off is
that Studio's local Logs section stays empty. Re-enable it only in a task that
genuinely needs local log aggregation.
