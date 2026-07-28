# TASK-011: Consent and Sharing Grants RLS Foundation

Status: Implemented, awaiting Codex read-only review

Writer: Claude Code (sole writer)

Reviewer: ChatGPT/Codex (read-only)

No AGY reviewer is assigned to this task. AGY must not be used.

Product Owner: the human repository owner. Scope and decisions 1–10 below were
approved before implementation started.

## Goal and user value

Create the minimum consent and sharing authorization boundary required **before**
any check-in, workout, sleep, or other protected health data is added to the
product.

TASK-008 established identity, teams, and membership, and deliberately recorded
that "active membership alone must never be described as sufficient for future
health access". This task supplies the missing half: an explicit, athlete-owned,
per-team, per-category consent record, and a single authorization helper that
future health tables must consult.

The user value is direct for the athlete: sharing is something they turn on and
turn off, the revocation takes effect on the coach's next query, and the record
of what they consented to is retained for them and not visible to the coach.

## Base and ownership

- Source branch: `feat/mobile-foundation`
- Required base SHA: `642c3b4faaac5acbb4a63d4fc8caedaf6f35377b`
- Task branch: `feat/TASK-011-consent-sharing-grants-rls`
- Isolated worktree; all work happens there.
- Claude Code is the only writer. The reviewer does not edit implementation
  files.
- No merge, push, deploy, hosted link, remote migration, `db push`, or any
  production operation is part of this task.

## In scope

- One new timestamped migration under `platform/supabase/migrations/` creating
  `public.sharing_grants`, its constraints and indexes, its Row Level Security,
  two narrowly scoped public RPCs, one private authorization helper, and two
  narrowly scoped triggers.
- One new additive pgTAP test file under
  `platform/supabase/tests/database/`.
- One additional deterministic concurrency regression file under
  `platform/supabase/tests/database/`, authorized by the Product Owner for the
  Codex round-1 High finding.
- Regenerated TypeScript database types from the **local** stack only.
- The handoff at `docs/app/handoffs/TASK-011.md`.

## Out of scope / forbidden

- Editing any existing migration file, including the TASK-008 and TASK-009
  migrations.
- Mobile sharing screens or any UI.
- RPE, feeling, pain/injury values.
- Actual check-in rows, workout data, sleep data.
- HealthKit or Health Connect.
- Training plans, coach dashboard.
- Invitations or membership administration.
- Notifications.
- Export, deletion, or privacy-request flows.
- Monitoring flags.
- Garmin integration or any protected legacy data.
- Root `supabase/`.
- Hosted Supabase, remote migrations, `db push`, production data.
- Service-role or secret keys.
- `platform/package.json`, `platform/apps/mobile/package.json`, or
  `platform/pnpm-lock.yaml` changes, unless an unexpected verified requirement
  is reported to the Product Owner and approved first.

## Owned paths

- `docs/app/tasks/TASK-011-consent-sharing-grants-rls.md`
- `docs/app/handoffs/TASK-011.md`
- `platform/supabase/migrations/20260728120000_consent_sharing_grants_rls.sql`
  (the one new TASK-011 migration)
- `platform/supabase/tests/database/003_consent_sharing_grants_rls_test.sql`
  (the main TASK-011 pgTAP test)
- `platform/supabase/tests/database/004_consent_sharing_grants_concurrency_test.sql`
  (the deterministic concurrency regression test for the Codex round-1 High
  finding, authorized by the Product Owner)
- `platform/apps/mobile/src/lib/supabase/database.types.ts`
- `platform/supabase/tests/database/001_identity_teams_membership_rls_test.sql`,
  **four literal counts only** — see "Verified requirement found during
  implementation" below.

No additional application documentation is named by this packet, so none may be
added during implementation.

## Codex round-1 High finding and fix

Status: fixed and proved by a passing regression test.

### The finding

