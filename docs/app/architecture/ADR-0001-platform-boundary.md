# ADR-0001: Isolate the New App Platform

Status: **Accepted**

Date: 2026-07-27

## Context

This repository already runs a Python/Streamlit Garmin pipeline, a LINE ingestion
pipeline, Windows scheduled tasks, and a legacy Supabase Edge Function. It also
contains ignored credentials and real athlete health data.

The new product needs an Expo workspace, shared TypeScript packages, Supabase
migrations, and mobile build configuration. Initializing those at the repository
root or reusing root `supabase/` would blur ownership and could disrupt the current
operation.

## Decision

Create the new product inside one isolated subtree:

```text
platform/
  package.json
  pnpm-workspace.yaml
  pnpm-lock.yaml
  apps/
    mobile/
  packages/
    domain/
    config/
  supabase/
```

Additional decisions:

- Do not create a root `package.json` or root JavaScript lockfile.
- Do not run `supabase init` at repository root.
- Root `supabase/` remains the legacy LINE webhook.
- Use a separate Supabase Free project for the app pilot while the legacy backend is
  still active.
- Do not import the existing Garmin SQLite database or athlete folders into the app
  backend.
- Initial app development uses synthetic fixtures only.
- Integration with current operations requires a future explicit ADR and migration
  plan.

## Consequences

Benefits:

- Existing automations remain stable.
- AI task ownership can be restricted to `platform/`.
- Node dependencies and native build files do not pollute the Python system.
- The new database can start with reviewed migrations and RLS from day one.
- A failure in the new app cannot overwrite the current LINE Edge Function.

Trade-offs:

- Some repository-level tooling must run from `platform/`.
- CI will need separate jobs for the legacy system and the mobile platform.
- Reusing selected legacy data later requires a deliberate export/import contract.

## Rollback

Before the app is connected to a remote backend, rollback consists of removing the
`platform/` subtree and these app-specific documents. No legacy runtime file needs
to change.
