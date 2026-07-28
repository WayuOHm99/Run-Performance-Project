# TASK-012 Handoff — Daily Check-In RLS Foundation

Status: Implemented and verified locally. Awaiting GPT/Codex read-only review.

## Task and writer

- Task: `docs/app/tasks/TASK-012-daily-check-in-rls-foundation.md`
- Writer: Claude Code (sole writer)
- Reviewer: GPT/Codex, read-only
- AGY: not used
- Product Owner approved the complete scope and decisions 1–10 before
  implementation started.

## Branch and worktree

- Worktree: `.claude/worktrees/task-012-daily-check-in-rls` (isolated, still in
  place for the reviewer)
- Branch: `feat/TASK-012-daily-check-in-rls`
- Source branch: `feat/mobile-foundation`
- Base SHA: `69a1471be6271d8b1e9b318ed5f70c16059dba4e`
- Task-packet commit (documentation only, made before implementation):
  `1f4c4c2a71d8b10d8b3c24a482fd2bdd12225b28`
- Implementation commit:
  `ec2b72b99d9068c84ce85e96f2cd8d0e53fc5702`
- Handoff commit: `26ca8a98dd0f4301f76abf4bc9044fa0a6cedfec` (the commit that
  first added this file). The branch HEAD is the follow-up documentation-only
  commit that records this SHA in place of the forward reference. Verify with
  `git rev-parse HEAD` and `git log --oneline`.
- Worktree clean at handoff.

### Pre-flight

Confirmed before any edit:

- Source branch `feat/mobile-foundation` at
  `69a1471be6271d8b1e9b318ed5f70c16059dba4e`.
- The source repository had no tracked modifications (only the untracked
  `.claude/worktrees/` directory).
- `feat/mobile-foundation` is an ancestor of the task branch.
- All work happened in the isolated worktree.

The isolated worktree permission canary was requested by its exact absolute
worktree path
`D:\...\.claude\worktrees\task-012-daily-check-in-rls\docs\app\permission-canary\WORKTREE-CANARY.md`
using the built-in `Read` tool only. It was **denied before any content was
returned**. No Bash, PowerShell, `grep`, `cat`, Glob, search, or other fallback
was used against it, and no retry through a different path form was attempted.
No protected legacy path and no root `CLAUDE.md` was read.

## Changed files

| File | Change |
| --- | --- |
| `docs/app/tasks/TASK-012-daily-check-in-rls-foundation.md` | new task packet, committed before implementation |
| `docs/app/handoffs/TASK-012.md` | this handoff |
| `platform/supabase/migrations/20260728140000_daily_check_ins_rls.sql` | new; the only migration added |
| `platform/supabase/tests/database/005_daily_check_ins_rls_test.sql` | new; 166 assertions |
| `platform/apps/mobile/src/lib/supabase/database.types.ts` | regenerated from local Supabase (+41) |
| `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql` | **four literal counts `7` → `9`** and one description reworded — the update the packet authorizes in advance |

Five files, all inside the packet's owned paths. No existing migration was
edited. No dependency manifest, lockfile, `config.toml`, `seed.sql`, mobile
source file, architecture document, or legacy path changed.

## Implemented schema and authorization behaviour

### `public.daily_check_ins`

`id uuid pk default gen_random_uuid()`, `athlete_profile_id uuid not null`
referencing `public.profiles (id) on delete cascade`, `check_in_date date not
null`, `rpe smallint not null`, `overall_feeling smallint not null`,
`pain_status text not null`, `created_at timestamptz not null default now()`,
`updated_at timestamptz not null default now()`.

- **No `team_id`** (decision 1). A check-in is personal athlete data; the same
  row is shared independently with each team through `sharing_grants`.
- **No free-text, note, body-location, diagnosis, image, or attachment column**
  (decision 3). The test pins the exact eight-column set and separately asserts
  that `pain_status` is the only free-form-capable column, so adding one later
  is a test failure rather than a review miss.
