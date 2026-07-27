# TASK-009: Authentication and Profile Onboarding

Status: In Progress

Writer: Claude Code

Reviewer: ChatGPT/Codex (read-only)

No AGY reviewer is assigned to this task.

## Goal and user value

Allow a user to sign up or sign in with email/password, establish and restore a
Supabase session, set their own display name, and enter only the role areas
authorized by active memberships returned by the backend.

This is the first vertical slice that calls the Supabase client created in
TASK-005 against the authorization foundation created in TASK-008.

## In scope

- Email/password sign-up and sign-in against Supabase Auth.
- Session restoration on app start with a neutral loading state.
- A profile onboarding step that requires a valid `display_name`.
- Loading only the caller's own profile and memberships through RLS.
- Role routing derived from active memberships returned by the database.
- An authorized role chooser for a dual-role user.
- A pending/no-active-team state for a user without an active membership.
- Authenticated profile editing and global sign-out.
- Expo Router protected routes that fail closed.
- TanStack Query for server state, with auth-bound keys, cache clearing on user
  change and sign-out, and no on-disk persistence.
- TypeScript database types generated from the local Supabase stack only.
- One timestamped migration granting self-only `UPDATE (display_name)` on
  `public.profiles`, with pgTAP authorization-negative tests.
- Pure-logic unit tests with a mocked Supabase client.
- A sanitized handoff at `docs/app/handoffs/TASK-009.md`.

## Out of scope

- Changing hosted Supabase Auth or email configuration.
- Email-confirmation deep links or redirect handling.
- Password reset, magic link, OAuth, anonymous sign-in, or passkeys.
- Team or membership administration, invitations, and role assignment.
- Migrating Supabase session storage to SecureStore.
- Training plans, check-ins, RPE, feeling, pain/injury, workouts, sleep.
- Sharing grants and monitoring flags.
- React Hook Form and Zod adoption.
- Component/render tests and any component-test dependency.
- Creating or accessing a hosted user account.
- Hosted Supabase login, link, pull, push, or remote migration.
- Deployment, store submission, `git push`, branch deletion, worktree cleanup.

## Owned paths

- `docs/app/tasks/TASK-009-authentication-profile-onboarding.md`
- `docs/app/handoffs/TASK-009.md`
- `platform/apps/mobile/package.json`
- `platform/pnpm-lock.yaml`
- `platform/apps/mobile/README.md`
- `platform/apps/mobile/src/app/`
- `platform/apps/mobile/src/components/`
- `platform/apps/mobile/src/features/auth/`
- `platform/apps/mobile/src/features/profile/`
- `platform/apps/mobile/src/features/role-preview/` (removal only; superseded)
- `platform/apps/mobile/src/lib/supabase/`
- `platform/apps/mobile/src/lib/query/`
- `platform/apps/mobile/src/test-support/`
- `platform/supabase/migrations/`
- `platform/supabase/tests/database/`

## Forbidden paths

- `platform/apps/mobile/.env.local`
- `platform/supabase/config.toml`
- `platform/supabase/seed.sql`
- `platform/supabase/migrations/20260727120000_identity_teams_membership_rls.sql`
  (the TASK-008 migration; never edited)
- `platform/package.json`
- `platform/packages/`
- every `docs/app/architecture/` file
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
- `docs/app/SUPABASE-ENVIRONMENT.md`
- `docs/app/CLAUDE-CODE-SETUP.md`
- `docs/app/tasks/TASK-005-supabase-client-foundation.md`
- `docs/app/tasks/TASK-008-identity-teams-membership-rls.md`

## Approved product and security decisions

1. Support email/password sign-up and sign-in.
2. New accounts receive no role or membership automatically.
3. Handle both sign-up outcomes: a session returned immediately, and a `null`
   session because email confirmation is required. Do not change hosted Auth or
   email configuration.
4. Require a valid `display_name` before entering a role area.
5. A dual-role user may select only roles represented by active memberships
   returned by the database.
6. A revoked/no-membership user may edit their own display name but may not
   enter athlete or coach areas.
7. Sign-out uses global Supabase sign-out.
8. Retain the existing AsyncStorage Supabase session adapter for this task.
   **SecureStore hardening is mandatory before pilot release or before health
   data is added.** See "Known limitations".
