# TASK-012 Handoff — Daily Check-In RLS Foundation

Status: Implemented, reviewed three times by GPT/Codex, and Round 4 fixes
applied and verified locally. Awaiting GPT/Codex Round 4 read-only review.

Round 1 and Round 2 history below is retained. Everything a later round altered
is recorded in its own "Round N — Codex findings and fixes" section, and figures
a later round superseded are corrected in place with the earlier value noted.

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
  first added this file), followed by a documentation-only commit recording that
  SHA in place of the forward reference. Verify with `git rev-parse HEAD` and
  `git log --oneline`.
- Worktree clean at handoff.

### Commit ledger

| Commit | Purpose | Changed files |
| --- | --- | --- |
| `1f4c4c2` | task packet, before implementation | 1 |
| `ec2b72b` | implementation | 4 |
| `26ca8a9` | this handoff | 1 |
| `7d41c0c` | record the handoff SHA | 1 |
| `9d6acd3` | Round 2 fixes | **4** |
| `1313bf0` | record the Round 2 SHA | 1 |
| `8f28893` | Round 3 fixes | 3 |
| `7eca322` | record the Round 3 SHA | 1 |
| `406f149` | Round 4 fixes | 3 |
| branch HEAD | record the Round 4 SHA | 1 |
| **Complete TASK-012 diff against `69a1471`** | | **6** |

**Correction of record (Round 3, L2).** The body of commit `9d6acd3` says
"Local only: 5 files". That is wrong: it changed exactly four files. Six is the
count for the complete TASK-012 scope, not for that commit. Commit `9d6acd3` was
not amended, rebased, or rewritten — this table is the correction.

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
| `platform/supabase/tests/database/005_daily_check_ins_rls_test.sql` | new; 190 assertions (166 in Round 1, 181 in Round 2) |
| `platform/apps/mobile/src/lib/supabase/database.types.ts` | regenerated from local Supabase (+41) |
| `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql` | **four literal counts `7` → `9`** and one description reworded — the update the packet authorizes in advance |

Six files, all inside the packet's owned paths. (Round 1 said "five" while
listing six; the count was wrong, not the list.) No existing migration was
edited. No dependency manifest, lockfile, `config.toml`, `seed.sql`,
architecture document, or legacy path changed.

No handwritten or behavioural mobile source changed. The generated
`database.types.ts` did change: it is a build artifact regenerated from the
local schema, it contains no logic, and its content is fully determined by the
migration. No mobile screen, component, hook, repository, navigation entry, or
test was added or edited.

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
   `check_in_date`, and `created_at` from the old row, and sets `updated_at` to
   `greatest(clock_timestamp(), old.updated_at + interval '1 microsecond')` so
   it strictly advances while staying database-controlled (Round 2, M2). This
   keeps decision 4 true for any future writer inside the trusted boundary, not
   merely for clients. The same trigger also rejects every invalid
   client-supplied field with one sanitized `22023` error before PostgreSQL can
   emit a failing-row `DETAIL` (Round 2, M1).

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
| `rpe`, `overall_feeling`, `pain_status` range and value rejection | seven sanitized `22023` assertions, including empty string and wrong case; the `23514` constraints remain behind them |
| Duplicate athlete/date rejected, uniqueness asserted as a constraint | `23505` at owner and client level; `contype = 'u'` and its exact column list asserted |
| `id`, `created_at`, `updated_at` database-controlled; owner, date, id, `created_at` immutable | column privileges (`42501` ×8) plus trigger restoration asserted |
| `updated_at` advances only under database control | forged value overwritten on both insert and update, and proved strictly increasing across two updates in one transaction |
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
| New file passes; TASK-008/009/011 files still pass | 5 files, 583 assertions, PASS |
| `db lint` clean for `public` and `private` | exit 0, no schema errors |
| Generated types match the local database, zero drift | `git diff --no-index` exit 0 against a fresh regeneration |
| Mobile format, lint, typecheck, unit tests pass | all exit 0; 327 tests |
| Fixtures synthetic; no health value in test output | `example.test` domain; every assertion compares a count, a constant sentinel, a column name, an error code, a boolean, or a snapshot join. Captured `MESSAGE_TEXT`, `DETAIL`, and `HINT` are compared inside the query and never returned to an assertion (Round 4) |
| No secret, credential, real user, Garmin, or legacy data; no dependency change | lockfile unchanged; nothing printed |
| No forbidden path modified | six changed files, all owned |

