# TASK-005: Supabase client foundation

Status: Complete

Writer: ChatGPT/Codex

Reviewer: AGY (`app-reviewer`, read-only)

## Goal and user value

Prepare a safe, lazy Supabase client for the Expo application so later
authentication work can use the intended hosted project without embedding a
server secret, querying the database, or making configuration errors leak key
values.

## In scope

- Add the official Supabase JavaScript client and React Native auth-storage
  dependencies.
- Define and validate the two allowed mobile environment variables.
- Create a lazy singleton Supabase client.
- Configure native session persistence and foreground token refresh.
- Add offline unit tests using synthetic URLs and keys only.
- Document how the client is initialized and why it is not invoked by the preview
  screens yet.

## Out of scope

- Network requests, connection probes, database queries, or auth requests.
- Supabase CLI login/link, Management API, schemas, tables, migrations, RLS, or
  seed data.
- Login UI, user sessions, role assignment, or team membership.
- Secret keys, legacy service-role keys, database passwords, or production data.
- Reading or editing the legacy Supabase system.

## Owned paths

- `platform/apps/mobile/package.json`
- `platform/pnpm-lock.yaml`
- `platform/apps/mobile/src/lib/supabase/`
- `platform/apps/mobile/README.md`
- `docs/app/tasks/TASK-005-supabase-client-foundation.md`
- `docs/app/reviews/TASK-005-AGY.md`

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
- `docs/app/SUPABASE-ENVIRONMENT.md`
- Supabase Expo React Native quickstart
- Expo environment-variable documentation

## Technical decisions

- Mobile code accepts only `EXPO_PUBLIC_SUPABASE_URL` and
  `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.
- Environment access uses static dot notation so Expo can inline public values.
- The client is created lazily. Preview screens do not need a network-capable
  client and must remain runnable without contacting Supabase.
- Native auth sessions use AsyncStorage; web uses the browser storage selected by
  `supabase-js`.
- Validation errors identify the variable but never echo its value.

## Acceptance criteria

- [x] Dependencies are compatible with Expo SDK 56.
- [x] Environment validation accepts the intended project URL and a publishable
      key format.
- [x] Validation rejects missing values, a different project URL, secret-key
      format, and legacy JWT-key format without exposing the supplied value.
- [x] Supabase client creation is lazy and returns one singleton.
- [x] Native auth configuration persists sessions and refreshes only while the app
      is active.
- [x] Tests make no network request and use synthetic values only.
- [x] Formatting, lint, typecheck, tests, Expo Doctor, and web export pass.
- [x] No credential value, protected health data, or generated artifact is
      committed.
- [x] No protected legacy path is modified.
- [x] AGY returns no blocker, high, or medium finding.

## Privacy classification

No user or health data. Local `.env.local` is present and ignored but is a
forbidden path for the writer and reviewer. Tests use a clearly synthetic
publishable-key string.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
Push-Location apps/mobile
corepack pnpm dlx expo-doctor@latest
corepack pnpm exec expo export --platform web
Pop-Location
```

Repository checks:

```powershell
git check-ignore platform/apps/mobile/.env.local
git diff --check
git status --short
```

Credential scanning is limited to owned tracked files and must not print local
environment contents.

## Dependencies and open decisions

- SecureStore may be evaluated later for small device secrets, but Supabase
  session storage follows its current React Native guidance in this task.
- The client will first be called by the authentication vertical slice.

## Required handoff

- Clean commit SHA
- Changed files and dependency versions
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