9. Verification uses mocks and the local database only. Do not create or access
   a hosted user account.
10. Write a sanitized handoff to `docs/app/handoffs/TASK-009.md` so the Product
    Owner does not need to copy the terminal handoff into Codex.

### Decision resolved during implementation

11. **TASK-009 owns one new migration.** TASK-008 granted `authenticated`
    `SELECT` only and explicitly deferred profile editing, so decisions 4, 6 and
    11 of the required flow are impossible against that schema. The Product
    Owner approved adding a migration that grants self-only
    `UPDATE (display_name)`. The TASK-008 migration itself is never edited.

## Required user flow

1. Restore session when the app starts.
2. Show a neutral loading state until restoration completes. Do not flash a
   protected route or the sign-in screen prematurely.
3. No session: show sign-in, and provide navigation to sign-up.
4. Sign-up: email/password only; no user metadata, `display_name`, role, team,
   or membership is sent. If no session is returned, show a generic check-email
   state. No confirmation deep-link implementation in this task.
5. Authenticated user with a missing `display_name`: require profile onboarding
   before role routing.
6. After profile onboarding: load only the caller's profile and active
   memberships through RLS.
7. No active membership: show a pending/no-active-team state; allow profile
   editing and sign-out; do not expose athlete or coach routes.
8. Athlete role only: allow the athlete shell; deny coach routes.
9. Coach role only: allow the coach shell; deny athlete routes.
10. Both roles: show an authorized role chooser built only from active
    memberships. Do not persist the selected role as an authorization claim.
11. Provide authenticated profile editing and global sign-out.

## Routing and security requirements

- Use Expo Router protected routes appropriate for the installed Router version
  (`expo-router ~56.2.16`, which supports `Stack.Protected`).
- Client route guards are UX protection only. PostgreSQL grants and RLS remain
  the authorization boundary.
- Direct navigation to `/athlete` or `/coach` must fail closed unless the
  restored session and current active memberships authorize that role.
- A network/profile/membership error must show a recoverable retry state, and
  must never be treated as "no active membership".
- A revoked membership must disappear from role resolution after the next
  successful refresh/query.
- Role resolution must be a pure, independently tested function.
- Never derive a role from auth metadata, email, local storage, or a UI choice.
- Query/cache keys must include the authenticated user id.
- Clear all auth-bound TanStack Query data when the user changes or signs out.
- Do not persist the query cache to disk.

## Authentication requirements

- Use the existing lazy Supabase client.
- Use `signUp()`, `signInWithPassword()`, session restoration, and
  `onAuthStateChange()`.
- Do not store email/password outside live form state.
- Trim and lower-case the email only; never trim or transform the password.
- Prevent duplicate submissions and clear password state after success or leave.
- Map server errors to short generic Thai messages.
- Never expose raw errors, account-existence details, tokens, request payloads,
  email, password, user id, profile, membership, or server error objects.
- A corrupt/unreadable restored session must fail closed to signed-out.
- Clean up auth event subscriptions.
- Avoid async re-entrant Supabase Auth calls inside auth-state callbacks.

### Added after the Codex review (M1, M2)

- An existing-email sign-up response must not produce an outcome observably
  different from the generic check-email outcome. Where the server makes a
  distinction unavoidable, document it precisely instead of claiming complete
  enumeration resistance.
- The restored JWT must be validated with `getClaims()` before an authenticated
  identity is exposed. The identity comes from the verified `sub` claim, never
  from the stored `user.id`.
- A malformed, expired, unverifiable, or mismatched session fails closed.
- No protected route may render while validation is pending.
- Validation is scheduled outside `onAuthStateChange`, and a stale
  restore/validation result must never overwrite a newer auth event or a
  sign-out.

## Database requirements

- Create one new migration; do not edit the TASK-008 migration.
- Grant `authenticated` `UPDATE` only on `public.profiles.display_name`.
- Add an `UPDATE` policy using both `USING` and `WITH CHECK` with `auth.uid()`.
- Retain the existing display-name constraint.
- Keep `id`/`created_at` non-updatable; profile `INSERT`/`DELETE` denied.
- Keep all `team_memberships` writes denied and `anon` with no grants.
- Do not add a service-role policy, a JWT role claim, or an auth-metadata role.