## Negative-test matrix and results

All 39 packet cases pass — 37 through Round 2, plus cases 38 and 39 added in
Round 3. `005` contributes 190 assertions (166 in Round 1, 181 in Round 2).

| # | Case | Result |
| --- | --- | --- |
| 1–4 | anon `SELECT`/`INSERT`/`UPDATE`/`DELETE` | PASS — `42501` ×4, plus the read helper denied |
| 5 | data subject inserts and reads own row | PASS — 1 row, both timestamps from the database |
| 6 | data subject updates own three health fields | PASS — affects exactly 1 row, and the post-image holds the attempted values |
| 7 | update naming owner, date, id, `created_at`, `updated_at` | PASS — `42501` ×5 |
| 8 | insert naming id, `created_at`, `updated_at` | PASS — `42501` ×3 |
| 9 | insert for another profile | PASS — `42501` |
| 10 | read another user's row | PASS — 0 rows, both directions |
| 11 | update another user's row | PASS — affects exactly 0 rows; snapshot join unchanged at 6 rows |
| 12 | invalid `rpe` | PASS — sanitized `22023` at both bounds |
| 13 | invalid `overall_feeling` | PASS — sanitized `22023` at both bounds |
| 14 | invalid `pain_status` | PASS — sanitized `22023` for a third word, empty string, and wrong case |
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
| 38 | sanitized-rejection matrix, six paths, run as the owner | PASS — one `22023`, one fixed message, empty `DETAIL`, empty `HINT`, nothing disclosed in the message |
| 39 | sanitized rejection observed by an authenticated client — null `overall_feeling`, null `pain_status` (Round 3) | PASS — `current_user` is `authenticated`; same `22023`, same fixed message, empty `DETAIL`, empty `HINT`, nothing disclosed |

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
  count, a constant sentinel, a column name, an error code, a boolean, or a
  snapshot join, and no assertion description names a measurement. The Round 2
  affected-row checks return the literal `1`, never a column. No health value
  appears in a commit message, this handoff, or an AI prompt.

  > **Round 4 correction.** This bullet previously claimed that "under all four
  > mutations the failure output named only authorization rules". That was
  > wrong. The Round 3 guard-removal mutation made the two
  > `is((select min(err_message) ...), 'daily check-in rejected: invalid
  > input', ...)` assertions fail, and pgTAP prints the captured value of a
  > failing `is()`. The failure output therefore contained PostgreSQL's native
  > `null value in column "overall_feeling" ... violates not-null constraint`
  > message — a column-bearing database error, not an authorization rule. Round
  > 4 replaces both assertions with counted forms; see the Round 4 section.
  >
  > To be precise about impact: **no real data and no protected production value
  > was exposed.** Every fixture in that run was synthetic, the mutation was
  > local, and the message named a column rather than any measurement. The
  > defect was in the assertion design, which violated the approved
  > failure-output-safety requirement, not in what happened to be disclosed on
  > that particular run. The requirement exists precisely so that the outcome
  > does not depend on which row happened to fail.
- **A rejected write discloses nothing** (Round 2, M1). Every invalid client
  write is refused with one fixed sanitized `22023` error carrying no field
  name, value, identifier, date, row representation, `DETAIL`, or `HINT`, so a
  protected-health row can no longer travel into a PostgREST error object or a
  log line through a constraint failure.
- No health value can reach an application log, analytics, a push payload, crash
  context, or session replay, because no application code was added.
- No free text, body location, diagnosis, note, image, or attachment column
  exists, so unstructured health disclosure is structurally impossible.