- `daily_check_ins_rpe_valid` — `rpe between 0 and 10`.
- `daily_check_ins_overall_feeling_valid` — `overall_feeling between 1 and 5`.
- `daily_check_ins_pain_status_valid` — `pain_status in ('none', 'present')`,
  case-sensitive, and an empty string is rejected.
- `daily_check_ins_athlete_date_unique` — `unique (athlete_profile_id,
  check_in_date)`, which is decision 2 as a constraint rather than an
  application convention.
- `daily_check_ins_athlete_profile_id_fkey` — `on delete cascade`.
  `public.profiles.id` itself cascades from `auth.users`, so deleting the
  account removes every check-in and leaves no orphan health row.

**Indexes.** Only the primary key and the unique constraint's index exist. The
unique index on `(athlete_profile_id, check_in_date)` is leading-column usable
for both query paths this task has — the data subject reading their own rows,
and a coach reading one athlete's rows once authorization has passed. No path
scans by date across athletes, so no date index was added. The test asserts the
exact index set, so a speculative index on a protected-health table cannot be
added silently.

### Database-controlled and immutable columns

Two independent layers, in this order:

1. **Column-level privileges.** `authenticated` holds
   `INSERT (athlete_profile_id, check_in_date, rpe, overall_feeling,
   pain_status)` and `UPDATE (rpe, overall_feeling, pain_status)` only. A client
   cannot *name* `id`, `created_at`, or `updated_at` in an insert, and cannot
   name `id`, `athlete_profile_id`, `check_in_date`, `created_at`, or
   `updated_at` in an update. Each attempt fails `42501` at the privilege layer,
   before RLS and before the trigger.
2. **`private.enforce_daily_check_in_columns()`** — `SECURITY DEFINER`,
   `search_path = ''`, `before insert or update`. On insert it overwrites
   `created_at` and `updated_at` with `pg_catalog.now()`, so a row cannot be
   backdated. On update it restores `id`, `athlete_profile_id`,
   `check_in_date`, and `created_at` from the old row and re-stamps
   `updated_at`. This keeps decision 4 true for any future writer inside the
   trusted boundary, not merely for clients.

The function name deliberately contains no `health` substring, so the TASK-008
assertion that no broad health-data authorization helper exists in `private`
stays meaningful and passing.

### Read authorization — reuse, not reimplementation

`private.can_current_user_read_check_in(p_athlete_profile_id uuid) returns
boolean` — `SECURITY DEFINER`, `stable`, `search_path = ''`, in the non-exposed
`private` schema.

Because the table has no `team_id`, the helper enumerates the teams in which the
target holds an active athlete membership and asks the **TASK-011 helper**,
unchanged, whether the caller may read `check_in` data for that athlete in that
team:

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

It adds no authorization condition of its own and removes none. Every coach-role
check, athlete-membership check, grant check, category check, and revocation
check stays inside `private.can_current_user_read_shared_data`. Its own outer
predicates are a strict subset of what that helper re-checks anyway, so it
cannot widen access; it only supplies candidate team ids. Three catalog
assertions enforce this structurally: the body must mention
`can_current_user_read_shared_data`, and must **not** mention `sharing_grants`
or `coach`. Forking that logic into this table breaks the build.

Being `SECURITY DEFINER`, the enumeration is not filtered by the
`team_memberships` policies, which keeps the coach policy fail-closed rather
than dependent on another table's read policy, and keeps it non-recursive.

### Privileges and RLS

- RLS enabled on `daily_check_ins`.
- All default privileges revoked from `anon` and `authenticated` first, because
  Supabase grants `ALL` on a new `public` table to both. `anon` holds **no**
  table privilege and **no** column privilege, so every anonymous statement
  fails `42501` before RLS is consulted.
- `authenticated` holds table-wide `SELECT` only, plus the two column-level
  write grants above. No `DELETE`, `TRUNCATE`, `REFERENCES`, or `TRIGGER`.
- **No `DELETE` privilege and no `DELETE` policy for any client role.**
- Four policies, all `to authenticated`, none targeting `anon` or `public`:

| Policy | Command | Expression |
| --- | --- | --- |
| `daily_check_ins_select_own` | `SELECT` | `athlete_profile_id = (select auth.uid())` |
| `daily_check_ins_select_shared_for_coach` | `SELECT` | `private.can_current_user_read_check_in(athlete_profile_id)` |
| `daily_check_ins_insert_own` | `INSERT` | `WITH CHECK athlete_profile_id = (select auth.uid())` |
| `daily_check_ins_update_own` | `UPDATE` | `USING` and `WITH CHECK`, both `athlete_profile_id = (select auth.uid())` |

The coach path is `SELECT` only, and two catalog assertions enforce it: no write
policy may consult the coach read helper, and every write policy must constrain
the row to `auth.uid()`.

### Recorded reading of decision 8

Decision 8 is enforced as "no user may insert, update, or delete a row whose
`athlete_profile_id` is not their own", asserted against an active coach of the
athlete's own team who currently *can* read that row.

It is deliberately **not** implemented as "a user holding any coach membership
may never own a check-in", because that would contradict decision 6 — self
insert and self update are identity-owned and independent of team membership,
and the model already supports a user who coaches one team and competes in
another. A coach writing their own check-in is the data subject acting on their
own data; the test asserts that row is visible to nobody else, including
athletes of their team. This reading is recorded in the task packet for the
reviewer to accept or reject.

## Acceptance-criteria results

All criteria met.

| Criterion | Where it is enforced and proved |
| --- | --- |
| Approved columns, types, constraints, FK; no `team_id`, no free-text column | pinned exact column set; `hasnt_column('team_id')`; only `pain_status` is free-form-capable |
| Decisions 1–10 enforced by PostgreSQL, not client code | no application code was added at all |
| `rpe`, `overall_feeling`, `pain_status` range and value rejection | seven `23514` assertions, including empty string and wrong case |
| Duplicate athlete/date rejected, uniqueness asserted as a constraint | `23505` at owner and client level; `contype = 'u'` and its exact column list asserted |
| `id`, `created_at`, `updated_at` database-controlled; owner, date, id, `created_at` immutable | column privileges (`42501` ×8) plus trigger restoration asserted |
| `updated_at` advances only under database control | forged value overwritten on both insert and update |
| `anon` holds nothing; all four verbs denied | `42501` ×4, plus zero table and zero column privileges asserted |
| `authenticated` privileges are exactly the approved minimum | table-wide `SELECT` only; insert/update column lists pinned by `aclexplode` |
| `DELETE` denied for every client role; no `DELETE` policy | `42501` for anon, data subject, teammate, and coach; zero `DELETE` policies |
| Data subject inserts, reads, updates only the three health fields | positive controls plus five column-privilege denials |
| No insert for another profile; no read or update of another user's row | `42501` on insert; 0 rows on read; snapshot join proves no mutation |
| Coach with both memberships but no grant sees zero rows | 0 rows, helper false |
| `workout_summary`/`sleep_summary` grant does not authorize check-in access | 0 rows, helper false |
| Active `check_in` grant plus both memberships allows `SELECT` only | visible; coach insert `42501`, coach update changes nothing, coach delete `42501` |
| Team A coach cannot read an athlete sharing only through Team B | 0 rows, helper false; the Team B coach sees the same row |
| Another athlete cannot use the grant | 0 rows, helper false |
| Grant, coach-membership, and athlete-membership revocation each remove visibility on the next query | three separate scenarios, each 0 rows with no token change |
| Revoked grant history never authorizes a read | history row retained and asserted; access stays 0 until an explicit new grant |
| Data subject still reads their own row after revocation | asserted after grant revocation and after both membership revocations |
| Coach policy reuses the TASK-011 helper | three body assertions plus the policy-delegation assertion; TASK-011 migration unedited |
| New file passes; TASK-008/009/011 files still pass | 5 files, 559 assertions, PASS |
| `db lint` clean for `public` and `private` | exit 0, no schema errors |
| Generated types match the local database, zero drift | `git diff --no-index` exit 0 against a fresh regeneration |
| Mobile format, lint, typecheck, unit tests pass | all exit 0; 327 tests |
| Fixtures synthetic; no health value in test output | `example.test` domain; every assertion compares a count, a column name, an error code, or a snapshot join |
| No secret, credential, real user, Garmin, or legacy data; no dependency change | lockfile unchanged; nothing printed |
| No forbidden path modified | five changed files, all owned |

