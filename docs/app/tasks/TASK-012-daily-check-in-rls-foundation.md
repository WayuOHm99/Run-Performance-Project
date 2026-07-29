# TASK-012: Daily Check-In RLS Foundation

Status: Implemented and verified locally. Round 1 Codex findings H1, M1, M2, and
M3, Round 2 Codex findings M1, M2, L1, and L2, the Round 3 Codex Medium on
pgTAP failure-output safety, Round 4 Codex findings M1 and L1, and Round 5 Codex
findings M1 and M2 are fixed and re-verified. Awaiting GPT/Codex Round 6
read-only review.

F1, the open finding of my own discovery recorded in Round 5 — bare fixture DML
emitting a native psql error with a failing-row `DETAIL` — was approved as Round
6 M1 and is closed with mutation proof. Nothing is outstanding.

The approved scope and decisions 1–10 below are unchanged. Round 2 altered only
how the boundary is enforced and proved, never what it is; the changes are
recorded in `docs/app/handoffs/TASK-012.md`.

Writer: Claude Code (sole writer)

Reviewer: GPT/Codex (read-only)

No AGY reviewer is assigned to this task. AGY must not be used.

Product Owner: the human repository owner. The complete scope and product and
security decisions 1–10 below were **approved before implementation started**.

## Goal and user value

Create the first **protected-health-data** table in the product —
`public.daily_check_ins` — and prove locally that athlete ownership plus the
TASK-011 sharing-grant authorization boundary actually works.

TASK-008 built identity, teams, and membership, and recorded that active
membership alone must never be treated as sufficient for health access. TASK-011
supplied the missing half: an athlete-owned, per-team, per-category consent
record and the single authorization helper
`private.can_current_user_read_shared_data`. This task is the first consumer of
that helper, and the first place where a real health value is stored.

The user value is the athlete's: their check-in belongs to them, they can always
read it, and a coach can read it only while the athlete is actively sharing the
`check_in` category with a team both of them actively belong to. Turning sharing
off, or either membership ending, removes the coach's access on the coach's very
next query.

This task is **database and RLS foundation only** and delivers **no mobile UI**.

## Base and ownership

- Source branch: `feat/mobile-foundation`
- Required base SHA: `69a1471be6271d8b1e9b318ed5f70c16059dba4e`
- Task branch: `feat/TASK-012-daily-check-in-rls`
- Isolated Git worktree; all work happens there and the worktree stays in place
  for the reviewer.
- Claude Code is the only writer. The reviewer does not edit implementation
  files.
- No merge, push, deploy, hosted link, remote migration, `db push`, or
  production operation of any kind is part of this task.
- The approved scope must not change during implementation. If a material
  conflict is discovered, stop and ask the Product Owner.

### Pre-flight, completed before any edit

- Source branch confirmed as `feat/mobile-foundation` at
  `69a1471be6271d8b1e9b318ed5f70c16059dba4e`.
- The source repository had no tracked modifications.
- `feat/mobile-foundation` confirmed to be an ancestor of the task branch.
- The isolated worktree permission canary
  `docs/app/permission-canary/WORKTREE-CANARY.md` was requested by its exact
  absolute worktree path with the built-in `Read` tool only, and was **denied
  before any content was returned**. No Bash, PowerShell, `grep`, `cat`, Glob,
  search, or other fallback was used against it, and no retry through a
  different path form was attempted.
- No protected legacy path and no root `CLAUDE.md` was read.

## In scope

- One new timestamped migration under `platform/supabase/migrations/` creating
  `public.daily_check_ins`, its constraints, its index justification, its Row
  Level Security, its minimum column-level privileges, one private
  column-enforcement trigger function, and one private read-authorization helper
  that **calls** `private.can_current_user_read_shared_data`.
- One new additive pgTAP authorization test file under
  `platform/supabase/tests/database/`.