- Coach access is fail-closed and evaluated fresh on every query: an active coach
  membership, an active athlete membership in the same team, and an active
  `check_in` grant. No authorization state lives in the token, so every
  revocation path takes effect on the next query.
- No service-role key was used. No credential, API URL, JWT secret, database
  URL, access token, real email address, or real user id was printed or
  persisted. Synthetic `@example.test` fixture addresses are committed in the
  test file, which is allowed and intended: `example.test` is a reserved,
  non-routable domain and the addresses belong to nobody.
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
- TASK-011 was reviewed and merged before this task started, and its merged
  state at the base SHA is what this task builds on. (Round 1 of this handoff
  claimed TASK-011 was still awaiting Codex review; that was stale and is
  withdrawn.) `private.can_current_user_read_shared_data` is therefore a settled
  dependency, not a moving one.
- A unique violation (`23505`) and a foreign-key violation (`23503`) still
  return PostgreSQL's native error, whose DETAIL can name the athlete id and the
  calendar date. Neither carries an `rpe`, `overall_feeling`, or `pain_status`,
  so no health measurement leaks, but the fact that a given athlete checked in
  on a given date can. M1 scoped the sanitized error to the required-field,
  range, and status paths; narrowing these two is a follow-up decision.
- Local Analytics remains disabled from TASK-007, so Studio's Logs section is
  empty locally.

## Round 2 — Codex findings and fixes

GPT/Codex reviewed Round 1 read-only and raised one high and three medium
findings. The Product Owner approved all four. No other change was made, no
approved decision was altered, and AGY was not used.

Round 2 fix commit: `9d6acd3006049cda4d7d6b894baad7026f1b463f` (the commit that applied all four fixes). The branch HEAD is the follow-up documentation-only commit that records this SHA in place of the forward reference. Verify with `git log --oneline`.

### H1 — the UPDATE tests could not fail

`lives_ok` cannot distinguish a successful update from one that matched no row,
because RLS filters rows rather than raising, so an update that reaches nothing
still succeeds. The Round 1 companion check was worse than neutral: it compared
`updated_at` to `now()`, and `now()` is transaction time, so the value already
matched from the insert earlier in the same transaction. The negative probes
assigned each column to itself and their snapshots omitted `updated_at`, so a
widened UPDATE policy could have modified those rows and still passed.

Fixed by counting the rows every UPDATE actually affected, via
`UPDATE ... RETURNING 1` consumed by a CTE, on all three paths:

| Path | Asserted affected rows |
| --- | --- |
| the data subject updating their own row | exactly 1 |
| another athlete updating the data subject's row | exactly 0 |
| a coach updating a row they are authorized to read | exactly 0 |

`RETURNING` yields a constant sentinel, never a column, so no protected value
reaches the output. All three attempts now assign values that differ from the
stored ones, the post-image is asserted against the attempted values, the
snapshot joins are kept as defence in depth, and `updated_at` was added to the
snapshot so a mutation that fired the trigger without changing the health
columns is still caught.

### M1 — a constraint failure could disclose the whole row

A native `NOT NULL` or `CHECK` failure carries
`DETAIL: Failing row contains (...)`, which reproduces the athlete id, the date,
and all three health values, and that string reaches PostgREST error objects and
observability logs.

The existing `BEFORE` trigger now validates every client-supplied required field
— `athlete_profile_id`, `check_in_date`, `rpe` and its range, `overall_feeling`
and its range, and `pain_status` against the two approved values — and raises a
single sanitized exception with SQLSTATE `22023` and the fixed message
`daily check-in rejected: invalid input`. One branch and one message serve every
failure mode, so the error cannot be used to probe which field was wrong. No
field name, value, identifier, date, `DETAIL`, or `HINT` is emitted.

Every declarative `NOT NULL` and `CHECK` constraint is kept unchanged. They
remain the real guarantee for any writer that could bypass the trigger; the
trigger only ensures a client never reaches them. No RPC and no new schema
surface was added — the test helper lives in `pg_temp` and dies with the
transaction.

