# TASK-011 Handoff — Consent and Sharing Grants RLS Foundation

Status: Implemented, awaiting Codex read-only review.

## Task and writer

- Task: `docs/app/tasks/TASK-011-consent-sharing-grants-rls.md`
- Writer: Claude Code (sole writer)
- Reviewer: ChatGPT/Codex, read-only
- AGY: not used
- Product Owner approved the scope and decisions 1–10 before implementation.

## Branch and worktree

- Worktree: `.claude/worktrees/task-011-sharing-grants-rls` (isolated)
- Branch: `feat/TASK-011-consent-sharing-grants-rls`
- Base SHA: `642c3b4faaac5acbb4a63d4fc8caedaf6f35377b`
- Packet checkpoint commit (documentation only): `5b8eef2`
- Final commit SHA: `7fe9ad2c9b78db5d78433e355e6384ccca76caba`
- Worktree clean at handoff.

### Pre-flight

Base SHA, clean worktree, and branch name were confirmed before any work. The
isolated permission canary was read with the built-in Read tool only, at the
worktree's exact absolute path
`docs/app/permission-canary/WORKTREE-CANARY.md`, and was **denied** before any
content was returned. No Bash, PowerShell, grep, cat, Glob, search, or fallback
was used against it. No protected legacy path and no root `CLAUDE.md` was read.

## Changed files

| File | Change |
| --- | --- |
| `docs/app/tasks/TASK-011-consent-sharing-grants-rls.md` | new task packet, committed before implementation |
| `docs/app/handoffs/TASK-011.md` | this handoff |
| `platform/supabase/migrations/20260728120000_consent_sharing_grants_rls.sql` | new; the only migration added |
| `platform/supabase/tests/database/003_consent_sharing_grants_rls_test.sql` | new; 154 assertions |
| `platform/apps/mobile/src/lib/supabase/database.types.ts` | regenerated from local Supabase (+43 / −1) |
| `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql` | **four literal counts `4` → `7`** and one description reworded — see "Deviation" |

No existing migration was edited. No dependency manifest, lockfile,
`config.toml`, `seed.sql`, mobile source file, or legacy path changed.

## Implemented schema and authorization behaviour

### `public.sharing_grants`

`id uuid pk`, `team_id uuid`, `athlete_profile_id uuid`, `data_category text`,
`granted_at timestamptz not null default now()`, `revoked_at timestamptz null`.
Consent metadata only — no health value, measurement, note, or free-text field.
The test pins the exact column set, so adding one later is a test failure.

- `sharing_grants_data_category_valid` — only `check_in`, `workout_summary`,
  `sleep_summary`.
- `sharing_grants_revoked_after_granted` — defence in depth behind the trigger.
- `sharing_grants_membership_fkey` — composite FK `(team_id,
  athlete_profile_id)` → `team_memberships (team_id, profile_id)`,
  `on delete cascade`, `on update no action`. Deleting the membership, the
  profile, the auth user, or the team leaves no orphan; a membership re-key is
  refused with `23503` instead of silently moving consent.
- `sharing_grants_one_active_idx` — partial unique index on `(team_id,
  athlete_profile_id, data_category) where revoked_at is null`. At most one
  active row; revoked history is unconstrained and retained.
- `sharing_grants_athlete_profile_id_idx`, `sharing_grants_team_active_idx` —
  lookup support.
- There is **no** status column. Active is exactly `revoked_at is null`.

### Database-controlled timestamps

`private.enforce_sharing_grant_timestamps()` — `SECURITY DEFINER`,
`search_path = ''`, `before insert or update`. On insert it overwrites
`granted_at` with `pg_catalog.now()` and forces `revoked_at` to null, so a row
can never be born revoked or backdated. On update it restores `id`, `team_id`,
`athlete_profile_id`, `data_category`, and `granted_at` from the old row, stamps
a revocation with database time, and refuses to change or clear an already-set
`revoked_at`. Consent history is therefore append-only at the table level, not
merely by convention in the calling function.

### Write API (the only client write path)

`authenticated` holds no write privilege on the table, so these two
`SECURITY DEFINER` functions with `search_path = ''` are the entire surface.
Neither takes an athlete identifier or a timestamp — the test asserts the exact
signature strings, and asserts that a three-argument call fails with `42883`.

`public.grant_team_data_sharing(p_team_id uuid, p_data_category text)
returns uuid` — returns the id of the caller's active grant.