`public.grant_team_data_sharing` originally established the caller's active
athlete membership with an **unlocked** `EXISTS`, and inserted the grant row
afterwards. That is a time-of-check-to-time-of-use race. Codex reproduced it
deterministically against local Supabase with synthetic fixtures and two
database connections:

1. the grant RPC passed its active-membership check and was paused before the
   `INSERT`;
2. a second connection revoked the athlete membership;
3. the membership trigger ran while **no grant row existed**, so it had nothing
   to revoke;
4. the grant RPC then inserted an active grant;
5. final committed state was `membership status = revoked` with
   `active grants = 1`;
6. after reactivation, `private.can_current_user_read_shared_data(...)` returned
   **true with no new consent action**.

This violates approved decision 7 and the acceptance criterion that reactivation
must never revive an old grant. It is a real authorization defect, not a
theoretical one.

### The fix

Only the unmerged TASK-011 migration was edited. The `EXISTS` check is replaced
by a locking read of the caller's exact membership row, taken **before** any
grant lookup or insert:

```sql
select m.id into v_membership_id
from public.team_memberships as m
where m.team_id = p_team_id
  and m.profile_id = v_actor
  and m.status = 'active'
  and m.role = 'athlete'
for update;

if v_membership_id is null then
  raise exception 'active athlete membership required' using errcode = '42501';
end if;
```

The lock targets the exact `team_id` + `auth.uid()` membership, requires
`status = 'active'` and `role = 'athlete'`, conflicts with any membership
status or role update, and is held until the grant transaction ends.

Both committed orderings are now safe:

- **Grant locks first.** A concurrent revocation blocks until the grant
  transaction ends. Its trigger then runs against a snapshot in which the new
  grant is committed and visible, so the grant is revoked.
- **Revocation locks first.** The locking read blocks; on release, `READ
  COMMITTED` re-evaluates the predicate against the updated row, which no longer
  satisfies `status = 'active' and role = 'athlete'`. No row is returned and the
  call fails with the unchanged sanitized `42501`.

There is therefore no committed ordering that leaves a revoked membership
holding an active grant, and reactivation still requires an explicit new grant.

Lock order is membership row, then `sharing_grants`, in both the RPC and the
membership trigger, so the two paths cannot deadlock.

Everything else is preserved unchanged: idempotent duplicate grant, category
validation, `auth.uid()`-owned identity, database-controlled timestamps, revoke
behaviour, RLS, and the minimum privilege model.

### The regression test

`platform/supabase/tests/database/004_consent_sharing_grants_concurrency_test.sql`
— 23 assertions, added under the Product Owner's authorization for one
additional test-only file.

A separate file is required because it cannot be transaction-scoped. Proving a
race needs a second genuinely independent session, and a second session cannot
see fixtures held in an uncommitted transaction. The file therefore commits
synthetic fixtures, drives two independent sessions through `dblink`, and
removes everything again; the cleanup is idempotent and also runs first, so an
interrupted run cannot poison a later one. Three assertions verify that it left
no grant row, no membership row, and no probe role behind, and a fourth verifies
the test-only `dblink` extension was removed.

No sleep, pause, test hook, extension, or debug object was added to the
migration. No dependency was added. The synthetic probe role's password is
generated by and for the test and the role is dropped before the file finishes.

It asserts both orderings, and in each: that the second session provably
**blocks** (`dblink_is_busy = 1`), that the committed state has zero active
grants, that reactivation produces no active grant, that the authorization
helper stays false after reactivation, and that only an explicit new grant makes
it true again.

### Mutation evidence

With the row lock removed and the unlocked `EXISTS` restored, the local suite
was re-run:

- `001`, `002`, and `003` all still **pass** — a sequential test cannot observe
  this race, which is exactly why the concurrency file was necessary;
- `004` **fails 11 of 23 assertions**, including the RPC not blocking,
  `scenario A commits with zero active grants` reporting 1, and
  `the authorization helper stays false after reactivation` reporting true.