Six rejection paths are probed as the database owner — out-of-range value,
unapproved status, a null `rpe`, a null `athlete_profile_id`, a null
`check_in_date`, and an invalid `UPDATE` — capturing `RETURNED_SQLSTATE`,
`MESSAGE_TEXT`, `PG_EXCEPTION_DETAIL`, and `PG_EXCEPTION_HINT`. The tests assert
one distinct SQLSTATE across all six, one distinct message, empty detail and
hint everywhere, and that no message names a column, a constraint, a row
representation, an identifier, or a date.

> **Round 3 correction (M1).** This paragraph originally claimed the matrix
> probed "a null in each required field". It did not: a null `overall_feeling`
> and a null `pain_status` were never probed, so removing either trigger guard
> would have left the suite green. Round 3 adds both, through the authenticated
> client path — see the Round 3 section below.

### M2 — `updated_at` advancement was not proved

The trigger stamped transaction-stable `now()`, and the whole pgTAP file runs in
one transaction, so `updated_at = now()` held whether or not the timestamp ever
moved.

`updated_at` is now
`greatest(clock_timestamp(), old.updated_at + interval '1 microsecond')` on
update. `clock_timestamp()` advances inside a transaction, and the `greatest`
floor makes the increase strict deterministically, with no sleep and no
dependence on observable clock movement. It stays entirely database-controlled:
no client role holds `UPDATE` on the column. `created_at` is untouched and still
restored from `OLD` on every update, and inserts still stamp both columns with
`now()`.

The regression captures the timestamp into a temporary table before the update
and asserts the post-update value is strictly greater, at both the trusted-writer
and the data-subject level, and separately asserts that a second update in the
same transaction advances it again — the case transaction-stable `now()` could
never satisfy. Only booleans are compared, so no timestamp is printed.

### M3 — documentation was internally inconsistent

- The task packet status moved from `Approved` to implemented-and-verified,
  awaiting Codex Round 2.
- The changed-file count is corrected from five to six. Round 1 listed six files
  and miscounted them in prose; the list was always right.
- "No mobile source file changed" is replaced with "no handwritten or
  behavioural mobile source changed". The generated `database.types.ts` did
  change, and saying otherwise was wrong.
- "No email address" is replaced with "no real email address". Synthetic
  `@example.test` fixture addresses are committed and allowed.
- The stale claim that TASK-011 was awaiting Codex review is withdrawn. TASK-011
  was reviewed and merged and is this task's base.
- Acceptance criteria and the negative-test matrix are re-checked against this
  round's evidence only, and superseded figures carry their Round 1 value.

### Round 2 mutation evidence

Both mutations required by the finding were applied to the live local database
and the suite re-run, then discarded with `supabase db reset --local --no-seed`:

| Mutation | Result |
| --- | --- |
| UPDATE policy widened to `using (true) with check (true)` | **FAIL — 3 of 181**: the coach affected-row count, the coach snapshot join, and the pinned write-policy expression |
| owner UPDATE policy denied while still containing `auth.uid()` — `using (athlete_profile_id = (select auth.uid()) and false)` | **FAIL — 3 of 181**: the owner affected-row count, the post-image check, and the `updated_at` advancement check |

The second mutation is the direct proof that H1 is closed: under Round 1's
assertions it would have passed silently, because `lives_ok` tolerates a
zero-row update and `updated_at` already equalled `now()`.

One honest detail about the first mutation. The cross-athlete affected-row
assertion did **not** fail under it, and that is correct rather than vacuous:
PostgreSQL also applies `SELECT` policies to an `UPDATE` that reads columns, so
a non-coach still cannot reach the row even with the UPDATE policy wide open.
The coach path is the one a widened UPDATE policy actually exposes, because the
coach can legitimately read the row, and that is exactly what failed.

### Round 2 verification