- `42501` when `auth.uid()` is null; `22023` for an unsupported or null
  category; `42501` unless the caller holds an **active athlete** membership in
  that team, so a coach-role membership cannot grant.
- Idempotent: a repeat returns the existing active row's id and inserts nothing.
  A concurrent duplicate that loses the partial unique index race is caught and
  resolved to the same result.

`public.revoke_team_data_sharing(p_team_id uuid, p_data_category text)
returns uuid` — returns the revoked row id, or `null` when nothing was active.

- Updates only rows where `athlete_profile_id = auth.uid()`.
- Performs **no** membership check by design, so withdrawal stays possible after
  the membership is revoked.
- A repeat revoke returns `null` and changes nothing.

Every raised message is a fixed string that interpolates no row, athlete, or
team, so a server error cannot leak another athlete's or team's data.

### Membership revocation cascades to consent

`private.revoke_sharing_grants_on_membership_change()` — `SECURITY DEFINER`,
`search_path = ''`, `after update on public.team_memberships for each row`, with
a `when` clause restricted to rows that *were* an active athlete membership and
*are no longer* one. It stamps `revoked_at` on every still-active grant for that
`(team_id, profile_id)`. It never inserts and never clears `revoked_at`, and it
does not fire on reactivation, so a reactivated membership starts with no active
grant. Both the status→revoked and the role→coach paths are tested. No TASK-008
membership policy, grant, constraint, or column semantic changed.

### Authorization helper

`private.can_current_user_read_shared_data(p_team_id uuid,
p_athlete_profile_id uuid, p_data_category text) returns boolean` —
`SECURITY DEFINER`, `stable`, `search_path = ''`, in the non-exposed `private`
schema. True only when the caller holds an active **coach** membership in the
team, the target holds an active **athlete** membership in the same team, **and**
the target has a grant for that category with `revoked_at is null`. Grant alone,
membership alone, role alone, or the wrong category returns false. This is the
gate every future protected health table must consult.

### Privileges and RLS

- RLS enabled on `sharing_grants`.
- All default privileges revoked from `anon` and `authenticated`; only `SELECT`
  granted back to `authenticated`. `anon` holds nothing, so an anonymous read
  fails `42501` at the privilege layer before RLS is consulted, and every
  refused authenticated write fails the same way.
- No `INSERT`/`UPDATE`/`DELETE` privilege or policy for any client role.
- Supabase default privileges grant `EXECUTE` on new `public` functions to
  `anon`, so `anon` is revoked explicitly on both RPCs in addition to the
  `PUBLIC` revoke. `EXECUTE` is granted only to `authenticated`.
- The helper is revoked from `PUBLIC` and `anon` and granted only to
  `authenticated`, the minimum for policy evaluation. The two trigger functions
  are executable by nobody.
- Two `SELECT` policies, no others:
  `sharing_grants_select_own_history` (`athlete_profile_id = auth.uid()`) and
  `sharing_grants_select_active_for_coach` (`revoked_at is null` **and** the
  helper). Coach visibility routes through the same helper future health
  policies must use, so the two cannot drift apart.
- The coach policy is non-recursive: the helper is `SECURITY DEFINER`, so its
  read of `sharing_grants` is not subject to the policy.

## Acceptance-criteria mapping

| Criterion | Where it is enforced and proved |
| --- | --- |
| No health value stored | exact-column-set assertion; `rpe` and `heart_rate` categories rejected `23514` |
| Decision 1 — per team | grant/helper key on `team_id`; no coach id anywhere in the schema |
| Decision 2 — three categories | check constraint + RPC guard; `23514` and `22023` asserted |
| Decision 3 — history retained | revoke stamps and keeps the row; re-grant creates a second row (2 rows asserted) |
| Decision 4 — no status column | `hasnt_column('status')` + pinned column set |
| Decision 5 — no direct client write | zero write privileges; direct insert/update/delete all `42501` |
| Decision 6 — identity and time from the database | RPC signatures pinned; `42883` on a forged third argument; trigger overwrites supplied timestamps |
| Decision 7 — membership revocation revokes grants | trigger; status and role paths both asserted; reactivation revives nothing |
| Decision 8 — coach sees active only, own team only | coach policy; revoked-history and cross-team counts are 0 |
| Decision 9 — grant alone insufficient | helper truth table, 10 assertions |
| Decision 10 — database foundation only | no mobile source file changed; synthetic fixtures only |
| Revocation effective on next query | athlete revokes, coach's next `select` returns 0 and the helper turns false, with no token change |
| Types match the local database | regenerated, then regenerated again into a temp file and compared: identical |
| Existing tests still pass | 001, 002, and the mobile suite all pass |