## Test requirements

- Add a focused new pgTAP test file.
- Update TASK-008's existing pgTAP file only where its former prohibition on all
  profile updates is now intentionally obsolete.
- Prove: own `display_name` update succeeds; anonymous, other-user, and
  coach-to-athlete updates fail; `id`/`created_at`, profile insert/delete, and
  all membership writes remain denied; a revoked user may update only their own
  `display_name`.
- Pure-logic unit tests only: no component-test dependency and no network.
- Test invalid input, duplicate submit, no role metadata in sign-up, both
  sign-up outcomes, sanitized errors, fail-closed session restore, route
  resolution, revoked/pending/dual-role states, and query-cache clearing.

## Generated types

- Generate and commit TypeScript database types from local Supabase only.
- Type the client and the profile/membership queries.
- Never generate from a hosted or linked Supabase project.

## Acceptance criteria

- [x] Session restoration completes before any protected route or the sign-in
      screen is rendered; a neutral loading state is shown meanwhile.
- [x] Sign-up sends email and password only, with no metadata, role, team, or
      membership.
- [x] A sign-up that returns a session proceeds; a sign-up that returns a `null`
      session shows a generic check-email state.
- [x] A user whose `display_name` is missing or blank is routed to onboarding
      and cannot reach `/athlete`, `/coach`, or the role chooser.
- [x] Authorized roles are derived only from `status = 'active'` membership rows
      returned by the database, by a pure independently tested function.
- [x] A revoked membership disappears from role resolution on the next
      successful load.
- [x] A user with no active membership sees the pending state, can edit their
      display name, and can sign out, with no athlete or coach route reachable.
- [x] An athlete-only user reaches the athlete shell and is denied `/coach`.
- [x] A coach-only user reaches the coach shell and is denied `/athlete`.
- [x] A dual-role user sees a chooser built only from active memberships, and
      the selection is not persisted as an authorization claim.
- [x] Direct navigation to `/athlete` and `/coach` fails closed for every
      non-ready state, including restoring, signed-out, onboarding, pending, and
      error.
- [x] A profile or membership load failure shows a retry state, is not treated
      as "no membership", and does not sign the user out.
- [x] Sign-out uses `signOut({ scope: "global" })` and returns to sign-in.
- [x] Auth failures show a generic Thai message, and no credential, token,
      payload, or server error value is exposed or logged.
- [x] An existing-email sign-up produces the same generic check-email outcome as
      a null-session sign-up, and never an error. Complete enumeration
      resistance holds only while email confirmation is enabled; the residual
      distinction is stated exactly in "Known limitations".
- [x] The restored JWT is verified with `getClaims()` before an authenticated
      identity exists, and the identity is taken from the verified `sub`.
- [x] A malformed, expired, unverifiable, role-mismatched, or subject-mismatched
      session fails closed to signed-out.
- [x] No protected route renders while validation is pending, including while a
      *newer* signal is being validated after an identity was already verified.
- [x] Observing a newer auth signal invalidates the previous identity
      immediately, before its validation starts.
- [x] A validation result applies only when its token is still the latest
      observed signal. Being newer than the last applied result is explicitly
      not sufficient.
- [x] A sign-out signal blocks protected routing immediately and does not wait
      for an older verification to settle.
- [x] A user-A → user-B transition never reapplies or exposes user A once the
      user-B signal has been observed.
- [x] Auth-scoped query data is cleared at the signal boundary, so it cannot be
      read for the previous identity during a pending transition.
- [x] Auth event subscriptions are cleaned up, the auth-state callback makes no
      async re-entrant Supabase Auth call, and unmounted or cancelled results
      are ignored.
- [x] Every auth-bound query key includes the authenticated user id.
- [x] Auth-bound cached data is removed when the user changes or signs out, and
      the query cache is never persisted to disk.
- [x] The migration grants only `UPDATE (display_name)` and only to the row
      owner; `anon` gains nothing.
- [x] pgTAP proves a user cannot update another user's profile, cannot change
      `id` or `created_at`, and cannot set `display_name` to `NULL` or blank.
- [x] `supabase db lint` reports no warning or error for `public` and `private`.
- [x] Database types are generated from the local stack only and the client and
      queries are typed with them.