- Regenerated TypeScript database types from the **local** stack only.
- The handoff at `docs/app/handoffs/TASK-012.md`.
- A mechanical count update in
  `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
  if, and only if, its schema-wide expected counts require it — see
  "Expected mechanical update to the TASK-008 test".

## Out of scope / forbidden

- Mobile screens, components, hooks, repositories, navigation, or any check-in
  UI.
- Training plans, coach dashboard, monitoring flags, notifications.
- Workout and sleep tables.
- HealthKit, Health Connect, Garmin, Strava, WHOOP, COROS, or any wearable code.
- Product Charter, ADR, permission-setting, dependency, package, or lockfile
  changes.
- Team creation, invitations, or membership administration.
- Free-text health notes, body location, diagnosis, or diagnostic
  interpretation.
- Direct Bluetooth pairing or writing workouts to a watch.
- Editing any existing migration file.
- Editing `platform/supabase/tests/database/002`, `003`, or `004`.
- Every part of `001_identity_teams_membership_rls_test.sql` other than the
  schema-wide expected counts described below.
- `platform/supabase/config.toml`, `platform/supabase/seed.sql`,
  `platform/package.json`, `platform/apps/mobile/package.json`,
  `platform/pnpm-lock.yaml`, `platform/apps/mobile/.env.local`,
  `platform/packages/`.
- Every `docs/app/architecture/` file.
- Root `athletes/`, `team_data/`, `garmin/`, `scripts/`, root `supabase/`,
  `CLAUDE.md`, `.agents/AGENTS.md`, `.claude/settings.json`,
  `.claude/settings.local.json`.
- Push, merge, deploy, hosted link, remote migration, `db push`, production
  data, service-role secret, or worktree cleanup.

## Owned paths

- `docs/app/tasks/TASK-012-daily-check-in-rls-foundation.md`
- `docs/app/handoffs/TASK-012.md`
- `platform/supabase/migrations/20260728140000_daily_check_ins_rls.sql`
  (the one new migration)
- `platform/supabase/tests/database/005_daily_check_ins_rls_test.sql`
  (the one new database authorization test)
- `platform/apps/mobile/src/lib/supabase/database.types.ts`
- `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`,
  **schema-wide expected counts only**, plus one concise explanation.

No additional application documentation is named by this packet, so none may be
added during implementation.

## Forbidden paths

- `platform/supabase/migrations/20260727120000_identity_teams_membership_rls.sql`
- `platform/supabase/migrations/20260727130000_profile_display_name_self_update.sql`
- `platform/supabase/migrations/20260728120000_consent_sharing_grants_rls.sql`
- `platform/supabase/tests/database/002_profile_display_name_self_update_test.sql`
- `platform/supabase/tests/database/003_consent_sharing_grants_rls_test.sql`
- `platform/supabase/tests/database/004_consent_sharing_grants_concurrency_test.sql`
- every part of `001_identity_teams_membership_rls_test.sql` other than the
  schema-wide expected counts
- `platform/supabase/config.toml`
- `platform/supabase/seed.sql`
- `platform/package.json`
- `platform/apps/mobile/package.json`
- `platform/pnpm-lock.yaml`
- `platform/apps/mobile/.env.local`
- `platform/packages/`
- every `docs/app/architecture/` file
- `athletes/`, `team_data/`, `garmin/`, `scripts/`
- root `supabase/`
- `CLAUDE.md`, `.agents/AGENTS.md`
- `.claude/settings.json`, `.claude/settings.local.json`

## References

- `AGENTS.md`
- `platform/AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/AI-WORKING-AGREEMENT.md`
- `docs/app/CLAUDE-CODE-SETUP.md`
- `docs/app/tasks/TASK-TEMPLATE.md`
- `docs/app/tasks/TASK-008-identity-teams-membership-rls.md`
- `docs/app/tasks/TASK-011-consent-sharing-grants-rls.md`
- `docs/app/handoffs/TASK-011.md`
- `platform/supabase/migrations/20260727120000_identity_teams_membership_rls.sql`
- `platform/supabase/migrations/20260728120000_consent_sharing_grants_rls.sql`
- `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
- `platform/supabase/tests/database/003_consent_sharing_grants_rls_test.sql`

## Approved product and security decisions

1. **A daily check-in is personal athlete data, not team-owned data.** The row
   carries no `team_id`. The same personal row may be shared independently with
   each team through `sharing_grants`.
2. **At most one check-in per athlete per client-supplied local calendar date,**
   enforced by a database unique constraint.
3. **The only health fields are exactly three:**
   - `rpe` — required integer 0 through 10
   - `overall_feeling` — required integer 1 through 5
   - `pain_status` — required text, exactly `none` or `present`

   No free text, body location, diagnosis, note, image, or attachment is
   allowed.
4. **`athlete_profile_id`, `check_in_date`, `id`, and the database-controlled
   creation timestamp are immutable after insert.** `updated_at` is controlled by
   the database.
5. **The data subject may update only `rpe`, `overall_feeling`, and
   `pain_status` on their own row.** There is no client `DELETE` privilege and no
   `DELETE` policy in this task.
