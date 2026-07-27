# TASK-004: Configure project identity safely

Status: Complete

Writer: ChatGPT/Codex

Reviewer: AGY (`app-reviewer`, read-only)

## Goal and user value

Bind the local repository to the Product Owner's empty GitHub repository and
document the hosted Supabase project for future mobile integration without
committing, logging, or using any API secret.

## In scope

- Configure the local Git `origin` URL.
- Record the non-secret Supabase project name, reference, and API URL.
- Add a mobile `.env.example` containing the public URL and a placeholder for the
  current publishable key.
- Document local environment setup and the client/server key boundary.
- Verify that local environment files are ignored.

## Out of scope

- Pushing or fetching application code.
- Linking Supabase CLI or contacting the database.
- Adding Supabase libraries or initializing a runtime client.
- Creating schemas, tables, migrations, RLS policies, users, or seed data.
- Storing a publishable, secret, legacy anon, or service-role key in Git.
- Reading or editing the legacy Supabase system.

## Owned paths

- `platform/apps/mobile/.env.example`
- `platform/apps/mobile/README.md`
- `docs/app/SUPABASE-ENVIRONMENT.md`
- `docs/app/tasks/TASK-004-project-identity.md`
- `docs/app/reviews/TASK-004-AGY.md`
- Local Git configuration for `remote.origin.url` (not committed)

## Forbidden paths

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
- Supabase API key documentation
- Expo environment-variable documentation

## Project identity

- GitHub owner: `WayuOHm99`
- GitHub repository: `Run-Performance-Project`
- Supabase project name: `Run-performance-Project`
- Supabase project reference: `altlphxckxsudnuwhqfw`
- Supabase API URL: `https://altlphxckxsudnuwhqfw.supabase.co`

These identifiers and the API URL are not secrets.

## Acceptance criteria

- [x] Local `origin` equals the intended GitHub HTTPS URL.
- [x] `.env.example` contains no real API key or server secret.
- [x] The mobile environment contract uses only `EXPO_PUBLIC_SUPABASE_URL` and
      `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.
- [x] `.env` and `.env.local` are ignored by Git.
- [x] Documentation forbids secret and service-role keys in mobile code.
- [x] No Supabase database or Management API operation is performed.
- [x] No protected legacy path is modified.
- [x] AGY returns no blocker, high, or medium finding.

## Privacy classification

No user or health data. The task handles public project identifiers only. A
previously disclosed server credential was revoked by the Product Owner before
this task began and is not copied or reused.

## Verification

```powershell
git remote get-url origin
git check-ignore --no-index platform/apps/mobile/.env
git check-ignore --no-index platform/apps/mobile/.env.local
git diff --check
git status --short
```

Secret-pattern scanning is limited to the task's owned repository files and must
report no JWT, secret-key value, or private key.

## Dependencies and open decisions

- The Product Owner will place the current publishable key in an ignored local
  file immediately before the Supabase client integration task.
- GitHub authentication and the first push require separate explicit approval.

## Required handoff

- Clean commit SHA
- Local remote URL
- Changed files
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