## Negative-test matrix and results

All 31 cases from the packet, all passing. `003` contributes 154 assertions.

| # | Case | Result |
| --- | --- | --- |
| 1 | anon reads the table | PASS — `42501` |
| 2 | anon executes either RPC (and the helper) | PASS — `42501` ×3 |
| 3 | authenticated direct insert (plain, forged timestamp, forged identity) | PASS — `42501` ×3 |
| 4 | authenticated direct update | PASS — `42501` |
| 5 | authenticated direct delete | PASS — `42501` |
| 6 | athlete reads own active and revoked history | PASS — 3 rows, 1 active, 2 revoked |
| 7 | athlete reads another athlete's grants | PASS — 0, same team and other team |
| 8 | athlete grants without active athlete membership | PASS — `42501`, incl. nonexistent team and revoked athlete |
| 9 | active coach grants or revokes for an athlete | PASS — grant `42501`; revoke returns null and the athlete's grant stays active |
| 10 | coach-role membership grants as an athlete | PASS — `42501` in the coached team; the same dual-role user succeeds in the team where they are an athlete |
| 11 | Team A coach reads Team B grants | PASS — 0 both directions |
| 12 | Team A coach reaches Team B through the helper | PASS — false |
| 13 | active coach reads an active grant of an active athlete | PASS — visible |
| 14 | coach reads revoked history | PASS — 0 |
| 15 | grant revoked, coach queries again | PASS — 0 on the next query, helper false |
| 16 | revoked coach | PASS — 0 for a pre-revoked coach, and an active coach revoked mid-transaction drops from 2 rows to 0 |
| 17 | revoked athlete membership | PASS — coach sees 0, helper false |
| 18 | membership revocation stamps grants | PASS — `revoked_at = now()`, row retained |
| 19 | reactivation | PASS — 0 active, helper still false |
| 20 | re-grant | PASS — new history row, 2 total, 1 active |
| 21 | duplicate grant | PASS — same id returned, 1 row |
| 22 | repeat revoke | PASS — returns null, history unchanged |
| 23 | invalid category | PASS — `22023` via RPC, `23514` via trusted insert |
| 24 | forged athlete identity | PASS — `42883` on the extra argument; direct insert `42501`; stored id equals `auth.uid()` |
| 25 | forged `granted_at` / `revoked_at` | PASS — overwritten on insert and on revoke; a revoked row cannot be un-revoked |
| 26 | helper: grant but no coach membership | PASS — false |
| 27 | helper: both memberships, no grant | PASS — false |
| 28 | helper: wrong category | PASS — false |
| 29 | helper: grant plus both active memberships | PASS — true |
| 30 | catalog assertions | PASS — RLS, 2 SELECT policies and 0 write policies, no policy targeting `anon`/`public`, table privileges, function privileges, `SECURITY DEFINER` ×5, empty `search_path` ×5, constraints, FK delete/update actions, partial-unique index, both triggers |
| 31 | existing TASK-008 and TASK-009 pgTAP files | PASS |

Positive controls are present alongside the denials — the coach sees exactly the
two active Team A grants while the same query returns 0 for a revoked coach and
3 own rows for the athlete — so the role switching is proven effective rather
than vacuously passing.

## Commands run and results