6. **An authenticated data subject can always read their own check-ins,**
   independent of team membership or sharing status. Self insert and self update
   are identity-owned and must not grant access to anybody else.
7. **A coach can `SELECT` a check-in only when an active coach membership, an
   active athlete membership in the same team, and an active sharing grant with
   category `check_in` all exist.** The policy must call and reuse
   `private.can_current_user_read_shared_data` from TASK-011; its authorization
   logic must not be duplicated or weakened.
8. **Coaches cannot insert, update, or delete check-ins.** One athlete cannot
   read or mutate another athlete's rows. A Team A relationship must not expose
   the row to Team B.
9. **Revoking either membership or the `check_in` sharing grant removes coach
   visibility on the next query,** without token refresh or sign-out.
10. **Synthetic fixtures and local Supabase only.** No hosted Supabase, remote
    migration, service-role credential, production data, wearable integration,
    or protected legacy access.

### Recorded reading of decision 8, for the reviewer

Decision 8 states the cross-user boundary: no coach obtains a write path into
another person's check-in, and no athlete reads or mutates another athlete's
rows. It is enforced as "no user may insert, update, or delete a row whose
`athlete_profile_id` is not their own", which is exactly what the tests assert
against an active coach of the athlete's own team.

It is deliberately **not** implemented as "a user who holds any coach membership
may never own a check-in", because that would contradict decision 6: self
insert and self update are identity-owned and independent of team membership,
and the data model already supports a user who is a coach in one team and an
athlete in another. A coach writing their own check-in row is the data subject
acting on their own data, and it exposes that row to nobody.

## Approved schema

### `public.daily_check_ins`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | primary key, `default gen_random_uuid()`, database-generated, immutable |
| `athlete_profile_id` | `uuid` | not null, references `public.profiles (id)` `on delete cascade`, immutable after insert |
| `check_in_date` | `date` | not null, client-supplied local calendar date, immutable after insert |
| `rpe` | `smallint` | not null, `check (rpe between 0 and 10)` |
| `overall_feeling` | `smallint` | not null, `check (overall_feeling between 1 and 5)` |
| `pain_status` | `text` | not null, `check (pain_status in ('none', 'present'))` |
| `created_at` | `timestamptz` | not null, `default now()`, database-controlled, immutable |
| `updated_at` | `timestamptz` | not null, `default now()`, database-controlled |

There is **no** `team_id` column, by decision 1. There is **no** free-text,
note, body-location, diagnosis, image, or attachment column, by decision 3. The
test pins the exact column set, so adding one later is a test failure rather
than a review miss.

Constraints:

- `daily_check_ins_rpe_valid` — `rpe between 0 and 10`.
- `daily_check_ins_overall_feeling_valid` — `overall_feeling between 1 and 5`.
- `daily_check_ins_pain_status_valid` — `pain_status in ('none', 'present')`.
- `daily_check_ins_athlete_date_unique` — `unique (athlete_profile_id,
  check_in_date)`, which is decision 2.
- `daily_check_ins_athlete_profile_id_fkey` — `athlete_profile_id` references
  `public.profiles (id)` `on delete cascade`. `public.profiles.id` itself
  references `auth.users (id)` `on delete cascade`, so deleting the account
  cascades through the profile to every check-in and leaves no orphan health
  row.

### Indexes

The unique constraint `daily_check_ins_athlete_date_unique` creates a b-tree
index on `(athlete_profile_id, check_in_date)`. That index is leading-column
usable for both query paths this task actually has:

- the data subject reading their own check-ins, filtered on
  `athlete_profile_id`;
- a coach reading one athlete's check-ins, which is also an
  `athlete_profile_id` lookup after the authorization helper has passed.

**No additional index is created.** A date-only index has no query path in this
task because no cross-athlete date scan exists, and speculative indexes on a
protected-health table are cost without benefit.

### Column enforcement trigger

`private.enforce_daily_check_in_columns()` — `SECURITY DEFINER`,
`search_path = ''`, `before insert or update on public.daily_check_ins for each
row`:

- validates every client-supplied required field — presence of
  `athlete_profile_id` and `check_in_date`, and the presence, range, and allowed
  values of `rpe`, `overall_feeling`, and `pain_status` — and rejects any
  violation with a single sanitized `22023` exception carrying a fixed message
  and no field, value, identifier, date, `DETAIL`, or `HINT` (Round 2, M1). The
  declarative `NOT NULL` and `CHECK` constraints are unchanged and remain the
  real guarantee; this branch only ensures a client never reaches them, because
  their native failure would carry the whole protected-health row in a
  `Failing row contains (...)` detail;
