# TASK-009 Handoff — Authentication and Profile Onboarding

This is the sanitized handoff for the read-only reviewer (ChatGPT/Codex). It
contains no credential, key, token, database URL, hosted identifier, or real
user data. Everything below can be pasted into a review tool as-is.

```text
Task:            TASK-009 — Authentication and Profile Onboarding
Writer:          Claude Code (sole writer)
Reviewer:        ChatGPT/Codex (read-only). No AGY reviewer.
Branch:          feat/TASK-009-auth-profile-onboarding
Worktree:        isolated, locked, based on feat/mobile-foundation
Base commit:     d8857c7a145e78aac2c6db48d169dbf4c430197b
Commit SHA:      d78ccb91fd09f0a380a497a1310c16b39c24087f
```

The commit above is the implementation and task packet. This handoff document is
a documentation-only follow-up commit, as required.

## Changed files

### Database (3)

| File | Change |
| --- | --- |
| `platform/supabase/migrations/20260727130000_profile_display_name_self_update.sql` | new |
| `platform/supabase/tests/database/002_profile_display_name_self_update_test.sql` | new, 43 assertions |
| `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql` | 3 assertions changed, plan 172 → 173 |

The TASK-008 **migration** was not edited. Only its test file changed, and only
where TASK-009 intentionally made an assertion obsolete.

### Mobile — pure logic, fully unit-tested (9)

`src/features/auth/`: `roles.ts`, `gate.ts`, `session.ts`, `credentials.ts`,
`display-name.ts`, `submission.ts`, `errors.ts`
`src/lib/query/`: `keys.ts`, `client.ts`

### Mobile — integration (6)

`src/features/auth/auth-repository.ts`, `auth-provider.tsx`
`src/features/profile/account-repository.ts`, `use-account.ts`
`src/lib/supabase/app-client.ts`, `database.types.ts` (generated, local only)

### Mobile — screens and components (15)

`src/app/`: `_layout.tsx`, `index.tsx`, `loading.tsx`, `sign-in.tsx`,
`sign-up.tsx`, `check-email.tsx`, `onboarding.tsx`, `pending.tsx`,
`choose-role.tsx`, `profile.tsx`, `athlete/index.tsx`, `coach/index.tsx`
`src/components/`: `text-field.tsx`, `primary-button.tsx`, `screen-heading.tsx`,
`notice.tsx`

### Tests (11 files, 187 assertions)

Alongside each pure module, plus `auth-repository.test.ts`,
`account-repository.test.ts`, `query/keys.test.ts`, `query/client.test.ts`, and
`src/test-support/capture-error.ts`.

### Dependencies and docs

| File | Change |
| --- | --- |
| `platform/apps/mobile/package.json` | `+ @tanstack/react-query 5.101.4` |
| `platform/pnpm-lock.yaml` | regenerated for the above |
| `platform/apps/mobile/README.md` | routes, authorization boundary, type generation, state rules |
| `docs/app/tasks/TASK-009-authentication-profile-onboarding.md` | new task packet |

### Removed

`src/features/role-preview/` — superseded by real authentication.

## Acceptance criteria

All 26 criteria in the task packet are met and checked. The security-relevant
ones:

| Criterion | Where it is enforced and proved |
| --- | --- |
| `/athlete` and `/coach` fail closed in every non-ready state | `canEnterRoleArea` returns true only for `ready`; gate test iterates all 7 non-ready states |
| Roles come only from active membership rows | `resolveAuthorizedRoles`; never from metadata, JWT, storage, or the chooser |
| A revoked membership disappears on the next load | `resolveAuthorizedRoles` filters `status !== 'active'`; gate test asserts before/after |
| An error is never treated as "no membership" | repository raises instead of returning `[]`; gate checks error before counting; 4 dedicated tests |
| A corrupt session fails closed | `readAuthenticatedIdentity` returns `null` for 12 malformed shapes |
| Sign-up sends no role or metadata | test pins the payload keys to exactly `["email", "password"]` |
| Errors cannot enumerate accounts | unknown account, wrong password, and already-registered all map to one category |
| Query keys are user-scoped, cache never on disk | `keys.ts`, `client.ts`, and their tests |
| `id`/`created_at` non-updatable | column-level grant; pgTAP asserts `42501` |

## Commands run and results

Local database only. No `--linked`, no remote URL, no hosted Auth.

| Command | Result |
| --- | --- |
| `pnpm install --frozen-lockfile` | exit 0 |
| `pnpm db:start *> $null` | exit 0, 10 containers healthy |
| `supabase db reset --local --no-seed` | exit 0, both migrations applied |
| `supabase test db --local` | **PASS — 216 assertions, 2 files** |
| `supabase db lint --local --schema public,private --fail-on warning` | exit 0, no schema errors |
| `pnpm format:check` | exit 0 |
| `pnpm lint` | exit 0 |
| `pnpm typecheck` | exit 0 |
| `pnpm test` | **187 passed, 12 files** |
| `expo-doctor@latest` | **21/21 checks passed** |
| `expo export --platform web` | exit 0, 13 static routes |
| `pnpm db:stop *> $null` | exit 0, no container remains |
| `git check-ignore .../.env.local` | ignored |
| `git diff --check` | clean |

