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

Round 1 implementation:  d78ccb91fd09f0a380a497a1310c16b39c24087f
Round 1 handoff:         75bdfeeb5ccf28d49534fb2fb54044f930c9a7ce
Round 2 fix (M1, M2):    see "Reviewer findings" below; this is the head
```

Round 2 fixes the two Codex Medium findings on the same branch. The file list
and results below are cumulative for the whole task unless a section says
otherwise. Nothing has been merged or pushed, and the worktree is still in
place.

## Changed files

### Database (3)

| File | Change |
| --- | --- |
| `platform/supabase/migrations/20260727130000_profile_display_name_self_update.sql` | new |
| `platform/supabase/tests/database/002_profile_display_name_self_update_test.sql` | new, 43 assertions |
| `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql` | 3 assertions changed, plan 172 → 173 |

The TASK-008 **migration** was not edited. Only its test file changed, and only
where TASK-009 intentionally made an assertion obsolete.

### Mobile — pure logic, fully unit-tested (11)

`src/features/auth/`: `roles.ts`, `gate.ts`, `session.ts`, `credentials.ts`,
`display-name.ts`, `submission.ts`, `errors.ts`, **`claims.ts`** (round 2),
**`sequence.ts`** (round 2)
`src/lib/query/`: `keys.ts`, `client.ts`

Round 2 changed `session.ts` (candidate/identity split), `errors.ts`
(`isExistingAccountError`), `auth-repository.ts`, and `auth-provider.tsx`.

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

### Tests (14 files, 244 assertions)

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
| The restored JWT is verified before an identity exists | `resolveVerifiedIdentity` calls `getClaims()`; identity comes from the verified `sub` |
| A stored `user.id` can no longer mint an identity | `SessionCandidate` is a distinct type accepted nowhere an identity is required |
| A stale restore cannot resurrect a signed-out session | `sequence.ts`, with an explicit out-of-order ordering test |
| An existing address shows no distinct error | `resolveSignUpResponse` normalizes to the generic outcome |
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
| `pnpm test` | **244 passed, 14 files** |
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

- Passwords, access tokens, refresh tokens, session objects, and JWT claims are
  never logged, never placed in an error message, and never stored outside the
  Supabase auth storage adapter. Only the verified `sub` is lifted out.
- An authenticated identity exists only after `getClaims()` verifies the JWT. A
  stored `user.id` cannot produce one, so an attacker with writable device
  storage cannot mint an identity by editing the stored session.
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

1. **Sign-up enumeration resistance is incomplete while email confirmation is
   disabled.** See the M1 table in "Reviewer findings" below. The finding as
   reported is fixed; the
   residual distinction is structural, is stated rather than hidden, and needs
   an Auth configuration decision before pilot.
2. **JWT verification may cost a network round trip.** `getClaims()` verifies
   locally only for an asymmetric signing key. With a symmetric secret it
   validates at the Auth server, so an offline launch fails closed to signed-out
   rather than restoring. That is the correct direction to fail, but moving the
   project to asymmetric signing keys would remove the cost.
3. If sign-in succeeds but the resulting JWT then fails verification, the user
   returns to the sign-in screen with no message. Fails closed correctly, but is
   opaque.
4. **SecureStore hardening is mandatory before pilot release, and before any
   health data is added.** Supabase session tokens persist in AsyncStorage,
   which is not encrypted at rest on device. This is acceptable only because
   TASK-009 handles no health data. Carrying it into a build that touches RPE,
   pain/injury, sleep, heart rate, or workout data would be a privacy
   regression. This is the single most important follow-up.
5. Email confirmation has no deep-link handler. A confirming user must return to
   the app and sign in manually. Hosted Auth and email configuration were not
   changed, as required.
6. No password reset, change-email, or account-deletion flow yet.
7. Membership state is read on load and on explicit retry, not live-subscribed.
   A revocation takes effect in the database immediately but in the UI on the
   next successful load. Safe because RLS, not the client, is the authorization
   boundary.
8. Verification is mock-and-local-database only. There is no end-to-end evidence
   against the hosted project.
9. The athlete and coach shells remain empty-state placeholders. This task
   delivers the way in, not what is inside.
10. No render/component test exists, by approved decision. Screens are
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

## Reviewer findings

Codex round 1 raised two Medium findings. Both were accepted as correct and are
fixed. **No finding remains open.**

### M1 — sign-up account enumeration — fixed

The old code threw for `user_already_exists`, so an existing address produced an
error while a new one produced check-email. `resolveSignUpResponse` is now a
pure function that collapses a null session, an obfuscated user with no session,
and every existing-account code into one `confirmation-required` outcome. No
error is shown for an existing address, and no raw error, email, or payload is
displayed or logged. Genuine failures — weak password, rate limit, transport —
still raise.

**The claim of complete enumeration resistance has been withdrawn, not
re-asserted.** It holds only while email confirmation is enabled:

| `enable_confirmations` | New address | Existing address | Distinguishable? |
| --- | --- | --- | --- |
| `true` | null session → check-email | obfuscated user, null session → check-email | **No** |
| `false` | session returned → app enters | existing-account code → check-email | **Yes** |

With confirmations disabled a successful sign-up necessarily signs the user in,
and that can only happen for a new address. Hiding it would mean discarding a
valid session and breaking approved outcome 3. Closing it requires enabling
email confirmation, which is a hosted Auth configuration change and is out of
scope. The local stack currently has `enable_confirmations = false`, so it is in
the distinguishable row. A timing side channel also remains in both rows.

### M2 — restored session trusted without verifying the JWT — fixed

`getSession()` reads on-device storage and proves nothing about authenticity.
The session type was split so the two can no longer be confused at a call site:

- `readSessionCandidate` → `SessionCandidate { unverifiedUserId }`, a cheap
  structural pre-check, accepted nowhere an identity is required;
- `readVerifiedIdentity` (new `claims.ts`) → `AuthenticatedIdentity { userId }`
  from the **verified** `sub`, additionally rejecting a missing/blank/non-string
  `sub`, an expired or non-finite `exp`, a `role` other than `authenticated`,
  and `is_anonymous`.

`resolveVerifiedIdentity` runs structural check → `getClaims()` → subject
cross-check, and returns `null` on any failure. The cross-check catches a stored
session whose user was swapped while the token was left intact.
`signInWithPassword` now returns `void`, so verified claims are the only source
of identity.

Ordering is handled by the pure `sequence.ts` guard. `onAuthStateChange` stays
synchronous and only records the observation with a freshly claimed token; a
second effect verifies outside the callback, so no async re-entrant Auth call is
made. The restore path claims its token *before* the read starts, so a slow
restore carries the older token and cannot resurrect a session after a later
sign-out. `restored` stays `false` until the first result applies, so the gate
reports `restoring` and no protected route renders while validation is pending.
Both effects guard on an `active` flag, so nothing is applied after unmount.

### Security impact of the fix round

Strictly a tightening. An attacker with writable device storage can no longer
mint an identity by editing a stored session, since the identity now comes from
a signature-verified `sub` rather than a stored `user.id`. Expired, wrong-role,
anonymous, and subject-mismatched tokens are refused. The sign-up flow no longer
returns a distinct response for a registered address at the point the server
lets us hide it. No authorization was widened, no database object changed, and
RLS remains the enforcement boundary throughout.

### Suggested focus for re-review

1. `claims.ts` — whether any accepted claim shape could still yield an identity
   from an unverified or unintended token.
2. `resolveVerifiedIdentity` — the ordering of the structural check, `getClaims()`,
   and the subject cross-check, and that no error escapes.
3. `sequence.ts` plus the two effects in `auth-provider.tsx` — whether any
   interleaving of restore, sign-in, sign-out, and unmount can apply a stale
   result or leave `restored` true with an unverified identity.
4. `resolveSignUpResponse` — whether the documented limitation is stated
   accurately, and whether any other response path reveals account existence.
5. Unchanged from round 1 and still worth confirming: the two refusal shapes in
   `002_..._test.sql`, the three changed assertions in the TASK-008 test file,
   and `resolveAuthGate` ordering in `gate.ts`.