- [x] Format, lint, typecheck, unit tests, pgTAP, Expo Doctor, and web export
      pass.
- [x] No credential, API key, database URL, or real user data is printed or
      committed.
- [x] No forbidden path is modified.

## Privacy classification

PII only: email address, user id, and a self-chosen display name. **No health
data.** No RPE, feeling, pain/injury, sleep, heart rate, or workout value is
read, written, logged, or displayed by this task.

Rules applied:

- Passwords, access tokens, refresh tokens, and session objects are never
  logged, never placed in error messages, and never written outside the Supabase
  auth storage adapter. Only the verified `sub` is lifted out, and the access
  and refresh tokens never enter React state at all.
- Auth error text shown to the user is a fixed generic Thai string chosen from a
  closed set. An unknown account, a wrong password, and an already-registered
  address all collapse to the same category, so the response cannot be used to
  enumerate registered addresses.
- The query cache holds profile and membership data in memory only, is scoped
  per user id, and is dropped on any identity change.
- All fixtures are synthetic and use `example.test` addresses.
- No hosted user account is created. No service-role or secret key is used.
- Local Supabase credentials are never printed; `supabase status` and
  `db:status` are not run.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
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

Run the mobile build checks. `EXPO_NO_DOTENV=1` keeps the local `.env.local`
out of the process entirely, and the synthetic public values below are the only
environment the export sees, so no real key can reach a build artifact:

```powershell
Push-Location apps/mobile
corepack pnpm dlx expo-doctor@latest

$env:EXPO_NO_DOTENV = "1"
$env:EXPO_PUBLIC_SUPABASE_URL = "https://altlphxckxsudnuwhqfw.supabase.co"
$env:EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_synthetic_local_verification_key"
corepack pnpm exec expo export --platform web
Pop-Location
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
git check-ignore platform/apps/mobile/.env.local
git diff --check
git status --short
git diff --name-only
```

`*> $null` redirects every PowerShell stream, so the API URL, anon key,
service-role key, JWT secret, and database URL printed by `supabase start` and
`supabase stop` never reach the terminal, the session transcript, or a log.
Judge start and stop success only by exit code and by `docker ps` container
names and status. Never run bare `supabase start`, `supabase stop`, or
`supabase status` while a transcript is capturing terminal output. Never run any
command with `--linked` or a remote database URL.

## Dependencies and open decisions

- TASK-005 provides the lazy Supabase client and environment validation.
- TASK-008 provides `profiles`, `teams`, `team_memberships`, and the read
  policies this task queries.
- TASK-007 provides the pinned Supabase CLI 2.109.1 and the local stack.
- Local Analytics remains disabled, so Studio's Logs section is empty locally.
  This does not affect TASK-009.
- Client-side minimum password length is 8, which is stricter than the local
  `minimum_password_length = 6`. The server remains the enforcing side.

## Known limitations