## Negative-test matrix and results

All 37 packet cases pass. `005` contributes 166 assertions.

| # | Case | Result |
| --- | --- | --- |
| 1–4 | anon `SELECT`/`INSERT`/`UPDATE`/`DELETE` | PASS — `42501` ×4, plus the read helper denied |
| 5 | data subject inserts and reads own row | PASS — 1 row, both timestamps from the database |
| 6 | data subject updates own three health fields | PASS |
| 7 | update naming owner, date, id, `created_at`, `updated_at` | PASS — `42501` ×5 |
| 8 | insert naming id, `created_at`, `updated_at` | PASS — `42501` ×3 |
| 9 | insert for another profile | PASS — `42501` |
| 10 | read another user's row | PASS — 0 rows, both directions |
| 11 | update another user's row | PASS — snapshot join unchanged at 6 rows |
| 12 | invalid `rpe` | PASS — `23514` at both bounds |
| 13 | invalid `overall_feeling` | PASS — `23514` at both bounds |
| 14 | invalid `pain_status` | PASS — `23514` for a third word, empty string, and wrong case |
| 15 | duplicate athlete and date | PASS — `23505`; constraint and its column list asserted |
| 16 | trusted writer moves owner, date, id, `created_at` | PASS — restored by the trigger |
| 17 | client-supplied timestamps on a trusted insert | PASS — overwritten with database time |
| 18 | `DELETE` by every client role | PASS — `42501` ×4; zero `DELETE` policies |
| 19 | coach, both memberships, no grant | PASS — 0 rows, helper false |
| 20 | `workout_summary` grant only | PASS — 0 rows, helper false |
| 21 | `sleep_summary` grant only | PASS — covered by the same athlete holding both wrong categories |
| 22 | active `check_in` grant plus both memberships | PASS — visible |
| 23 | that coach inserts for the athlete | PASS — `42501` |
| 24 | that coach updates the athlete's row | PASS — snapshot join unchanged at 6 rows |
| 25 | that coach deletes | PASS — `42501` |
| 26 | Team A coach vs an athlete sharing only through Team B | PASS — 0 rows, helper false |
| 27 | Team B coach reads that athlete | PASS — visible, and 0 for Team A rows |
| 28 | teammate athlete tries to use the grant | PASS — 0 rows, helper false |
| 29 | grant revoked, coach queries again | PASS — 0 on the next query, helper false |
| 30 | coach membership revoked | PASS — 0 on the next query, helper false; another active coach unaffected |
| 31 | athlete membership revoked | PASS — 0 on the next query, helper false |
| 32 | revoked grant history | PASS — retained, authorizes nothing; reactivation revives nothing; only an explicit new grant restores access |
| 33 | data subject after grant revocation | PASS — still reads own row |
| 34 | data subject after membership revocation | PASS — still reads own row, both revocation kinds |
| 35 | catalog assertions | PASS — RLS, exactly four policies, zero `DELETE` policies, no policy targeting `anon`/`public`, table and column privileges, function privileges, `SECURITY DEFINER` ×2, empty `search_path` ×2, constraints, exact index set, trigger |
| 36 | coach policy reuses the TASK-011 helper | PASS — body mentions it, mentions neither `sharing_grants` nor `coach`, and the policy delegates to the helper |
| 37 | TASK-008, TASK-009, TASK-011 pgTAP files | PASS |

Positive controls sit alongside every denial — the coach sees exactly three rows
while the same query returns 0 for a revoked coach and 1 for the data subject —
so the role switching is proven effective rather than vacuously passing.

## Mutation evidence