Full approved suite, local stack only:

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0, lockfile unchanged |
| `corepack pnpm exec supabase --version` | 2.109.1 |
| `corepack pnpm db:start *> $null` | exit 0, 10 containers, 8 reporting a health check |
| `corepack pnpm exec supabase db reset --local --no-seed` | exit 0 |
| `corepack pnpm exec supabase test db --local` | **PASS — 5 files, 574 assertions** (`005` contributes 181) |
| same, UPDATE policy widened | **FAIL — `005` fails 3/181** |
| same, owner UPDATE policy denied | **FAIL — `005` fails 3/181** |
| `corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, no schema errors |
| `supabase gen types typescript --local --schema public` | exit 0 |
| type drift: fresh regeneration compared with `git diff --no-index` | exit 0, identical, no drift |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | **327 passed, 18 files** |
| `git diff --check` | clean |
| `corepack pnpm db:stop *> $null` | exit 0, no Supabase container remains |

The generated types are byte-identical to the committed file: M1 and M2 changed
a trigger body, not a column, so the schema surface is unchanged.

Two process notes, both mine and neither affecting the delivered code. The first
plan count was one too low because I mis-added the assertion tally, and the
runner caught it. The first drift check reported 28 added lines because I
omitted `--schema public`, which is the canonical flag recorded in the packet and
in `apps/mobile/README.md`; with the correct command the diff is empty.

## Round 3 — Codex findings and fixes

Round 1 and Round 2 records above are retained. Figures Round 3 superseded are
corrected in place with the earlier value noted. Round 3 changed three files and
no migration: `005_daily_check_ins_rls_test.sql`, the task packet, and this
handoff.

### M1 — sanitized NULL-path coverage was incomplete

The Round 2 matrix probed a null `rpe`, `athlete_profile_id`, and
`check_in_date`, but never a null `overall_feeling` or a null `pain_status`,
while this handoff claimed it covered "a null in each required field". The
migration guards were correct, but nothing held them in place: deleting either
guard left the suite green and let PostgreSQL's native `NOT NULL` error reach
the client.

The two missing paths are now probed, and — per L1 — they are the paths run
through the authenticated client rather than a second owner-path pair, so no
redundant case was added. Both capture `RETURNED_SQLSTATE`, `MESSAGE_TEXT`,
`PG_EXCEPTION_DETAIL`, and `PG_EXCEPTION_HINT` and assert one distinct SQLSTATE
(`22023`), one distinct message, empty detail, empty hint, and no column,
constraint, row representation, identifier, or date in the message.

The migration was **not** changed. Its guards were already correct, and no
defect was found in them, so nothing was edited there.

### L1 — the sanitized-error probes did not exercise the client path

Every Round 2 probe ran as the database owner, which proves the trigger raises a
sanitized error but not that a real client observes one — a client also passes
through column privileges and RLS.

The two new probes run under `set local role authenticated` with synthetic JWT
claims, inserting the caller's **own** row. The capture table is created and
read by the owner and only written by `authenticated`, so no assertion depends
on a temp table the client owns; role and claims are reset immediately
afterwards, and all fixtures stay transaction-scoped. No service-role credential
was used and RLS was not bypassed.

One assertion exists purely to make this section honest: a sanitized rejection
looks identical whether it was raised for the owner or for a client, so
`current_user = 'authenticated'` is asserted inside the block. Without it a
silently failed role switch would leave the section proving nothing new.

### M2 — stale TASK-011 dependency statement in the task packet

The packet still said TASK-011 was awaiting Codex round-2 review and made this
task's helper conditional on that review's outcome. That contradicted both Git
history and the Round 2 handoff. The bullet now records the settled state:
TASK-011 was reviewed and merged before TASK-012 began, and its merged helper at
base SHA `69a1471` is the dependency used here and verified by every run in this
handoff. The conditional language is withdrawn rather than reworded. No approved
decision and no Round 1 record was altered.

### L2 — Round 2 commit body overstated its file count

Commit `9d6acd3` says "Local only: 5 files". It changed exactly **four**:

| Scope | Changed files |
| --- | --- |
| Round 2 fix commit `9d6acd3` | **4** |
| Complete TASK-012 diff against `69a1471` | **6** |

This is a documentation correction only. Commit `9d6acd3` was not amended,
rebased, or rewritten, and its message still reads "5 files"; this ledger entry
is the correction of record.

### Round 3 mutation evidence

Each mutation was applied to a local working copy of the migration, verified by
`git diff --numstat` to be exactly the intended edit, run after a full
`db reset`, then reverted with `git checkout --` and the database reset again.
The migration is byte-identical to its committed state afterwards.

| Mutation | Result |
| --- | --- |
| the `overall_feeling is null` and `pain_status is null` trigger guards removed (`0` insertions, `2` deletions) | **FAIL — 4 of 190**: tests 62, 63, 64, 67 |
| UPDATE policy widened to `using (true) with check (true)` | **FAIL — 3 of 190**: tests 119, 121, 154 |
| owner UPDATE policy denied while still containing `auth.uid()` — `using (athlete_profile_id = (select auth.uid()) and false)` | **FAIL — 3 of 190**: tests 82, 83, 84 |

The first mutation is the direct proof that M1 is closed: those four assertions
are exactly the new authenticated-client checks, and they were absent in Round
2. Test 67 failing shows the message a client would then receive matches one of
the forbidden patterns — a column name, a constraint name, a row
representation, an identifier, or a date — instead of the fixed sanitized
string.

One honest detail: under that mutation tests 65 and 66 (empty `DETAIL`, empty
`HINT`) still **passed**, so the observed leak was in the message text, not in a
failing-row `DETAIL`. I have not established why PostgreSQL withheld the
`DETAIL` from this particular role and am not asserting a mechanism here. The
guard is what keeps the contract sanitized either way, and the assertions that
failed are sufficient to prove the guard is load-bearing.

The second and third mutations are the two Round 2 H1 checks, re-run unchanged
against the Round 3 suite; their failing test numbers shifted only because nine
assertions were inserted earlier in the file.

### Round 3 verification

Every command below was run locally in this worktree. Credential-bearing streams
were suppressed; no status output, API URL, key, JWT secret, database URL, or
token was printed.

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 |
| `corepack pnpm exec supabase --version` | `2.109.1` |
| start local stack, output suppressed | exit 0 |
| `corepack pnpm exec supabase db reset --local --no-seed` | exit 0 |
| `corepack pnpm exec supabase test db --local` | **PASS — 5 files, 583 assertions** (`005` contributes 190) |
| same, trigger NULL guards removed | **FAIL — `005` fails 4/190** |
| same, UPDATE policy widened | **FAIL — `005` fails 3/190** |
| same, owner UPDATE policy denied | **FAIL — `005` fails 3/190** |
| after reverting every mutation and resetting | **PASS — 5 files, 583 assertions** |
| `supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, "No schema errors found" |
| `supabase gen types typescript --local --schema public`, BOM stripped, Prettier-formatted | `git diff --no-index` exit 0 — zero drift |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | exit 0 — 18 files, 327 tests passed |
| `git diff --check` | clean |
| stop local stack, output suppressed | exit 0, no Supabase container remains |