- on insert, overwrites `created_at` and `updated_at` with `pg_catalog.now()`,
  so neither can be backdated even by a trusted writer;
- on update, restores `id`, `athlete_profile_id`, `check_in_date`, and
  `created_at` from the old row, making decision 4 immutability a property of
  the table;
- on update, sets `updated_at` to
  `greatest(clock_timestamp(), old.updated_at + interval '1 microsecond')`, so
  it stays database-controlled and strictly advances on every update, including
  two updates inside one transaction, with no sleep (Round 2, M2).

The trigger is defence in depth **behind** the column privileges, not instead of
them: no client role holds `INSERT` or `UPDATE` privilege on `id`, `created_at`,
or `updated_at`, and no client role holds `UPDATE` privilege on
`athlete_profile_id` or `check_in_date`, so a client attempt is refused with
`42501` before the trigger is reached. The trigger keeps the guarantee true for
any future writer inside the trusted boundary.

Its name deliberately contains no `health` substring, so the TASK-008 assertion
that no broad health-data authorization helper exists in `private` remains
meaningful and passing.

### Read-authorization helper

```text
private.can_current_user_read_check_in(p_athlete_profile_id uuid)
returns boolean
```

`SECURITY DEFINER`, `stable`, `search_path = ''`, in the non-exposed `private`
schema.

`public.daily_check_ins` has no `team_id`, because a check-in is personal data
shared independently per team (decision 1). This helper therefore enumerates the
teams in which the target holds an active athlete membership and asks the
**TASK-011 helper**, unchanged, whether the caller may read `check_in` data for
that athlete in that team:

```sql
select exists (
  select 1
  from public.team_memberships as athlete_membership
  where athlete_membership.profile_id = p_athlete_profile_id
    and athlete_membership.status = 'active'
    and athlete_membership.role = 'athlete'
    and private.can_current_user_read_shared_data(
          athlete_membership.team_id, p_athlete_profile_id, 'check_in')
);
```

It adds **no** authorization condition of its own and removes none. Every
coach-role check, athlete-membership check, grant check, category check, and
revocation check remains inside
`private.can_current_user_read_shared_data`, exactly as decision 7 requires.
The outer scan only supplies candidate team ids, and its own predicates are a
strict subset of what the TASK-011 helper already re-checks, so it cannot widen
access. Because it is `SECURITY DEFINER`, the enumeration is not filtered by the
`team_memberships` policies, which keeps the check-in policy fail-closed rather
than dependent on another table's read policy.

Privileges: `PUBLIC` and `anon` execution revoked; `EXECUTE` granted only to
`authenticated`, which is the minimum required because a policy expression is
evaluated as the calling role.

### Approved table privileges

- All default privileges are revoked from `anon` and `authenticated` first,
  because Supabase grants `ALL` on a new `public` table to both.
- `anon` receives **nothing**, so an anonymous `SELECT`, `INSERT`, `UPDATE`, or
  `DELETE` fails with `42501` at the privilege layer before RLS is consulted.
- `authenticated` receives exactly:
  - `SELECT` on the table;
  - `INSERT (athlete_profile_id, check_in_date, rpe, overall_feeling,
    pain_status)` — column-level, so `id`, `created_at`, and `updated_at` cannot
    be named in a client insert at all;
  - `UPDATE (rpe, overall_feeling, pain_status)` — column-level, so the owner,
    the date, the id, and both timestamps cannot be named in a client update at
    all.
- **No `DELETE` privilege for any client role, and no `DELETE` policy.**
- No `TRUNCATE`, `REFERENCES`, or `TRIGGER` privilege for any client role.

### Approved Row Level Security

RLS is enabled on `public.daily_check_ins`. Four policies, all
`to authenticated`, and no policy targets `anon` or `public`:

| Policy | Command | Expression |
| --- | --- | --- |
| `daily_check_ins_select_own` | `SELECT` | `USING (athlete_profile_id = (select auth.uid()))` |
| `daily_check_ins_select_shared_for_coach` | `SELECT` | `USING (private.can_current_user_read_check_in(athlete_profile_id))` |
| `daily_check_ins_insert_own` | `INSERT` | `WITH CHECK (athlete_profile_id = (select auth.uid()))` |
| `daily_check_ins_update_own` | `UPDATE` | `USING (athlete_profile_id = (select auth.uid()))` and `WITH CHECK (athlete_profile_id = (select auth.uid()))` |