The suite passed on its first run, which is not by itself evidence that it
constrains anything. Two mutations were applied to the live local database and
the suite re-run:

| Mutation | Result |
| --- | --- |
| Coach policy swapped to the TASK-008 identity helper `private.is_coached_by_current_user` — active membership treated as sufficient, the exact failure this task exists to prevent | **FAIL — 8 of 166**: no-grant athlete visible, wrong-category athlete visible, Team B–only athlete visible to the Team A coach, coach total wrong, grant revocation ineffective, revoked history authorizing a read, reactivation restoring access, and the policy-delegation assertion |
| `UPDATE (athlete_profile_id, check_in_date, updated_at)` additionally granted to `authenticated` | **FAIL — 4 of 166**: the three column-privilege denials and the pinned update-column list |

Both mutations were then discarded by `supabase db reset --local --no-seed`, and
the suite passes again at 559 assertions. Note that under the second mutation
the stored data still stayed correct, because the trigger restored the immutable
columns — which is the two-layer design working, and is why the privilege
assertions are written separately from the immutability assertions.

## Commands run and results

Local database only. No `--linked`, no project ref, no remote URL, no hosted
Supabase contact.

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0, lockfile unchanged |
| `corepack pnpm exec supabase --version` | 2.109.1 |
| `corepack pnpm db:start *> $null` | exit 0, 10 containers healthy |
| `corepack pnpm exec supabase db reset --local --no-seed` | exit 0, all four migrations applied |
| `corepack pnpm exec supabase test db --local` | **PASS — 5 files, 559 assertions** (173 + 43 + 154 + 23 + 166) |
| same, coach policy mutated to the identity helper | **FAIL — `005` fails 8/166** |
| same, column grants widened | **FAIL — `005` fails 4/166** |
| `corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, no schema errors |
| `supabase gen types typescript --local --schema public` | exit 0, BOM stripped, Prettier-formatted |
| type drift: fresh regeneration compared with `git diff --no-index` | exit 0, identical, no drift |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | **327 passed, 18 files** |
| `corepack pnpm db:stop *> $null` | exit 0, no Supabase container remains |
| `git diff --check` | clean |
| `git status --short` | clean at handoff |

`db:start` and `db:stop` were run with `*> $null`, so the API URL, anon key,
service-role key, JWT secret, and database URL never reached the terminal, the
transcript, or a log. `supabase status` and `db:status` were not run. Container
health was judged only by exit code and by `docker ps` names and status.

Two issues were found and fixed during verification, both in the verification
tooling rather than in the delivered code:

- Docker Desktop was not running, so the first `db:start` failed. It was started
  and the stack came up cleanly.
- The BOM check used `[System.IO.File]::ReadAllText`, which silently strips a
  BOM on decode, so it reported "no BOM" while a BOM was in fact written by
  PowerShell 5.1's `Out-File -Encoding utf8`. It was replaced with a byte-level
  check, the BOM was removed, and drift was then proved with
  `git diff --no-index` rather than PowerShell string comparison. Two earlier
  "TYPE DRIFT DETECTED" readings were artifacts of that comparison and of
  Prettier's `endOfLine: "auto"` config not applying to a file outside
  `platform/`; the committed file has zero drift.

## Privacy and security impact

**This is the first table in the product to store protected health data.**
`rpe`, `overall_feeling`, and `pain_status` are protected health values under
`AGENTS.md`, and `athlete_profile_id` plus `check_in_date` make them
attributable.

- All fixtures are synthetic, transaction-scoped, and rolled back, on the
  reserved `example.test` domain. No real name, address, or measurement was
  used or read.
- **No health value is printed in test output.** Every assertion compares a row
  count, a column name, an error code, or a snapshot join, and no assertion
  description names a measurement. Under both mutations the failure output named
  only authorization rules. No health value appears in a commit message, this
  handoff, or an AI prompt.
- No health value can reach an application log, analytics, a push payload, crash
  context, or session replay, because no application code was added.
- No free text, body location, diagnosis, note, image, or attachment column
  exists, so unstructured health disclosure is structurally impossible.
- Coach access is fail-closed and evaluated fresh on every query: an active coach
  membership, an active athlete membership in the same team, and an active
  `check_in` grant. No authorization state lives in the token, so every
  revocation path takes effect on the next query.
- No service-role key was used. No credential, API URL, JWT secret, database
  URL, access token, email address, or real user id was printed or persisted.
- The security posture is strictly additive: `anon` gains nothing anywhere,
  `authenticated` gains `SELECT` plus two narrow column-level write grants on
  one new table and `EXECUTE` on one new helper, and no existing grant or policy
  was loosened.

## Known limitations

- No mobile UI is delivered, so the table is unreachable from the app today.
- `check_in_date` is a client-supplied local calendar date by decision 2. The
  database cannot verify that the client's local date is honest, and accepts any
  date including a future one, because no approved decision constrains the
  range. A future mobile task owns that.
- There is no client `DELETE` path, so an athlete cannot yet delete a check-in.
  A future privacy-request task owns deletion and export.
- Correcting a check-in updates the same row, so no correction history is
  retained. Only the latest values and `updated_at` survive. If an audit trail
  of edits is later required, it is a new decision and a new table.
- There is no client-reachable path to create teams or memberships, so the
  coach-read path can only be exercised against trusted fixtures until a
  membership-administration task exists.
- Sharing stays per team by TASK-011 decision 1, so an athlete cannot exclude one
  coach of a team they have consented to.
- The generated `Insert`/`Update` types look more permissive than the database
  is, because the generator does not model column-level privileges. The
  database, not the type, is the boundary.
- The coach read helper enumerates the target's active athlete memberships and
  calls the TASK-011 helper once per candidate team. That is negligible at
  realistic team counts, but it is a per-row policy call and would deserve
  measurement before a large coach-side list view is built.
- TASK-011 is still awaiting Codex round-2 review. This task builds on its
  committed state at the base SHA; if that review changes the TASK-011 helper's
  signature or semantics, this task's helper and tests must be re-verified.
- Local Analytics remains disabled from TASK-007, so Studio's Logs section is
  empty locally.

## Rollback

1. `git revert` the TASK-012 commits, or delete
   `platform/supabase/migrations/20260728140000_daily_check_ins_rls.sql`,
   `platform/supabase/tests/database/005_daily_check_ins_rls_test.sql`, the task
   packet, and this handoff; restore
   `platform/apps/mobile/src/lib/supabase/database.types.ts` and
   `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`
   from `69a1471`.
2. Run `corepack pnpm exec supabase db reset --local --no-seed` to rebuild the
   local database without the migration.

Nothing was applied to a remote database, so no remote rollback exists or is
needed. No dependency, lockfile, or configuration file was touched.

## Remaining reviewer findings

None. This is the first review round for TASK-012; no Codex finding has been
raised or is outstanding.

Two points are flagged for the reviewer's explicit attention:

1. **The reading of decision 8** recorded in the task packet and above: a coach
   is denied any write path into another person's check-in, but is not
   prohibited from owning their own, because decision 6 makes self-write
   identity-owned and independent of role. If the Product Owner intends the
   stricter reading, it is a one-line policy change plus test updates.
2. **The mechanical `7` → `9` update** to the TASK-008 pgTAP file, authorized in
   advance by this task's packet, following the precedent set by TASK-009 and
   TASK-011. The diff contains exactly four literals and one description and
   nothing else.

## Confirmation

Nothing was pushed, merged, deployed, linked to a hosted project, remotely
migrated, or applied to hosted Supabase. No `db push`, no `--linked`, no remote
database URL, no project ref, and no service-role credential was used at any
point. No production data was accessed and no protected legacy path was read.

The branch `feat/TASK-012-daily-check-in-rls` is local and was not merged into
`feat/mobile-foundation`. The worktree still exists and is clean, and was not
cleaned up. The local Supabase stack is stopped with no container remaining.

Stopping here for GPT/Codex read-only review.