Two process notes, both mine and neither reaching the delivered code. My first
mutation run wrote the migration with `Set-Content -Encoding utf8`, which adds a
BOM in PowerShell 5.1; `db reset` exited 1 and that run's evidence was discarded
and redone with a byte-exact writer. My first Round 3 drift check compared raw
generator output against the committed file and reported a whole-file
difference; the committed file is Prettier-formatted after generation, which is
the procedure the packet records, and with that step the diff is empty.

## Round 4 — Codex finding and fix

All prior-round history above is retained. Round 4 changed three files and no
migration, schema, policy, privilege, or generated type:
`005_daily_check_ins_rls_test.sql`, the task packet, and this handoff.

### Medium — pgTAP could print a captured `MESSAGE_TEXT` on failure

Two assertions compared a captured error message directly:

```sql
select is(
  (select min(err_message) from rejection_probe),
  'daily check-in rejected: invalid input',
  'that message is the fixed generic one'
);
```

pgTAP prints the have/got value of a failing `is()`. So if a regression ever put
a UUID, a date, a row representation, a supplied value, or a health value into
`MESSAGE_TEXT`, the assertion whose entire purpose is to detect that disclosure
would copy the disclosed string into the test log. The test meant to catch the
leak was itself a leak path.

Both are now counted. The comparison happens inside the query and only a row
count crosses the boundary into pgTAP:

```sql
select is(
  (select count(*)::int from rejection_probe
    where err_message is distinct from 'daily check-in rejected: invalid input'),
  0,
  'no rejection message differs from the fixed generic one'
);
```

and, for the authenticated client matrix:

```sql
select is(
  (select count(*)::int from client_rejection_probe
    where err_message is distinct from 'daily check-in rejected: invalid input'),
  0,
  'no rejection message an authenticated client sees differs from the fixed generic one'
);
```

`is distinct from` is deliberate: a null `MESSAGE_TEXT` counts as differing
rather than evaluating to null and vanishing from the count.

The distinct-message, SQLSTATE, `DETAIL`, `HINT`, and forbidden-pattern
assertions are all preserved unchanged. The replacement is one-for-one, so the
plan stays at 190 — recalculated from the actual assertion tally, not assumed.

### Audit of the rest of the rejection section

`err_message`, `err_detail`, and `err_hint` are no longer returned to any
assertion anywhere in the file; every remaining check counts rows.

Two things were deliberately **not** changed:

1. **`is((select min(err_state) ...), '22023', ...)` returns a captured
   SQLSTATE.** This is a five-character code from a closed enumeration. It
   cannot carry a value, an identifier, a date, or a row, and its printed value
   on failure is diagnostically useful. Under mutation it printed `23502`, which
   is exactly the safe scalar this assertion is for.
2. **`throws_ok(..., '<code>', null, ...)`.** pgTAP's `throws_ok` prints the
   caught error — code *and* message — when the expected code does not match, so
   it is structurally the same channel as the finding. It is flagged below
   rather than rewritten, because changing it means replacing 27 assertions
   across sections unrelated to this finding, and the instruction was not to
   broadly rewrite unrelated tests. It did not fire in any mutation run: all
   diagnostics observed were bare integers.

### Round 4 mutation evidence

Full test output was captured to a file and scanned programmatically. The raw
output was never printed; only counts, booleans, and values proven to be bare
integers are reported. Each mutation was verified by `git diff --numstat` to be
exactly the intended edit, then reverted with `git checkout --` and the database
reset.

| Mutation | Result | Diagnostic value lines | Non-integer diagnostics | Leaked message/UUID/date/row |
| --- | --- | --- | --- | --- |
| trigger `overall_feeling`/`pain_status` NULL guards removed (`0` insertions, `2` deletions) | **FAIL — 4 of 190**: tests 62, 63, 64, 67 | 8 | **0** | **0** |
| UPDATE policy widened to `using (true) with check (true)` | **FAIL — 3 of 190**: tests 119, 121, 154 | 6 | **0** | **0** |
| owner UPDATE denied while retaining `auth.uid()` | **FAIL — 3 of 190**: tests 82, 83, 84 | 4 | **0** | **0** |

Every diagnostic under the guard-removal mutation was a bare integer, and they
are safe to reproduce in full:

```
#   have: 23502     #   want: 22023      (test 62, SQLSTATE)
#   have: 2         #   want: 1          (test 63, distinct message count)
#   have: 2         #   want: 0          (test 64, the new counted assertion)
#   have: 2         #   want: 0          (test 67, forbidden-pattern count)
```

The whole 50-line output was also scanned for `null value in column`,
`Failing row contains`, `violates not-null`, `violates check constraint`, the
synthetic UUID prefix, and any `2026-07-` date: **zero occurrences of each**.

### The same mutation against the Round 3 test file

To verify the finding rather than take it on trust, the Round 3 committed test
file was checked out and run against the identical mutation, with the Round 4
file set aside and restored immediately afterwards.