The self-read policy is independent of membership and sharing, which is
decision 6. The coach-read policy is `SELECT` only, which is decisions 7 and 8:
no coach reaches any write path, because the only `INSERT` and `UPDATE` policies
require `athlete_profile_id = auth.uid()`.

## Acceptance criteria

- [x] `public.daily_check_ins` exists with exactly the approved columns, types,
      nullability, check constraints, unique constraint, and cascading foreign
      key, and with no `team_id` and no free-text or attachment column.
- [x] Every approved decision 1–10 is enforced by PostgreSQL, not by client
      code.
- [x] `rpe` outside 0–10, `overall_feeling` outside 1–5, and `pain_status`
      outside `none`/`present` are all rejected by the database.
- [x] A second row for the same athlete and the same `check_in_date` is
      rejected, and the uniqueness guarantee is asserted as a constraint, not
      merely observed once.
- [x] `id`, `created_at`, and `updated_at` are database-controlled and cannot be
      written by a client; `athlete_profile_id`, `check_in_date`, `id`, and
      `created_at` cannot be changed after insert.
- [x] `updated_at` advances only under database control.
- [x] `anon` holds no privilege and no policy; every anonymous `SELECT`,
      `INSERT`, `UPDATE`, and `DELETE` is denied.
- [x] `authenticated` holds `SELECT` plus exactly the two approved column-level
      write privileges, and no `DELETE`, `TRUNCATE`, `REFERENCES`, or `TRIGGER`
      privilege.
- [x] A `DELETE` by any client role is denied, and no `DELETE` policy exists.
- [x] The data subject inserts, reads, and updates their own row, and can update
      only `rpe`, `overall_feeling`, and `pain_status`.
- [x] A user cannot insert a row for another profile, and cannot read or update
      another user's row.
- [x] A coach with active same-team memberships but no `check_in` grant sees
      zero rows.
- [x] A `workout_summary` or `sleep_summary` grant does not authorize check-in
      access.
- [x] An active `check_in` grant plus both active memberships allows coach
      `SELECT` only, and no coach `INSERT`, `UPDATE`, or `DELETE`.
- [x] A Team A coach cannot read an athlete who shares only through Team B.
- [x] Another athlete cannot use someone else's grant.
- [x] Revoking the sharing grant, the coach membership, or the athlete
      membership each removes coach visibility on the next query, with no token
      refresh or sign-out.
- [x] Revoked grant history never authorizes a read.
- [x] The data subject continues to read their own row after grant or membership
      revocation.
- [x] The coach policy calls `private.can_current_user_read_shared_data` and
      neither duplicates nor weakens it; the TASK-011 migration is unedited.
- [x] The new pgTAP file passes, and the TASK-008, TASK-009, and TASK-011 pgTAP
      files still pass.
- [x] `supabase db lint` reports no warning or error for `public` and `private`.
- [x] Generated types match the local database with zero drift.
- [x] Existing mobile format, lint, typecheck, and unit tests still pass.
- [x] Test fixtures are synthetic, and no health value appears in test output.
- [x] No secret, credential, API URL, JWT secret, database URL, real user, real
      athlete, Garmin data, or protected legacy data is introduced or printed,
      and no dependency or lockfile changes.
- [x] No forbidden path is modified, and no existing migration file is edited.

## Required authorization-negative tests

Synthetic identities only, on the reserved `example.test` domain.