Local database only. No `--linked`, no project ref, no remote URL, no hosted
Supabase contact.

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0, lockfile unchanged |
| `corepack pnpm db:start *> $null` | exit 0, 10 containers healthy |
| `corepack pnpm exec supabase db reset --local --no-seed` | exit 0, all three migrations applied |
| `corepack pnpm exec supabase test db --local` | **PASS — 3 files, 370 assertions** (173 + 43 + 154) |
| `corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, no schema errors |
| `supabase gen types typescript --local --schema public` | exit 0, BOM stripped, Prettier-formatted |
| type drift re-generation and comparison | identical, no drift |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | **327 passed, 18 files** |
| `corepack pnpm db:stop *> $null` | exit 0, no Supabase container remains |
| `git diff --check` | clean |
| `git status --short` | clean at handoff |

`db:start` and `db:stop` were run with `*> $null`, so the API URL, anon key,
service-role key, JWT secret, and database URL never reached the terminal, the
transcript, or a log. `supabase status` and `db:status` were not run.

Two genuine failures were found and fixed before the results above:
`has_default` is not a pgTAP function in this version (the correct name is
`col_has_default`), which aborted the file and proved the suite reports real
errors rather than passing vacuously; and the initial `plan(160)` did not match
the 154 assertions actually written.

## Deviation from the packet, flagged for approval

`001_identity_teams_membership_rls_test.sql` asserts four **global** counts over
`pg_proc` in the `private` schema: that exactly 4 functions exist there and that
all 4 are `SECURITY DEFINER` with a pinned, empty `search_path`. TASK-011
necessarily adds three private functions, so those four assertions become
arithmetically false the instant the migration applies. Acceptance criterion 31
requires the TASK-008 suite to keep passing, and there is no way to satisfy both
while adding the required `private.can_current_user_read_shared_data` helper.

The minimum correction was applied: four literals `4` → `7`, plus one assertion
description reworded to name which task contributes which functions. No
assertion was removed, weakened, or re-scoped — the three security properties
still apply globally to every function in `private`, now covering 7 instead of
4, and TASK-011's own file additionally asserts its 5 functions by name. TASK-009
set the precedent by updating the same file where one of its assertions had
become intentionally obsolete.

This is recorded in the task packet under "Verified requirement found during
implementation" and is flagged here for Product Owner and reviewer attention
rather than assumed pre-approved.

## Privacy and security impact

Consent metadata is PII but carries **no** health measurement: a team id, a
profile id, a category name, and two timestamps. It records that a person
consented to share a category with a team, and when — nothing about what was
shared.

All fixtures are synthetic, transaction-scoped, and rolled back, and use the
reserved `example.test` domain. No real user, real athlete, Garmin data, or
protected legacy data was read or introduced. No service-role key was used. No
credential, JWT, database URL, `db:status` output, email address, real user id,
health value, or native secret was printed or persisted.

The security posture is strictly additive: `anon` gains nothing anywhere,
`authenticated` gains `SELECT` on one new table and `EXECUTE` on two new RPCs
and one new helper, and no existing grant or policy was loosened.

## Known limitations

- Sharing is per team by decision 1. An athlete cannot exclude one coach of a
  team they have consented to; revoking the category or leaving the team is the
  only control.
- No client-reachable path exists to create teams or memberships, so the
  athlete-facing grant flow can only be exercised against trusted fixtures until
  a membership-administration task exists.
- No mobile UI is delivered, so the RPCs are unreachable from the app today.
- Grant history accumulates with no retention or compaction policy. A future
  privacy-request task must decide how it is exported and deleted.
- The composite FK uses `on update no action`, so a trusted re-key of a
  membership row is refused with `23503` while an active grant exists. This is
  the fail-safe direction, not silent consent migration.
- `sharing_grants_revoked_after_granted` is currently unreachable because the
  timestamp trigger already guarantees it. It is retained as defence in depth
  against a disabled or altered trigger.
- The generated `Insert`/`Update` types for `sharing_grants` look permissive,
  but no client role holds the privilege to use them; the database, not the
  type, is the boundary.
- Local Analytics remains disabled from TASK-007, so Studio's Logs section is
  empty locally.

## Rollback

1. `git revert` the TASK-011 commits, or delete
   `platform/supabase/migrations/20260728120000_consent_sharing_grants_rls.sql`,
   `platform/supabase/tests/database/003_consent_sharing_grants_rls_test.sql`,
   this handoff, and the task packet; restore
   `platform/apps/mobile/src/lib/supabase/database.types.ts` and
   `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
   from `642c3b4`.
2. Run `corepack pnpm exec supabase db reset --local --no-seed` to rebuild the
   local database without the migration.

Nothing was applied to a remote database, so no remote rollback exists or is
needed. No dependency, lockfile, or configuration file was touched.

## Confirmation

Nothing was merged, pushed, deployed, linked to a hosted project, remotely
migrated, or cleaned up. The branch is local, the worktree still exists and is
clean, the local Supabase stack is stopped with no container remaining, and no
production operation of any kind was performed.

Stopping here for Codex read-only review.