- **Sign-up enumeration resistance is not complete while email confirmation is
  disabled.** The Codex M1 finding — an existing address producing an *error*
  while a new one produced the check-email state — is fixed: both now produce
  the identical generic outcome, and no error is shown. What remains is
  structural rather than a code defect:

  | `enable_confirmations` | New address | Existing address | Distinguishable? |
  | --- | --- | --- | --- |
  | `true` | null session → check-email | obfuscated user, null session → check-email | **No** |
  | `false` | session returned → app enters | `user_already_exists` → check-email | **Yes** |

  With confirmations disabled, a successful sign-up necessarily signs the user
  in, and that can only happen for a new address. Hiding it would mean
  discarding a valid session and breaking approved outcome 3 ("session returned
  immediately"). Closing this properly requires enabling email confirmation,
  which is a hosted Auth configuration change and is explicitly out of scope for
  this task. `platform/supabase/config.toml` currently has
  `enable_confirmations = false`, so **the local stack is in the distinguishable
  row.** This should be revisited before pilot.

  A timing side channel also remains in both rows and is not addressed here.
- **SecureStore hardening is mandatory before pilot release or before health
  data is added.** Supabase session tokens currently persist in AsyncStorage,
  which is not encrypted at rest on device. This is accepted only because
  TASK-009 handles no health data. Carrying it into a build that touches RPE,
  pain/injury, sleep, heart rate, or workout data would be a privacy regression.
- Email confirmation has no deep-link handler. A confirming user must return to
  the app and sign in manually.
- There is no password reset, change-email, or account-deletion flow yet.
- Membership state is read on load and on explicit retry, not live-subscribed. A
  revocation takes effect in the database immediately but in the UI on the next
  successful load. This is safe because RLS, not the client, is the
  authorization boundary.
- **Every auth signal now briefly shows the neutral loading state.** Because a
  newer signal clears the identity immediately, a `TOKEN_REFRESHED` event —
  roughly hourly while the app is foregrounded — drops the user to the loading
  screen for the duration of one verification, and the auth-scoped cache is
  cleared and refetched. This is the deliberate cost of closing the exposure
  window, and the refetch has the side benefit of surfacing a revocation sooner.
  If the flash proves noticeable in use, the fix is a UI one (hold the previous
  screen's chrome while pending); it must **not** be fixed by keeping the
  previous identity live, which is exactly the defect that was corrected.
- **JWT verification may cost a network round trip.** `getClaims()` verifies
  locally against the cached JWKS only for an asymmetric signing key. If the
  project still uses a symmetric secret, it validates at the Auth server, so
  session restore requires connectivity and an offline launch fails closed to
  signed-out rather than restoring. That is the correct direction to fail, but
  it is a usability cost, and moving the project to asymmetric signing keys
  would remove it.
- If sign-in succeeds but the resulting JWT then fails verification, the user
  returns to the sign-in screen without an error message. This fails closed
  correctly but is opaque; it should be revisited if it is ever observed.
- Verification is mock-and-local-database only, so there is no end-to-end
  evidence against the hosted project and no hosted account was created.
- The role shells themselves remain empty-state placeholders. This task delivers
  the way in, not what is inside.
- No render/component test exists, by decision. Screens are deliberately thin so
  the tested pure functions carry the behaviour.

## Rollback

- Revert the feature branch; no other branch depends on it.
- The migration is additive (one column grant and one policy). To roll back the
  database alone:

  ```sql
  drop policy profiles_update_self on public.profiles;
  revoke update (display_name) on table public.profiles from authenticated;
  ```

  which restores the exact TASK-008 privilege state.
- Reverting also restores `platform/apps/mobile/package.json` and
  `platform/pnpm-lock.yaml`, so run `corepack pnpm install --frozen-lockfile`
  afterwards to drop `@tanstack/react-query`.
- No remote migration, deployment, hosted account, or push was performed, so
  there is nothing to undo outside this repository.

## Required handoff

- Clean commit SHA
- Changed files
- Acceptance criteria status
- Verification results
- Privacy/security impact
- Known limitations
- Rollback instructions
- A sanitized copy at `docs/app/handoffs/TASK-009.md`, committed as a
  documentation-only follow-up after the implementation commit

## Implementation notes

### Delivered files

Database:

- `platform/supabase/migrations/20260727130000_profile_display_name_self_update.sql`
- `platform/supabase/tests/database/002_profile_display_name_self_update_test.sql`
- `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
  — three assertions changed, described below

Mobile pure logic (all unit-tested):

- `src/features/auth/roles.ts` — role resolution
- `src/features/auth/gate.ts` — the gate state machine and route authorization
- `src/features/auth/session.ts` — fail-closed reading of an *unverified*
  stored session candidate
- `src/features/auth/claims.ts` — verified-claims validation (M2)
- `src/features/auth/sequence.ts` — token issuing and observation ordering (M2)
- `src/features/auth/auth-state.ts` — the auth state machine: pending state,
  identity exposure, and result-application rules (M2 round 3)
- `src/features/auth/credentials.ts`, `display-name.ts`, `submission.ts`
- `src/features/auth/errors.ts` — error sanitization and
  `isExistingAccountError` (M1)
- `src/lib/query/keys.ts`, `client.ts`

Mobile integration:

- `src/features/auth/auth-repository.ts`, `auth-provider.tsx`
- `src/features/profile/account-repository.ts`, `use-account.ts`
- `src/lib/supabase/app-client.ts`, `database.types.ts` (generated)
- `src/app/` — layout guards and ten screens
- `src/components/` — `text-field`, `primary-button`, `screen-heading`, `notice`

Removed: `src/features/role-preview/`, superseded by real authentication.

### Why a column grant rather than a table grant

`grant update (display_name)` is what makes `id` and `created_at`
non-updatable. PostgreSQL checks column privileges before evaluating row
policies, so an `UPDATE` naming either column is refused with `42501` and never
reaches RLS. A table-level grant plus a policy would have left those columns
writable to whatever the policy happened to allow.

### Two different refusal shapes

The tests assert two different things on purpose, because the database refuses
in two different ways:

- A column with no grant raises `42501`.
- A row excluded by the policy's `USING` is *filtered*, so the statement
  succeeds and affects zero rows without raising.

The second case is why a coach attempting to rename an athlete is asserted as an
unchanged value and a zero affected-row count, not as a thrown error. A test
written as `throws_ok` there would have failed while the security property held.

### RLS WITH CHECK runs before the table CHECK constraint

Verified empirically: a client storing a blank or over-length `display_name` is
rejected with `42501` from `profiles_update_self`, not `23514` from
`profiles_display_name_valid`. The constraint is retained and still governs
every non-client write path, including the signup trigger. The first test run
asserted `23514` and failed, which confirmed the suite reports real behaviour
rather than passing vacuously.

### Changes to the TASK-008 pgTAP file

Three assertions, each because TASK-009 intentionally changed the behaviour they
described. The TASK-008 *migration* was not touched.

1. "an authenticated user cannot update their own profile in this task" is now
   obsolete. It was replaced with an assertion that `created_at` still cannot be
   updated, so the section still proves something real.
2. "an active coach cannot edit an athlete profile" still holds but now fails by
   row filtering rather than by privilege, so it became `lives_ok` plus an
   unchanged-value check.
3. "no write policy exists on any of the three tables" became an exact-name
   assertion that the only write policy is `profiles_update_self`, which is a
   stronger guard than a count against a future unnoticed policy.

The plan count moved from 172 to 173. Total across both files: 216 assertions.

### Why data access takes the client as an argument

`loadAccount`, `saveDisplayName`, and the auth functions receive the Supabase
client rather than importing it. Importing `client.ts` would pull in React
Native, which would have forced a component-test runtime into the test setup.
Injection keeps every test pure and is why 187 unit tests run under plain
`vitest` with no configuration file and no new dependency beyond TanStack Query.

### An error is not an empty result

The single most important behaviour in this task. A failed membership load and a
user with no active team both yield zero usable rows. They are kept apart in
three places: the repository raises instead of returning `[]`; `useAuthGate`
maps `isError` to `{ kind: "error" }`; and `resolveAuthGate` checks for an error
before it counts memberships. Four gate tests assert specifically that a failed
load never reports `no-active-team`, `onboarding`, or `ready`.

### Post-review fixes (Codex Medium findings M1 and M2)

Both findings were accepted as correct and fixed on the same branch.

#### M1 — sign-up account enumeration

The original code threw for `user_already_exists`, so an existing address showed
an error while a new one showed check-email. That contradicted the packet's
enumeration-resistance claim.

`resolveSignUpResponse` is now a pure function that collapses a null session, an
obfuscated user with no session, and every existing-account code into the single
`confirmation-required` outcome. A genuine failure — weak password, rate limit,
transport error — still raises. `isExistingAccountError` in `errors.ts` is the
pure predicate that decides.

The residual distinction when `enable_confirmations = false` is documented
exactly in "Known limitations" with a table rather than papered over. Auth
configuration was not changed.

#### M2 — restored session trusted without verifying the JWT

`getSession()` reads on-device storage and proves nothing about authenticity.
The old `readAuthenticatedIdentity` accepted any non-empty token plus user id,
so a writable-storage attacker could mint an identity.

The session type was split so the two cannot be confused at a call site:

- `readSessionCandidate` returns `SessionCandidate { unverifiedUserId }` — a
  cheap structural pre-check, explicitly untrusted, accepted nowhere that an
  identity is required;
- `readVerifiedIdentity` in the new `claims.ts` returns
  `AuthenticatedIdentity { userId }` from a **verified** `sub`, and additionally
  rejects a missing/blank/non-string `sub`, an expired or non-finite `exp`, a
  `role` other than `authenticated`, and `is_anonymous`.

`verifyStoredIdentity` runs structural check → `getClaims()` → subject
cross-check. A mismatch between the stored user id and the verified `sub` fails
closed, which catches a session whose user was swapped while the token was left
intact. Every failure returns `null`; no verification error is ever propagated
to a caller that might display it.

`signInWithPassword` now returns `void`. Returning an identity from the sign-in
response would have created a second, weaker source of truth alongside verified
claims.

#### Ordering — corrected again in round 3

The round-2 ordering fix was **insufficient and Codex was right to reject it.**
The current design is described under "Round 3" below; this section records only
the parts that survived unchanged.

Validation is asynchronous, so results can arrive out of order — a restore
started at launch can resolve *after* a sign-out observed later. Applying it
would resurrect a signed-out session.

Each auth signal takes the next token from `sequence.ts` at the moment it is
observed. `onAuthStateChange` stays synchronous and only records the
observation; a second effect performs verification outside the callback, so no
async re-entrant Auth call is made and the auth lock cannot deadlock. The
restore path claims its token *before* the read starts, not when it resolves, so
a slow restore carries the older token and is discarded. Both effects guard on
an `active` flag, so nothing is applied after unmount.

What was wrong — the result-application predicate, and leaving the previous
identity exposed while a newer signal validated — is described next.

### Round 3 — the M2 ordering fix Codex rejected, and what replaced it

Codex closed M1 and accepted the cryptographic half of M2, but kept the
**async event/result ordering** at Medium. The rejection was correct on two
counts, and both were genuine defects rather than documentation gaps.

**Defect 1 — the guard was too weak.** Round 2 applied a result when
`resultToken > lastAppliedToken`. That admits this interleaving:

```text
applied = 1 (user A)      validation for token 2 in flight
signal 3 observed         (sign-out, or user B)  -- token 3 not settled yet
token 2 resolves          2 > 1 passes  ->  user A reapplied
```

so a stale identity could be applied *after* a newer signal had already been
observed. The fix is `canApplyValidation`, which requires
`token === latestToken` and keeps `token > appliedToken` only so a duplicated
result cannot re-apply. Equality is the load-bearing half.

**Defect 2 — the old identity stayed live during revalidation.** Round 2
recorded a newer signal but left the previously verified `identity` in place
with `restored = true` until the new validation settled. For the length of a
round trip, a protected route and the previous user's auth-scoped queries stayed
readable after a sign-out or a user switch had been observed. The reducer now
clears `identity` and enters `verifying` on every accepted signal, before any
validation runs, so the gate reports `restoring` and routing closes at once.

**Where the logic lives.** Both rules moved into a pure reducer,
`auth-state.ts`, with `authReducer`, `canApplyValidation`, `authIdentity`, and
`isAuthSettled`. `AuthProvider` is now a thin shell that issues tokens, performs
I/O, and dispatches — it consumes the same tested functions rather than
reimplementing them, so there is no second copy of the rules to drift.
`onAuthStateChange` stays synchronous: it reduces the session to a candidate
with the pure `readSessionCandidate` and dispatches, and validation still runs
in a separate effect.

`shouldApplyResult` was deleted rather than deprecated. It read as sufficient
and was not, and leaving it exported invited the same mistake again.
`resolveVerifiedIdentity(client, session)` became
`verifyStoredIdentity(client, candidate)`, which additionally keeps the access
and refresh tokens out of React state entirely — only the candidate user id is
carried.

**Cache boundary.** Because the identity is cleared when the signal is observed,
the existing `identityChanged` effect now clears auth-scoped queries at the
*signal* boundary rather than a round trip later, which is what requirement 6
asked for.

**Tests.** `auth-state.test.ts` covers the reported interleaving step by step,
the user-A → user-B late-resolution case, an exposure trace asserting user A
never reappears after the user-B signal, older/newer/repeated/out-of-order
results, cancelled results, and that a rejected event returns the identical
state object so it cannot even trigger a re-render. Two tests drive the real
`resolveAuthGate` from reducer output to prove the gate is closed while pending.

### Deliberate non-goals reconfirmed

No role is stored in a JWT claim or user metadata, no service-role policy was
added, no membership write path was opened, the role chooser writes nothing, the
query cache has no persister, and no hosted Supabase resource was contacted.