| # | Case | Expected |
| --- | --- | --- |
| 1 | anon `SELECT` | denied, `42501` |
| 2 | anon `INSERT` | denied, `42501` |
| 3 | anon `UPDATE` | denied, `42501` |
| 4 | anon `DELETE` | denied, `42501` |
| 5 | authenticated user inserts and reads their own valid row | succeeds; row readable |
| 6 | data subject updates only their own three health fields | succeeds |
| 7 | data subject names `athlete_profile_id`, `check_in_date`, `id`, `created_at`, or `updated_at` in an `UPDATE` | denied, `42501` |
| 8 | data subject names `id`, `created_at`, or `updated_at` in an `INSERT` | denied, `42501` |
| 9 | user inserts a row for another profile | denied, `42501` policy violation |
| 10 | user reads another user's row | 0 rows |
| 11 | user updates another user's row | 0 rows affected |
| 12 | invalid `rpe` (`-1`, `11`) | rejected, sanitized `22023` (Round 2, M1; was `23514`) |
| 13 | invalid `overall_feeling` (`0`, `6`) | rejected, sanitized `22023` (Round 2, M1; was `23514`) |
| 14 | invalid `pain_status` (`mild`, `''`, `NONE`) | rejected, sanitized `22023` (Round 2, M1; was `23514`) |
| 15 | duplicate athlete and date | rejected, `23505`, and the unique constraint is asserted in the catalog |
| 16 | immutable owner, date, id, and `created_at` changed by a trusted writer | silently restored by the trigger |
| 17 | client-supplied `created_at`/`updated_at` on a trusted insert | overwritten with database time |
| 18 | direct `DELETE` by every client role | denied, `42501`; no `DELETE` policy exists |
| 19 | coach with both active memberships but no grant | 0 rows; helper false |
| 20 | `workout_summary` grant only | 0 rows; helper false |
| 21 | `sleep_summary` grant only | 0 rows; helper false |
| 22 | active `check_in` grant plus both active memberships | coach `SELECT` succeeds |
| 23 | that coach attempts `INSERT` for the athlete | denied |
| 24 | that coach attempts `UPDATE` of the athlete's row | 0 rows affected |
| 25 | that coach attempts `DELETE` | denied, `42501` |
| 26 | Team A coach reads an athlete who shares only through Team B | 0 rows; helper false |
| 27 | Team B coach reads that same athlete | visible |
| 28 | another athlete in the same team tries to use the grant | 0 rows |
| 29 | sharing-grant revocation, then the coach queries again | 0 rows on the next query; helper false |
| 30 | coach-membership revocation, then that coach queries again | 0 rows on the next query; helper false |
| 31 | athlete-membership revocation, then the coach queries again | 0 rows on the next query; helper false |
| 32 | revoked grant history | never authorizes a read; a re-grant is required |
| 33 | the data subject after grant revocation | still reads their own row |
| 34 | the data subject after membership revocation | still reads their own row |
| 35 | catalog: RLS enabled, exactly the four policies, no `DELETE` policy, no policy targeting `anon`/`public`, table and column privileges, function privileges, `SECURITY DEFINER`, empty `search_path`, constraints, index justification, trigger | asserted |
| 36 | the coach policy reuses the TASK-011 helper | the helper appears in the new helper's body; the TASK-011 migration is unedited |
| 37 | existing TASK-008, TASK-009, and TASK-011 pgTAP files | still pass |
| 38 | sanitized-rejection matrix run as the database owner: out-of-range value, unapproved status, null `rpe`, null `athlete_profile_id`, null `check_in_date`, invalid `UPDATE` — six paths | each rejected with the same `22023` and the same fixed message; empty `DETAIL`, empty `HINT`; no column, constraint, row representation, identifier, or date in the message |
| 39 | the same sanitized rejection observed by an **authenticated client** writing their own row: null `overall_feeling`, null `pain_status` — two paths (Round 3, M1 and L1) | `current_user` asserted to be `authenticated`; both rejected with the same `22023` and fixed message; empty `DETAIL`, empty `HINT`; no column, constraint, row representation, identifier, or date in the message |

Cases 38 and 39 were added in Round 3. Together they cover all five
client-supplied required fields: cases 12–14 and 38 cover range, allowed values,
and a null in `rpe`, `athlete_profile_id`, and `check_in_date`; case 39 covers
the null `overall_feeling` and null `pain_status` paths that Round 2 left
untested. Eight rejection paths are probed in total. No `NOT NULL` or `CHECK`
constraint was changed, and the trigger guards were already correct and were not
edited.

No test prints an `rpe`, `overall_feeling`, or `pain_status` value. Assertion
descriptions state the authorization outcome, never a measurement, and
assertions compare counts and error codes rather than echoing values.

This requirement governs **failure** output, not merely passing output. pgTAP
prints the have/got value of a failing assertion, so an assertion that returns a
captured database error message would republish that message at exactly the
moment a disclosure regression occurred. Captured `MESSAGE_TEXT`,
`PG_EXCEPTION_DETAIL`, and `PG_EXCEPTION_HINT` are therefore compared inside the
query, with only a row count returned to the assertion (Round 4). A captured
`RETURNED_SQLSTATE` is returned directly: it is a five-character code from a
closed enumeration and can carry no value, identifier, date, or row.

