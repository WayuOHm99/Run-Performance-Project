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

Directories will be created only when an accepted task needs them. This avoids
empty scaffolding that has no tested user outcome.

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

Future JavaScript commands will run from `platform/` with pnpm. No package manager
or framework has been initialized by the boundary task.