| Test file | Failing tests | Diagnostic value lines | Non-integer diagnostics | Diagnostic lines containing the native message |
| --- | --- | --- | --- | --- |
| Round 3 (`7eca322`) | 62-64, 67 | 8 | **2** | **1** — matched `null value in column`, `violates not-null`, and `overall_feeling` |
| Round 4 | 62-64, 67 | 8 | **0** | **0** |

The finding is confirmed exactly as written. The offending line was detected by
pattern match and its content was never printed to a terminal, a log, or this
handoff. Fixtures in that run were synthetic and the leaked string named a
column, not a measurement — but the assertion design, not the luck of which row
failed, is what the requirement governs.

### Round 4 verification

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 |
| `corepack pnpm exec supabase --version` | `2.109.1` |
| start local stack, output suppressed | exit 0 |
| `corepack pnpm exec supabase db reset --local --no-seed` | exit 0 |
| `corepack pnpm exec supabase test db --local` | **PASS — 5 files, 583 assertions** (`005` contributes 190) |
| guard-removal mutation | **FAIL — 4/190**, diagnostics all bare integers |
| UPDATE policy widened | **FAIL — 3/190**, diagnostics all bare integers |
| owner UPDATE denied | **FAIL — 3/190**, diagnostics all bare integers |
| after restoring every file and resetting | **PASS — 5 files, 583 assertions** |
| `supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, "No schema errors found" |
| type regeneration, BOM stripped, Prettier-formatted | `git diff --no-index` exit 0 — zero drift |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | exit 0 — 18 files, 327 tests passed |
| `git diff --check` | clean |
| stop local stack, output suppressed | exit 0, no Supabase container remains |
| final worktree | clean |

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

None outstanding. All four Round 1 findings (H1, M1, M2, M3), all four Round 2
findings (M1, M2, L1, L2), and the single Round 3 Medium are implemented,
tested, and verified above. No finding was deferred, partially applied, or
reinterpreted. The H1 and M2 implementations and their tests were preserved
unchanged and re-proved by mutation in every later round.

Four points are flagged for the reviewer's explicit attention:

1. **The reading of decision 8** recorded in the task packet and above: a coach
   is denied any write path into another person's check-in, but is not
   prohibited from owning their own, because decision 6 makes self-write
   identity-owned and independent of role. If the Product Owner intends the
   stricter reading, it is a one-line policy change plus test updates.
2. **The mechanical `7` → `9` update** to the TASK-008 pgTAP file, authorized in
   advance by this task's packet, following the precedent set by TASK-009 and
   TASK-011. The diff contains exactly four literals and one description and
   nothing else.
3. **`23505` and `23503` still return native PostgreSQL errors.** M1 sanitized
   the required-field, range, and status paths exactly as specified. A duplicate
   or foreign-key violation still carries a `DETAIL` that can name the athlete
   id and the calendar date — no health measurement, but it does reveal that a
   given athlete checked in on a given date. I did not narrow those two
   unilaterally, because doing so changes the error a client sees for a
   legitimate duplicate-submission case and that is a product decision.
4. **`throws_ok` prints the caught error message on a code mismatch** (raised in
   Round 4). This is the same failure-output channel the Round 3 Medium
   identified, but it reaches 27 assertions across sections that finding did not
   cover, and the instruction was explicitly not to broadly rewrite unrelated
   tests. It did not fire under any mutation run here. If the Product Owner
   wants the guarantee to be structural rather than situational, the fix is to
   route those assertions through the same `pg_temp` probe used by the rejection
   matrices and assert counted SQLSTATEs — a mechanical but wide change, and one
   I did not make unilaterally.

## Confirmation

Nothing was pushed, merged, deployed, linked to a hosted project, remotely
migrated, or applied to hosted Supabase. No `db push`, no `--linked`, no remote
database URL, no project ref, and no service-role credential was used at any
point. No production data was accessed and no protected legacy path was read.

The branch `feat/TASK-012-daily-check-in-rls` is local and was not merged into
`feat/mobile-foundation`. The worktree still exists and is clean, and was not
cleaned up. The local Supabase stack is stopped with no container remaining.

Stopping here for GPT/Codex read-only review.