The guarantee is structural as of Round 5 for assertions and as of Round 6 for
the file as a whole.

`throws_ok()` and `lives_ok()` print the caught database error when they fail,
so all 35 of their calls were replaced with a `SECURITY INVOKER`
`pg_temp.probe_state(text)` probe that runs the statement under the caller's
role and JWT claims, preserves the effects of a successful statement, and
returns only the fixed sentinel `'ok'` or a five-character `SQLSTATE`. No
`throws_ok` or `lives_ok` call remains. The two assertions that compared a raw
`created_at`/`updated_at` against `now()` were converted to row counts in the
same round, so no assertion can print a timestamp.

Round 6 extends the boundary to executable fixture statements, which sat outside
it. A bare `INSERT`, `UPDATE`, or `DELETE` that fails emits psql's native error
including `DETAIL: Failing row contains (...)`. All 17 statements carrying a
health value, athlete identifier, or check-in date are wrapped in
`pg_temp.run_fixture(text)`, which re-raises a fixed sanitized `22023` so an
expected-success failure stays loud and aborts the file rather than continuing
silently. The three affected-row CTE updates use `pg_temp.probe_rowcount(text)`,
which returns `GET DIAGNOSTICS ROW_COUNT` and raises sanitized on error, keeping
owner-update-1-row, cross-athlete-0, and coach-0 at their previous strength
while ensuring an unexpected failure cannot be misread as zero rows. The only
statement left bare is a column-definition-only `CREATE TEMPORARY TABLE`, which
carries no value, identifier, or date.

Round 6 also closes a gap in the probes themselves. PostgreSQL's `WHEN OTHERS`
does not catch `QUERY_CANCELED` or `ASSERT_FAILURE`, so both escaped with a
`CONTEXT` line reproducing the dynamic SQL verbatim. All four temporary helpers
now handle those two conditions by name and re-raise a fixed sanitized
diagnostic, so the condition stays terminal while the statement text is
replaced.

## Expected mechanical update to the TASK-008 test

`001_identity_teams_membership_rls_test.sql` asserts four **schema-wide** counts
over `pg_proc` in the `private` schema: how many functions exist there, and that
all of them are `SECURITY DEFINER` with a pinned, empty `search_path`. TASK-008
set those to `4`; TASK-011 updated them to `7` under an explicit Product Owner
approval recorded in its packet.

TASK-012 necessarily adds two private functions —
`private.enforce_daily_check_in_columns()` and
`private.can_current_user_read_check_in(uuid)` — so those four counts become
arithmetically false the moment this migration applies, and the criterion that
existing pgTAP files keep passing could not otherwise be met.

This packet therefore authorizes, in advance and in full, exactly:

- the four literal counts changed from `7` to `9`;
- one assertion description updated to name which task contributes which
  functions.

No assertion may be removed, weakened, or re-scoped, and no other line of that
file may be edited. The three security properties still apply globally to every
function in `private`, now covering 9 instead of 7, and TASK-012's own file
additionally asserts its two functions by name.

## Privacy classification

**Protected health data.** This is the first table in the product to store it.
`rpe`, `overall_feeling`, and `pain_status` are protected health values under
`AGENTS.md`, and `check_in_date` plus `athlete_profile_id` make them
attributable.

Controls in this task:

- All fixtures are synthetic, transaction-scoped, and rolled back, and use the
  reserved `example.test` domain. No real name, address, or measurement is
  used.
- No health value is printed in test output, an assertion description, a commit
  message, the handoff, or an AI prompt.
- No health value reaches an application log, analytics, a push payload, crash
  context, or session replay, because no application code is added at all.
- No free text, body location, diagnosis, note, image, or attachment column
  exists, so no unstructured health disclosure is possible.
- Coach access is fail-closed and requires an active coach membership, an active
  athlete membership in the same team, and an active `check_in` grant, evaluated
  fresh on every query.
- No service-role key is used. Local Supabase credentials are never printed or
  persisted: `supabase status` and `db:status` are not run, and
  `db:start`/`db:stop` output is fully redirected so only an exit code is
  reported.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm exec supabase --version
```

Start the local stack while suppressing every credential-bearing stream, and
report only the exit code:

```powershell
corepack pnpm db:start *> $null
"start exit: $LASTEXITCODE"

