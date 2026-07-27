# TASK-003: Expo mobile foundation

Status: Complete

Writer: ChatGPT/Codex

Reviewer: AGY (`app-reviewer`, read-only)

## Goal and user value

Create a minimal, runnable Expo application shell for Android, iOS, and web that
demonstrates the athlete-first navigation direction and a separate coach entry
without connecting to production data or a backend.

## In scope

- Initialize a pnpm workspace rooted at `platform/`.
- Create one Expo SDK 56 application at `platform/apps/mobile/`.
- Use Expo Router and TypeScript strict mode.
- Add a small shared design-token layer inside the mobile app.
- Provide a development-only role preview leading to:
  - an Athlete Today shell;
  - a Coach Team shell.
- Use synthetic display content only.
- Add formatting, lint, typecheck, and focused test commands.
- Document local start commands and current limitations.

## Out of scope

- Authentication and real role assignment.
- Supabase, migrations, RLS, or remote services.
- Garmin, HealthKit, Health Connect, or wearable permissions.
- Real training plans, sleep values, RPE, pain, or athlete data.
- Push notifications, analytics, crash reporting, EAS, store builds, or deployment.
- Editing, moving, importing, or deleting any legacy system.

## Owned paths

- `platform/package.json`
- `platform/pnpm-workspace.yaml`
- `platform/pnpm-lock.yaml`
- `platform/.npmrc`
- `platform/.gitignore`
- `platform/README.md`
- `platform/apps/mobile/`
- `docs/app/tasks/TASK-003-expo-mobile-foundation.md`
- `docs/app/reviews/TASK-003-AGY.md`

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
- `platform/README.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/architecture/ADR-0001-platform-boundary.md`
- Expo SDK 56 documentation

## Technical decisions

- Expo SDK 56 is selected because it is the latest released stable SDK. SDK 57
  is in a documented transition period at task start.
- Node.js must be an active LTS release; the local environment uses Node 24 LTS.
- pnpm is pinned to `11.17.0` in `packageManager` and the lockfile.
- The initial shell avoids global state and server-state libraries until a user
  flow needs them.
- No runtime AI capability is included.

## Acceptance criteria

- [x] `platform/` is a valid pnpm workspace with one mobile application.
- [x] Expo configuration targets Android, iOS, and web without store identifiers.
- [x] TypeScript strict mode and Expo Router are active.
- [x] The initial screen clearly labels its role switcher as development preview.
- [x] Athlete Today is visually primary and exposes no real health value.
- [x] Coach Team is a separate shell and exposes no real team value.
- [x] Loading, empty, and error architecture is documented even if not yet wired.
- [x] Formatting, lint, typecheck, and focused tests pass.
- [x] `expo-doctor` reports no dependency compatibility issue.
- [x] No secret, generated build artifact, or real athlete data is committed.
- [x] No protected legacy path is modified.
- [x] AGY returns no blocker, high, or medium finding.

## Privacy classification

Synthetic data only. The preview may use generic identities such as `athlete-a`
but must not contain realistic health measurements or content copied from the
legacy operation.

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

Repository boundary verification:

```powershell
git diff --check
git diff --name-only HEAD
git status --short
```

## Dependencies and open decisions

- App name, bundle identifiers, icons, and brand assets remain provisional.
- Physical-device health integration will require a later development build and
  dedicated task.
- Authentication will replace the development role preview in a later vertical
  slice.

## Required handoff

- Clean commit SHA
- Changed files
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