`supabase start`/`stop` output was fully redirected, so no API URL, anon key,
service-role key, JWT secret, or database URL reached the terminal or any log.
`supabase status` and `db:status` were not run. The web export ran with
`EXPO_NO_DOTENV=1` plus synthetic public values, so the local `.env.local` never
entered the process and no real key could reach a build artifact.

Two rounds of genuine failures were found and fixed before the results above:
the first pgTAP run failed on four points (an illegal data-modifying CTE in a
scalar subexpression, a column-grant assertion that had not accounted for
per-column SELECT rows, and two error codes asserted as `23514` that are
actually `42501`), and ESLint rejected a `setState` inside an effect, which was
resolved by deriving the check-email flag instead of storing and resetting it.

## Privacy and security impact

**Classification: PII only. No health data.** No RPE, feeling, pain/injury,
sleep, heart rate, or workout value is read, written, logged, or displayed.

The data involved is an email address, a user id, and a self-chosen display
name.

- Passwords, access tokens, refresh tokens, and session objects are never
  logged, never placed in an error message, and never stored outside the
  Supabase auth storage adapter. Only the user id is lifted out of a session.
- The password is never trimmed, lower-cased, or otherwise transformed;
  whitespace is legitimate password content. Only the email is normalized.
- Credentials live in component state and are cleared after every completed
  attempt.
- All user-facing error text is a fixed generic Thai string from a closed set.
  Raw errors, server messages, status codes, request payloads, and
  account-existence details never reach the UI.
- The query cache is in-memory only, scoped per user id, and dropped outright on
  any identity change, so no data can cross between accounts on a shared device.
- The database change is a strict narrow addition: one column-level grant and
  one self-scoped policy. `anon` gained nothing, no membership write path was
  opened, and no service-role policy, JWT role claim, or metadata role exists.
- All fixtures are synthetic and use `example.test` addresses.
- No hosted user account was created, no hosted Supabase resource was contacted,
  and no service-role or secret key was used.

## Known limitations

1. **SecureStore hardening is mandatory before pilot release, and before any
   health data is added.** Supabase session tokens persist in AsyncStorage,
   which is not encrypted at rest on device. This is acceptable only because
   TASK-009 handles no health data. Carrying it into a build that touches RPE,
   pain/injury, sleep, heart rate, or workout data would be a privacy
   regression. This is the single most important follow-up.
2. Email confirmation has no deep-link handler. A confirming user must return to
   the app and sign in manually. Hosted Auth and email configuration were not
   changed, as required.
3. No password reset, change-email, or account-deletion flow yet.
4. Membership state is read on load and on explicit retry, not live-subscribed.
   A revocation takes effect in the database immediately but in the UI on the
   next successful load. Safe because RLS, not the client, is the authorization
   boundary.
5. Verification is mock-and-local-database only. There is no end-to-end evidence
   against the hosted project.
6. The athlete and coach shells remain empty-state placeholders. This task
   delivers the way in, not what is inside.
7. No render/component test exists, by approved decision. Screens are
   deliberately thin so the tested pure functions carry the behaviour.

## Rollback

1. Revert the branch; nothing depends on it. Nothing was merged, pushed, or
   deployed, and the branch and worktree are left in place.
2. Database only, to restore the exact TASK-008 privilege state:

   ```sql
   drop policy profiles_update_self on public.profiles;
   revoke update (display_name) on table public.profiles from authenticated;
   ```

3. Reverting restores `platform/apps/mobile/package.json` and
   `platform/pnpm-lock.yaml`; run `corepack pnpm install --frozen-lockfile`
   afterwards to drop `@tanstack/react-query`.
4. Nothing exists outside this repository to undo: no remote migration, no
   deployment, no hosted account, no push.

## Reviewer findings remaining

None. No review has been performed yet — this is the first submission.

### Suggested review focus

1. The migration and `002_..._test.sql`, especially the two refusal shapes: an
   ungranted column raises `42501`, while a row excluded by the policy's `USING`
   is filtered and affects zero rows without raising. Confirm the zero-row
   assertions are the right shape rather than a weakened test.
2. The three changed assertions in the TASK-008 test file — whether each is
   genuinely obsolete rather than quietly relaxed.
3. `resolveAuthGate` ordering in `gate.ts`: restoration before everything, and
   the error check before the membership count.
4. Whether any path could still let a role reach the UI from somewhere other
   than an active membership row.
5. `errors.ts`, for any category that could leak account existence.