docker ps --format '{{.Names}} {{.Status}}'
```

Rebuild the local database and run the database checks:

```powershell
corepack pnpm exec supabase db reset --local --no-seed
corepack pnpm exec supabase test db --local
corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning
```

Regenerate the types from the **local** stack, strip the PowerShell 5.1 BOM,
format, and then prove zero drift by regenerating into a temporary file and
comparing it against the committed file:

```powershell
corepack pnpm exec supabase gen types typescript --local --schema public `
  | Out-File -FilePath "apps\mobile\src\lib\supabase\database.types.ts" -Encoding utf8
```

Workspace checks:

```powershell
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

Stop the local stack, again reporting only the exit code, and confirm no
container remains:

```powershell
corepack pnpm db:stop *> $null
"stop exit: $LASTEXITCODE"

docker ps -a --filter 'name=supabase_' --format '{{.Names}} {{.Status}}'
```

Repository checks:

```powershell
git diff --check
git status --short
git diff --name-only
```

`*> $null` redirects every PowerShell stream, so the API URL, anon key,
service-role key, JWT secret, and database URL printed by `supabase start` and
`supabase stop` never reach the terminal, the transcript, or a log. Never run
bare `supabase start`, `supabase stop`, `supabase status`, or `db:status` while
a transcript is capturing output, and never run any command with `--linked` or a
remote database URL.

## Dependencies and open decisions

- TASK-007 provides the pinned Supabase CLI 2.109.1 and the local stack.
- TASK-008 provides `profiles`, `teams`, `team_memberships`, and the `private`
  schema.
- TASK-011 provides `sharing_grants`, the grant/revoke RPCs, and
  `private.can_current_user_read_shared_data`, which this task must call rather
  than reimplement.
- TASK-011 was reviewed and merged before TASK-012 began, so this dependency is
  settled rather than pending. Its merged helper at base SHA `69a1471` is the
  version this task calls and the version every verification run here was
  executed against. (Round 3, M2: this bullet previously said TASK-011 was still
  awaiting Codex round-2 review and made the dependency conditional on that
  review's outcome. That was stale — it contradicted both Git history and the
  Round 2 handoff. The conditional language is withdrawn, not merely reworded.)
- Local Analytics remains disabled from TASK-007, so Studio's Logs section is
  empty locally.
- No open product decision remains: decisions 1–10 are approved.

## Known limitations (recorded before implementation)

- No mobile UI is delivered, so the table is unreachable from the app in this
  task. `check_in_date` is a client-supplied local calendar date by decision 2,
  and the database cannot validate that the client's local date is honest; a
  future mobile task owns that.
- There is no client `DELETE` path, so an athlete cannot yet delete a
  check-in. A future privacy-request task owns deletion and export.
- There is no client-reachable path to create teams or memberships, so the
  coach-read path can only be exercised against trusted fixtures until a
  membership-administration task exists.
- Sharing remains per team by TASK-011 decision 1, so an athlete cannot exclude
  one coach of a team they have consented to.
- Correcting a check-in is an update to the same row, so no correction history
  is retained. Only the latest values and `updated_at` survive.
- `check_in_date` accepts any date the client sends, including a future one. No
  approved decision constrains the range, so none is invented here.
- The generated `Insert`/`Update` types will look more permissive than the
  database is, because the generator does not model column-level privileges.
  The database, not the type, is the boundary.

## Rollback

The task is additive and file-scoped. To roll back:

1. `git revert` the TASK-012 commits, or delete
   `platform/supabase/migrations/20260728140000_daily_check_ins_rls.sql`,
   `platform/supabase/tests/database/005_daily_check_ins_rls_test.sql`, this
   packet, and `docs/app/handoffs/TASK-012.md`, and restore
   `platform/apps/mobile/src/lib/supabase/database.types.ts` and
   `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
   from `69a1471`.
2. Run `corepack pnpm exec supabase db reset --local --no-seed` to rebuild the
   local database without the migration.

Nothing is applied to a remote database, so no remote rollback exists or is
needed. No dependency, lockfile, or configuration file is touched.

## Required handoff

Sanitized, at `docs/app/handoffs/TASK-012.md`, using the canonical format and
containing: task; writer; branch and worktree; the task-packet commit SHA; the
implementation and handoff commit SHAs; changed files; acceptance-criteria
results; the exact commands run with sanitized results; privacy and security
impact; known limitations; rollback; remaining reviewer findings; and explicit
confirmation that nothing was pushed, merged, deployed, linked, remotely
migrated, or applied to hosted Supabase.

Then stop for GPT/Codex read-only review. Do not merge into
`feat/mobile-foundation`, and do not remove the worktree.