That last failure is the finding itself: coach access restored with no consent.
The lock was then restored and the full suite passes again.

## Verified requirement found during implementation

The Product Owner has **explicitly approved** this deviation. It is no longer
merely flagged for attention.

The approval is limited to exactly: four literal private-function counts changed
from `4` to `7`, and one assertion description updated. No assertion is removed,
weakened, or otherwise changed, and no other line of that file may be edited.

This packet originally listed the TASK-008 pgTAP file as forbidden. That turned
out to be incompatible with acceptance criterion 31 ("all existing TASK-008 and
TASK-009 pgTAP tests remain passing").

`001_identity_teams_membership_rls_test.sql` asserts four **global** catalog
counts over `pg_proc` in the `private` schema — that exactly 4 functions exist
there, and that all 4 are `SECURITY DEFINER` with a pinned, empty `search_path`.
TASK-011 necessarily adds three private functions (the authorization helper and
two trigger functions), so those four assertions become arithmetically false the
moment the migration is applied. There is no way to add a
`private.can_current_user_read_shared_data` helper — which this task explicitly
requires — and leave the counts at 4.

The correction applied is the minimum possible: **four literals changed from `4`
to `7`**, plus one assertion description reworded to say which task contributes
which functions. No assertion is removed, weakened, or re-scoped; the three
security properties still apply globally to every function in `private`, now
covering 7 instead of 4. No other line of that file, and no line of
`002_profile_display_name_self_update_test.sql`, is touched.

There is precedent: TASK-009 similarly updated TASK-008's pgTAP file where one
of its assertions had become intentionally obsolete.

The Product Owner reviewed this deviation and approved it explicitly, with the
scope limited exactly as stated above.

## Forbidden paths

- `platform/supabase/migrations/20260727120000_identity_teams_membership_rls.sql`
- `platform/supabase/migrations/20260727130000_profile_display_name_self_update.sql`
- `platform/supabase/tests/database/002_profile_display_name_self_update_test.sql`
- every part of `001_identity_teams_membership_rls_test.sql` other than the four
  literal counts described above
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
- `docs/app/architecture/ADR-0001-platform-boundary.md`
- `docs/app/tasks/TASK-007-supabase-local-foundation.md`
- `docs/app/tasks/TASK-008-identity-teams-membership-rls.md`
- `docs/app/tasks/TASK-009-authentication-profile-onboarding.md`
- `docs/app/tasks/TASK-010-secure-session-storage.md`

## Approved product and security decisions

1. **Sharing is granted per team, not per individual coach.** An athlete
   consents to a team; every active coach of that team is covered, and a coach
   who joins later is covered without a new consent action.
2. **Supported categories are exactly three:** `check_in`, `workout_summary`,
   `sleep_summary`. A database check constraint is the authority.
3. **Consent history is retained.** Revocation stamps `revoked_at`; a later
   re-grant creates a new row. Nothing is deleted or overwritten.
4. **There is no status column.** An active grant is exactly
   `revoked_at is null`. No second source of truth for activeness may exist.
5. **Authenticated clients cannot write the table directly.** Grant and revoke
   go through narrowly scoped RPCs. `authenticated` holds no `INSERT`,
   `UPDATE`, `DELETE`, or `TRUNCATE` privilege and no write policy exists.
6. **The athlete identity comes only from `auth.uid()`,** and the timestamps
   come only from the database. No client input supplies either.
7. **Revoking or changing an active athlete membership must revoke that
   membership's active grants.** Reactivating the membership must not revive an
   old grant; the athlete must explicitly grant again.
8. **A coach sees only currently active grants for active athletes** in a team
   where the caller holds an active coach membership.
9. **A grant alone is never sufficient for protected-data access.** The
   authorization helper must additionally require an active athlete membership
   and an active coach membership in the same team.
10. **This task is database authorization foundation only:** local Supabase and
    synthetic fixtures, with no health values and no mobile sharing UI.

## Approved schema

### `public.sharing_grants`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | primary key, `default gen_random_uuid()` |
| `team_id` | `uuid` | not null |
| `athlete_profile_id` | `uuid` | not null |
| `data_category` | `text` | not null, constrained to the three approved values |
| `granted_at` | `timestamptz` | not null, `default now()`, database-generated and immutable |
| `revoked_at` | `timestamptz` | nullable, database-controlled; `null` means active |

Constraints and indexes:

- `sharing_grants_data_category_valid`
  — `data_category in ('check_in', 'workout_summary', 'sleep_summary')`.
- `sharing_grants_revoked_after_granted`
  — `revoked_at is null or revoked_at >= granted_at`.
- `sharing_grants_membership_fkey`
  — composite foreign key `(team_id, athlete_profile_id)` referencing
  `public.team_memberships (team_id, profile_id)` `on delete cascade`. This is
  the integrity tie required by the task: a grant cannot exist without the
  trusted membership row, and deleting the membership, the profile, the auth
  user, or the team cascades the grant away rather than leaving a usable
  orphan. `on update no action` is deliberate: re-keying a membership row while
  an active grant exists is refused with `23503` instead of silently moving
  someone's consent.
- `sharing_grants_one_active_idx`
  — partial unique index on `(team_id, athlete_profile_id, data_category)`
  `where revoked_at is null`. At most one active row per athlete, team, and
  category; historical revoked rows are unaffected and may accumulate.
- `sharing_grants_athlete_profile_id_idx`
  — supports the athlete's own-history read.
- `sharing_grants_team_active_idx`
  — partial index on `(team_id, athlete_profile_id, data_category)`
  `where revoked_at is null`, supporting coach-side and helper lookups.

No health value, measurement, note, or free-text field exists on this table. It
carries consent metadata only.

### Timestamp enforcement trigger

`private.enforce_sharing_grant_timestamps()`, a `SECURITY DEFINER` trigger
function with `search_path = ''`, fires `before insert or update` on
`public.sharing_grants` and:

- on insert, overwrites `granted_at` with `pg_catalog.now()` and forces
  `revoked_at` to `null`;
- on update, restores `id`, `team_id`, `athlete_profile_id`, `data_category`,
  and `granted_at` from the old row, so they are immutable after insert;
- on update, stamps `revoked_at` with `pg_catalog.now()` when an active row is
  being revoked, and refuses to change or clear an already-set `revoked_at`, so
  consent history is append-only and a revoked row can never be un-revoked.

This makes decision 6 a property of the database rather than of the calling
function, and it holds even for a future writer inside the trusted boundary.

### Membership-revocation trigger

`private.revoke_sharing_grants_on_membership_change()`, a `SECURITY DEFINER`
trigger function with `search_path = ''`, fires `after update` on
`public.team_memberships` for each row, with a `when` clause restricted to rows
that **were** an active athlete membership and **are no longer** an active
athlete membership. It stamps `revoked_at = pg_catalog.now()` on every still
active grant for that `(team_id, profile_id)`.

It never inserts, never clears `revoked_at`, and does not fire on reactivation,
so a reactivated membership starts with no active grant. No TASK-008 membership
policy, grant, constraint, or column semantic is changed.

## Approved write API

Two `SECURITY DEFINER` functions in `public`, each with `search_path = ''`.
They exist because `authenticated` holds no write privilege on the table; they
are the only client-reachable write path.

### `public.grant_team_data_sharing(p_team_id uuid, p_data_category text) returns uuid`

Returns the `id` of the caller's active grant row for that team and category —
the newly inserted row, or the already-active row when the call is a repeat.

- Raises `42501` when `auth.uid()` is null.
- Raises `22023` when `p_data_category` is not one of the three approved values.
- Raises `42501` unless the caller holds a membership in `p_team_id` with
  `status = 'active'` **and** `role = 'athlete'`. A coach-role membership
  therefore cannot grant athlete sharing. This check is a locking read
  (`select ... for update`) of that exact membership row, taken before any grant
  lookup or insert, so a concurrent revocation cannot slip between the check and
  the write — see "Codex round-1 High finding and fix".
- Never accepts an athlete identifier from the client; the row is always written
  with `auth.uid()`.
- Idempotent: a repeat call returns the existing active row's id and inserts
  nothing. A concurrent duplicate that loses the partial unique index race is
  caught and resolved to the same result, so two active rows can never exist.
- Error messages are fixed strings that name no other athlete, team, or row.

### `public.revoke_team_data_sharing(p_team_id uuid, p_data_category text) returns uuid`

Returns the `id` of the row that was revoked, or `null` when the caller had no
active grant for that team and category.

- Raises `42501` when `auth.uid()` is null.
- Raises `22023` for an unsupported category.
- Updates only rows where `athlete_profile_id = auth.uid()` and
  `revoked_at is null`, so it can only ever revoke the caller's own consent.
- Deliberately performs **no** membership check, so an athlete whose membership
  has already been revoked can still revoke their own consent.
- A repeat revoke is safe: it matches nothing and returns `null`.
- Error messages are fixed strings that name no other athlete, team, or row.

### RPC privileges

- Default `PUBLIC` execution is revoked from both functions.
- `anon` execution is revoked explicitly, because Supabase default privileges
  grant `EXECUTE` on new `public` functions to `anon` and `authenticated`.
- `EXECUTE` is granted only to `authenticated`.

## Approved authorization helper

```text
private.can_current_user_read_shared_data(
  p_team_id uuid,
  p_athlete_profile_id uuid,
  p_data_category text
) returns boolean
```

`SECURITY DEFINER`, `stable`, `search_path = ''`, in the non-exposed `private`
schema, which remains absent from the exposed API schemas in `config.toml`.

Returns true only when **all three** hold:

- the caller holds an active **coach** membership in `p_team_id`;
- the target holds an active **athlete** membership in the same team;
- the target has a sharing grant for `p_data_category` in that team with
  `revoked_at is null`.

A grant alone, a membership alone, a role alone, or a grant for a different
category returns false. This is the single helper that every future protected
health table must consult; membership helpers from TASK-008 are identity
visibility only and remain insufficient.

Privileges: `PUBLIC` and `anon` execution revoked; `EXECUTE` granted only to
`authenticated`, which is the minimum required because an RLS policy expression
is evaluated as the calling role.

Being `SECURITY DEFINER`, its internal lookups are not subject to the policies
on `sharing_grants`, which is what keeps the coach policy non-recursive.

## Approved table privileges and RLS

- Row Level Security is enabled on `public.sharing_grants`.
- All default privileges are revoked from `anon` and `authenticated` first;
  `SELECT` only is granted back to `authenticated`.
- `anon` receives no table privilege and no RPC execution. An anonymous read
  therefore fails with `42501` at the privilege layer, before RLS is consulted.
- No `INSERT`, `UPDATE`, or `DELETE` privilege or policy exists for any client
  role.

Two `SELECT` policies, both `to authenticated`:

| Policy | `USING` | Effect |
| --- | --- | --- |
| `sharing_grants_select_own_history` | `athlete_profile_id = (select auth.uid())` | The athlete reads their own complete consent history, active and revoked. Another athlete matches nothing. |
| `sharing_grants_select_active_for_coach` | `revoked_at is null and private.can_current_user_read_shared_data(team_id, athlete_profile_id, data_category)` | An active coach reads only active grant rows of active athletes in a team they actively coach. Revoked history is invisible; a revoked coach and a cross-team coach see nothing. |

Because the coach path routes through the helper, coach visibility and future
health-data authorization cannot drift apart.

## Acceptance criteria

- [x] No health value is stored or introduced; the migration adds consent
      metadata only.
- [x] Every approved decision 1–10 is enforced by PostgreSQL, not by client
      code.
- [x] `public.sharing_grants` exists with the approved columns, category check
      constraint, composite membership foreign key, partial unique active index,
      and lookup indexes.
- [x] `granted_at` is database-generated and cannot be supplied or changed by a
      client; `revoked_at` is database-controlled and append-only.
- [x] Deleting the membership, profile, auth user, or team leaves no usable
      orphan grant.
- [x] `authenticated` holds `SELECT` only on `sharing_grants`; `anon` holds
      nothing; no write policy exists.
- [x] The two RPCs are the only client write path, take no athlete identifier,
      are executable only by `authenticated`, and behave exactly as specified
      above including idempotent grant and safe repeat revoke.
- [x] Revocation takes effect on the coach's next query.
- [x] Membership revocation stamps active grants as revoked, and reactivation
      never revives an old grant.
- [x] Consent history is retained and readable by the athlete owner only.
- [x] Coach visibility is active-only and team-isolated.
- [x] `private.can_current_user_read_shared_data` returns true only for
      grant plus both active memberships plus matching category.
- [x] No TASK-008 membership policy changes semantic behaviour, and no existing
      migration file is edited.
- [x] Generated types match the local database.
- [x] No committed interleaving of a grant call and a membership revocation
      leaves a revoked membership holding an active grant, proved by a
      two-connection regression test that fails if the row lock is removed.
- [x] The new pgTAP file passes, and TASK-008 and TASK-009 pgTAP files still
      pass unchanged.
- [x] Existing mobile format, lint, typecheck, and unit tests still pass.
- [x] No secret, real user, real athlete, Garmin data, or protected legacy data
      is introduced, and no dependency or lockfile changes.

## Negative-test matrix

Synthetic identities only: `athlete-a`, `athlete-b`, `coach-a`, `coach-b`,
`team-a`, `team-b`, plus a dual-role user and revoked variants.

| # | Case | Expected |
| --- | --- | --- |
| 1 | anon reads `sharing_grants` | denied, `42501` |
| 2 | anon executes either RPC | denied, `42501` |
| 3 | authenticated direct `INSERT` | denied, `42501` |
| 4 | authenticated direct `UPDATE` | denied, `42501` |
| 5 | authenticated direct `DELETE` | denied, `42501` |
| 6 | athlete reads own active and revoked history | both rows visible |
| 7 | athlete reads another athlete's grants | 0 rows |
| 8 | athlete grants for a team without active athlete membership | `42501` |
| 9 | active coach grants or revokes for an athlete | grant `42501`; revoke affects nothing and the athlete's grant stays active |
| 10 | coach-role member grants as an athlete in the coached team | `42501`, while the same user's athlete team succeeds |
| 11 | Team A coach reads Team B grants | 0 rows |
| 12 | Team A coach calls the helper for Team B | false |
| 13 | active coach reads an active grant of an active athlete in the same team | visible |
| 14 | coach reads revoked consent history | 0 rows |
| 15 | grant revoked, coach queries again | row disappears on the next query |
| 16 | revoked coach reads through coach access | 0 rows, helper false |
| 17 | athlete membership revoked, coach queries | 0 rows, helper false |
| 18 | membership revocation runs | active grants stamped `revoked_at` |
| 19 | membership reactivated | no grant revived; helper false |
| 20 | athlete grants again after revoke | a new history row; two rows total |
| 21 | duplicate grant call | one active row only; same id returned |
| 22 | repeat revoke | returns `null`, no error, history unchanged |
| 23 | invalid category through the RPC and through a trusted insert | `22023` and `23514` |
| 24 | client attempts to forge the athlete identity | no RPC parameter exists; a trusted insert for another athlete is not reachable by any client role |
| 25 | client attempts to forge `granted_at` or `revoked_at` | no RPC parameter exists; direct update denied `42501`; trigger overwrites a supplied value |
| 26 | helper with a grant but no coach membership | false |
| 27 | helper with both memberships but no grant | false |
| 28 | helper with the wrong category | false |
| 29 | helper with grant plus both active memberships | true |
| 30 | catalog: RLS enabled, policies, grants, table privileges, function privileges, constraints, indexes, triggers, `search_path` | asserted |
| 31 | existing TASK-008 and TASK-009 pgTAP files | still pass |
| 32 | grant concurrent with membership revocation, revocation locking first | grant blocks, then fails `42501`; zero grant rows |
| 33 | grant concurrent with membership revocation, grant locking first | revocation blocks, then its trigger revokes the new grant; zero active grants |
| 34 | reactivation after either race | zero active grants; helper false until an explicit new grant |

## Privacy classification

Consent metadata is PII but contains **no** health measurement. The table stores
a team id, a profile id, a category name, and two timestamps. It records that a
person consented to share a category with a team, and when — nothing about what
was shared.

All fixtures are synthetic, transaction-scoped, and rolled back, and use the
reserved `example.test` domain. No service-role key is used. Local Supabase
credentials are never printed or persisted: `supabase status` and `db:status`
are not run in this task, and `db:start`/`db:stop` output is fully redirected so
that only an exit code is reported.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm exec supabase --version
```

Start the local stack while suppressing credential output; report only the exit
code:

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

The deterministic concurrency regression test needs no separate command: it is
an ordinary pgTAP file and runs as part of `supabase test db --local`, fourth
and last. It manages its own committed fixtures and removes them, so the local
database is left exactly as `db reset` produced it.

Regenerate the types from the **local** stack and confirm no drift:

```powershell
corepack pnpm exec supabase gen types typescript --local --schema public `
  | Out-File -FilePath "apps\mobile\src\lib\supabase\database.types.ts" -Encoding utf8
```

Strip the PowerShell 5.1 BOM before committing, then re-run the generator into a
temporary file and diff it against the committed file to prove zero drift.

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
bare `supabase start`, `supabase stop`, or `supabase status` while a transcript
is capturing output, and never run any command with `--linked` or a remote
database URL.

## Known limitations (recorded before implementation)

- Sharing is per team by decision 1. An athlete cannot exclude one coach of a
  team they have consented to; leaving the team or revoking the category is the
  only control.
- There is no client-reachable path to create teams or memberships, so the
  athlete-facing grant flow can only be exercised against trusted fixtures until
  a future membership-administration task exists.
- No mobile UI is delivered, so the RPCs are unreachable from the app in this
  task.
- Grant history accumulates without a retention or compaction policy; a future
  privacy-request task must decide how it is exported and deleted.
- The composite foreign key uses `on update no action`, so a trusted re-keying
  of a membership row is refused while an active grant exists. This is the
  fail-safe direction, not silent consent migration.
- Local Analytics remains disabled from TASK-007, so Studio's Logs section is
  empty locally.

## Rollback

The task is additive and file-scoped. To roll back:

1. `git revert` the TASK-011 commits, or delete the new migration, the new
   pgTAP file, this packet, and `docs/app/handoffs/TASK-011.md`, and restore
   `platform/apps/mobile/src/lib/supabase/database.types.ts` from the base SHA.
2. Run `corepack pnpm exec supabase db reset --local --no-seed` to rebuild the
   local database without the migration.

Nothing was applied to a remote database, so no remote rollback exists or is
needed. No dependency, lockfile, or configuration file is touched.

## Required handoff

Sanitized, at `docs/app/handoffs/TASK-011.md`, containing: task and writer;
branch and worktree; base and final commit SHAs; changed files; implemented
schema and authorization behaviour; acceptance-criteria mapping; the
negative-test matrix with results; commands run and results; privacy and
security impact; known limitations; rollback; and explicit confirmation that
nothing was merged, pushed, deployed, linked, remotely migrated, or cleaned up.

Then stop for Codex read-only review. Do not merge and do not remove the
worktree.
