# TASK-016 — Coach Daily Check-in Review (Mobile)

Status: **Approved for implementation**
Writer: **Claude Code** (sole writer)
Reviewer: **GPT/Codex** (read-only)
Product Owner: **Wayu**
AGY: **not used for this task**

## Numbering note

This work was originally discussed as TASK-015. **TASK-015 is already occupied by
the completed Garmin Low-Latency Sync task** (`docs/app/tasks/TASK-015-garmin-low-latency-sync.md`,
handoff `docs/app/handoffs/TASK-015.md`, commit `716e004`). The approved app work is
therefore renumbered to **TASK-016** with **no scope change**. Nothing in TASK-015 is
re-opened, amended, or superseded by this packet.

## Checkpoint

| Item | Value |
| --- | --- |
| Source branch | `feat/mobile-foundation` |
| Approved base SHA | `4ac2bfef3fdf10cdeaa28e0f7134d2589a21d594` |
| Task branch | `feat/TASK-016-coach-daily-check-in-review-mobile` |
| Worktree | `.claude/worktrees/task-016-coach-daily-check-in-review-mobile` |
| Session procedure | `docs/app/CLAUDE-CODE-SETUP.md`, worktree canary denied before content |

The task branch is cut from the approved base only. The main checkout is never
edited. No merge, push, deploy, publish, hosted-Supabase link, remote migration,
branch deletion, or worktree removal is part of this task.

## Goal

Replace **only** the "ทีม" (Team) placeholder card on the existing guarded Coach
Team screen with the smallest possible read-only mobile slice that shows the
**latest Daily Check-in explicitly shared with the coach's team**.

The monitoring-flags ("ธงเฝ้าระวัง") and training-plan ("แผนซ้อม") placeholders stay
exactly as they are. **No route, no detail screen, and no tab is added.**

## Approved decisions

### 1. Placement

Use the existing `platform/apps/mobile/src/app/coach/index.tsx` screen. No new
route, no detail screen, no tab. The section is a component rendered in place of
the Team placeholder.

### 2. Authorization

The existing active-coach route gate (`canEnterRoleArea(gate, "coach")`) controls
**UX only**. PostgreSQL RLS is the security boundary:

- `team_memberships_select_own_or_coached`
- `teams_select_active_member`
- `profiles_select_self_or_coached`
- `sharing_grants_select_active_for_coach`
- `daily_check_ins_select_shared_for_coach` →
  `private.can_current_user_read_check_in(athlete_profile_id)` →
  `private.can_current_user_read_shared_data(team_id, athlete_profile_id, category)`

Client-side filtering is **never** treated as authorization. Every client filter in
this task is a statement of intent that is then re-validated against the response;
neither the filter nor the validation is the boundary.

### 3. Consent visibility

Show only athlete/team pairs where **all three** hold:

- an **active coach membership** for the verified caller in that team;
- an **active athlete membership** for that athlete in **that exact team**;
- an **active `sharing_grants` row** for **exactly** `data_category = "check_in"`.

Athletes who have not shared are **not** individually listed and are **never**
labelled as refusing consent. The absence of an athlete is not rendered as a
statement about that athlete.

### 4. Latest record

At most **one** latest check-in per shared athlete/team pair. **No history** is
loaded or displayed. If one athlete actively shares with two teams the caller
coaches, the athlete is rendered under **both exact teams**, each from its own
validated grant pair.

### 5. Displayed data

Displayed, and nothing else:

- team name;
- athlete display name;
- the athlete-recorded local `check_in_date`;
- RPE as **0–10**;
- overall feeling as **1–5**;
- fixed Thai pain-presence wording.

Rules:

- The recorded date is **never** called "today" (`วันนี้`) and is **never** converted
  through UTC. It is the athlete's own recorded civil date, rendered verbatim.
- **No** row `id`, `created_at`, `updated_at`, notes, diagnosis, interpretation, or
  any unused column is selected or displayed.
- Fixed **non-diagnostic** wording accompanies every reading.

### 6. Load contract

Four stages, fail-safe order, each fully validated before the next begins:

| Stage | Reads | Purpose |
| --- | --- | --- |
| a | `team_memberships` + embedded `teams(name)` | the verified caller's active coach memberships and team names |
| b | `sharing_grants` | active `check_in` grants visible to that coach, restricted to stage-a team ids |
| c | `profiles` + embedded `daily_check_ins` | the strictly required athlete profiles and their latest visible check-in |
| d | `sharing_grants` | **consent revalidation** — the same read as stage b, repeated after the health values have arrived |

**Stage d was added in Round 3** by approved scope deviation, to close the Medium
revoked-grant race. Stage b authorizes the health-bearing read but cannot speak
for the moment that read *finishes*. If consent is withdrawn in between — an
athlete pressing "stop sharing", or a membership revocation firing the TASK-011
trigger that revokes their grants — RLS immediately refuses the embedded rows,
and **a refused embed is indistinguishable from an empty one**. Without stage d
the athlete would render as `ยังไม่ได้เช็กอิน`, which states as fact that they had
not checked in when what actually happened is that they withdrew consent.

This is a **presentation** defect, not an access-control one: no unauthorized row
was ever returned at any point.

Rules:

- Explicit columns only. **Never `select("*")`.**
- The **validated grant pairs** — not roster visibility — associate a health row
  with a team.
- Athlete profile reads are **deduplicated**, then the result is **materialized
  under every exact active grant pair**.
- Stage c uses the `profiles → daily_check_ins` relationship with
  **referenced-table `order(check_in_date, ascending: false)`** and
  **referenced-table `limit(1)`**.
- A response carrying **more than one embedded latest row** is refused.
- Maximum scope is **100 active athlete/team sharing pairs**. Stage b requests
  `101` so overflow is *detectable*; `101` rows raise a sanitized capacity error.
  The list is **never silently truncated** and a partial list is **never** returned.
- Stage c is **not issued at all** when stage b yields no active grants.
- Stage d issues **the same query as stage b**, through the same function, against
  the same stage-a team ids, with the same filters, the same validation, and the
  same capacity rule. A revalidation that asked a weaker question than the
  authorization would be worse than none, because it would look like a check.
- Stage d is **not issued** when stage b yields no active grants: there was no
  health-bearing read to protect.
- The stage-d comparison is **one-directional**:
  - a pair present in stage b but **absent** in stage d fails the **entire** load —
    no athlete and no health value is rendered, not even for surviving pairs;
  - a pair **newly present** in stage d is **ignored**. Stage c never read for it,
    so attaching it would mean rendering a row assembled from a read that did not
    cover it. It is picked up by the next deliberate query.

### 7. Fail-closed states

- A load error is **never** an empty result.
- Any of the following fails the **whole** load: a malformed membership, team,
  grant, profile, display name, or date; a malformed health value; a duplicate; an
  unknown category; a grant/team mismatch; a missing expected profile; an excess
  embedded row; an incomplete response.
- A partially valid team list is **never** rendered.
- The **only** "ยังไม่ได้เช็กอิน" (not submitted yet) state is: an active grant, a
  valid athlete, and no check-in row.

### 8. Freshness, revocation, and cache

One new auth-scoped key: `authScopedKeys.coachCheckInReview(userId)` →
`["auth-scoped", <verified coach user id>, "coach-check-in-review"]`. It contains
the verified coach user id and **no health value**, no team id, and no athlete id.

Query behaviour is overridden to:

| Option | Value | Reason |
| --- | --- | --- |
| `staleTime` | `0` | every mount re-reads consent |
| `gcTime` | `0` | leaving the screen makes the inactive health query immediately collectible |
| `retry` | `0` | a refused health read is never silently resent |
| `networkMode` | `"always"` | never paused, never deferred, never an outbox |
| `refetchOnMount` | `"always"` | returning to the screen re-checks revocation |
| polling | none | no `refetchInterval` |
| Realtime | none | no subscription |
| placeholder / previous data | none | no `placeholderData`, no `initialData`, no `keepPreviousData` |

Additionally:

- A **deliberate refresh action** is provided.
- **All health values are hidden while a refresh is in flight.**
- **A failed refresh hides the previously loaded health values** and shows a
  sanitized retry state.
- Signing out or switching identity removes the old account's query
  (`clearAuthScopedQueries`) **and** remounts the hook-owning subtree under an
  identity-derived React key, so the old observer is destroyed rather than reused.
- Revocation is reflected on the **next successful query**.

**Honest limitation, recorded deliberately:** screen data that has *already been
delivered to the device* cannot be remotely recalled without Realtime. A revocation
that happens while the coach is looking at a rendered card takes effect on the next
successful query, not instantly. This is accepted for this task; Realtime is out of
scope.

### 9. Privacy

- The identity comes **only** from `useAuth()` (verified against the JWT `sub`).
  Never from a prop, a route parameter, or a client-side session lookup.
- A **dual-role** user must not receive their own self-readable check-in through
  the coach list unless an exact valid coach/team/grant relationship exists.
  Because `team_memberships` is unique on `(team_id, profile_id)`, a caller cannot
  hold both a coach and an athlete membership in the same team, so a self-targeted
  grant among coached teams is **impossible** and is treated as a **closed
  failure**.
- Never displayed or logged: raw UUIDs, SQLSTATE, table names, RPC names, raw
  Supabase messages, `details`, `hint`, `cause`, or payloads.
- **No health value is ever logged or persisted.**
- No analytics, crash context, session replay, notifications, AsyncStorage,
  SecureStore, filesystem persistence, snapshots, or background work.
- Fixed sanitized Thai copy only.

### 10. Read-only mobile task

- No coach mutation and no RPC write path of any kind.
- No database, generated-type, dependency, lockfile, design-system, or shared-theme
  change.
- Local Supabase and synthetic fixtures only.

## Schema contracts consumed (read-only)

From `platform/apps/mobile/src/lib/supabase/database.types.ts` (not modified):

| Table | Columns read | Columns deliberately not read |
| --- | --- | --- |
| `team_memberships` | `team_id`, `role`, `status`, `teams(name)` | `id`, `profile_id`, `created_at`, `revoked_at` |
| `teams` | `name` (embedded) | `id`, `created_at` |
| `sharing_grants` | `team_id`, `athlete_profile_id`, `data_category` | `id`, `granted_at`, `revoked_at` (filtered, not selected) |
| `profiles` | `id`, `display_name` | `created_at` |
| `daily_check_ins` | `check_in_date`, `rpe`, `overall_feeling`, `pain_status` | `id`, `athlete_profile_id`, `created_at`, `updated_at` |

`profiles.id` is read because it is the join key for materializing grant pairs. It
is **never rendered**.

Relationship used: `daily_check_ins_athlete_profile_id_fkey`
(`daily_check_ins.athlete_profile_id → profiles.id`).

## Owned implementation paths

- `platform/apps/mobile/src/app/coach/index.tsx`
- `platform/apps/mobile/src/features/coach-check-in/**`
- `platform/apps/mobile/src/lib/query/keys.ts`
- `platform/apps/mobile/src/lib/query/keys.test.ts`
- `docs/app/tasks/TASK-016-coach-daily-check-in-review-mobile.md`
- `docs/app/handoffs/TASK-016.md`

## Read-only dependencies (may be imported, never modified)

- `platform/apps/mobile/src/features/check-in/domain.ts`
- `platform/apps/mobile/src/features/check-in/local-date.ts`
- existing auth, query-client, Supabase-client, component, and theme modules
- existing generated database types

## Forbidden changes

- Any `platform/supabase` migration, policy, grant, function, view, pgTAP file,
  config, or seed
- `platform/apps/mobile/src/lib/supabase/database.types.ts`
- Existing auth, athlete check-in, sharing, profile, component, theme,
  test-support, or navigation files outside the owned list
- `package.json`, `pnpm-lock.yaml`, dependency versions, Expo versions, tooling
  configuration
- Protected legacy paths: `athletes/`, `team_data/`, `garmin/`, `scripts/`, root
  `supabase/`, `CLAUDE.md`, `.agents/AGENTS.md`, `.claude/settings.json`,
  `.claude/settings.local.json`
- Real athlete data and production credentials

## Query contract

```text
stage a  team_memberships
         .select("team_id, role, status, teams(name)")
         .eq("profile_id", <verified caller>)
         .eq("role", "coach")
         .eq("status", "active")

stage b  sharing_grants                                  -- skipped when stage a is empty
         .select("team_id, athlete_profile_id, data_category")
         .eq("data_category", "check_in")
         .is("revoked_at", null)
         .in("team_id", <stage-a team ids>)
         .limit(101)                                      -- 100 + 1 overflow probe

stage c  profiles                                         -- skipped when stage b is empty
         .select("id, display_name, daily_check_ins(check_in_date, rpe, overall_feeling, pain_status)")
         .in("id", <deduplicated athlete ids>)
         .order("check_in_date", { referencedTable: "daily_check_ins", ascending: false })
         .limit(1, { referencedTable: "daily_check_ins" })

stage d  sharing_grants                                  -- skipped when stage b is empty
         -- byte-for-byte the stage-b query, issued through the same function
         .select("team_id, athlete_profile_id, data_category")
         .eq("data_category", "check_in")
         .is("revoked_at", null)
         .in("team_id", <stage-a team ids>)
         .limit(101)
```

Post-response validation, all fail-closed:

1. every membership row has a non-empty `team_id`, `role === "coach"`,
   `status === "active"`, and exactly one visible embedded team name;
2. no duplicate team id in stage a;
3. every grant row has a non-empty `team_id` and `athlete_profile_id` and
   `data_category === "check_in"` exactly;
4. every grant's `team_id` is one of the stage-a team ids;
5. no duplicate `(team_id, athlete_profile_id)` grant pair;
6. no grant whose `athlete_profile_id` equals the verified caller;
7. `101` grant rows → capacity failure;
8. the returned profile id set equals the requested id set exactly — no missing,
   no extra, no duplicate;
9. `display_name` is a non-empty string;
10. the embedded `daily_check_ins` array has length `0` or `1` — `≥ 2` is refused;
11. a present check-in passes `isLocalDateString(check_in_date)` and
    `parseCheckInRow` (RPE 0–10 integer, feeling 1–5 integer, pain status in
    `{none, present}`);
12. rules 3 through 7 apply again, unchanged, to the stage-d response;
13. every stage-b pair is still present in the validated stage-d pairs.

Stable order: team name, then team id, then athlete display name, then athlete id.

## UI states

| State | Rendering |
| --- | --- |
| initial loading | fixed loading line, no health value |
| refreshing | **previously displayed health values hidden**, fixed refreshing line |
| genuine no active coach team | fixed empty-team wording |
| team exists, nobody actively shares `check_in` | fixed no-consent wording, no athlete named |
| active sharing, no check-in yet | "ยังไม่ได้เช็กอิน" for that pair only |
| latest check-in | team, athlete, recorded date, RPE 0–10, feeling 1–5, fixed pain wording, fixed non-diagnostic note |
| load/refetch failure | sanitized notice + deliberate retry, **health values hidden** |
| capacity failure | sanitized capacity notice + retry, no partial list |
| multiple teams and athletes | stable documented order |

## Acceptance criteria

1. The Team placeholder is replaced; the monitoring-flags and training-plan
   placeholders are byte-for-byte unchanged.
2. No route, detail screen, or tab is added.
3. Only the six fields in decision 5 are selected and displayed.
4. No `select("*")` anywhere in the feature.
5. Stage c is not issued when there are no active grants, and neither is stage d.
6. Overflow above 100 pairs fails with a sanitized capacity error and never
   truncates.
7. Every fail-closed condition in decision 7 rejects the entire load.
8. The query key is auth-scoped and health-free.
9. The eight cache overrides in decision 8 hold, verified against a real
   `QueryClient`/`QueryObserver`.
10. Health values are hidden during refresh and after a failed refresh.
11. Nothing in the feature logs, persists, or writes.
12. Every failure message is one of a fixed sanitized Thai set.
13. All verification commands pass.
14. Mutation evidence is recorded for the four required safeguards, plus the
    Round 3 stage-d revalidation.
15. A grant or membership revoked between stage b and stage c fails the entire
    load; a grant newly activated in that window is not attached to the current
    result.

## Negative matrix

| # | Case | Expected |
| --- | --- | --- |
| 1 | signed-out route access | denied by gate; query disabled |
| 2 | pending membership | denied by gate |
| 3 | revoked membership | denied by gate |
| 4 | athlete-only user | denied by gate; RLS returns nothing |
| 5 | Team A coach requests Team B data | grant/team mismatch → whole load fails |
| 6 | coach membership without any grant | no-consent empty state, no athlete named |
| 7 | wrong sharing category | category mismatch → whole load fails |
| 8 | revoked grant | excluded by `revoked_at is null`; pair disappears |
| 9 | revoked coach membership | stage a empty → no-team state; RLS refuses regardless |
| 10 | revoked athlete membership | RLS helper false → no grant, no health row |
| 11 | active grant, no check-in | the only "not submitted yet" state |
| 12 | athlete shares with two coached teams | rendered under both exact teams |
| 13 | dual-role self-row | self-targeted grant among coached teams → closed failure |
| 14 | forged/mismatched team↔athlete relation | whole load fails |
| 15 | malformed / missing team | whole load fails |
| 16 | malformed / missing profile | whole load fails |
| 17 | malformed / missing grant | whole load fails |
| 18 | malformed / missing check-in value | whole load fails |
| 19 | duplicate grant pair | whole load fails |
| 20 | duplicate embedded check-in row | whole load fails |
| 21 | failure at stage a | sanitized load error, not an empty list |
| 22 | failure at stage b | sanitized load error, not an empty list |
| 23 | failure at stage c | sanitized load error, not an empty list |
| 24 | more than 100 pairs | sanitized capacity error, no partial list |
| 24a | grant revoked between stage b and stage c | stage d misses the pair → whole load fails, nothing rendered |
| 24b | membership revoked in that window (trigger revokes the grant) | same — whole load fails |
| 24c | consent moved to another coached team in that window | pair changed, not merely added → whole load fails |
| 24d | one of two grants revoked in that window | the surviving athlete is **not** rendered either |
| 24e | grant newly activated in that window | ignored this load, no error, picked up next query |
| 24f | stage d refused / rejected / malformed / over capacity | sanitized failure, capacity keeps its own wording |
| 25 | account change during an in-flight query | old observer destroyed; new identity starts idle |
| 26 | refresh failure with old health data internally present | health values hidden |
| 27 | resolved `{ error }` | sanitized |
| 28 | synchronous throw | sanitized |
| 29 | rejected builder | sanitized |
| 30 | rejected thenable | sanitized |
| 31 | insert/update/delete/upsert/RPC | none exists — AST-enforced |
| 32 | logs, persistence, health-bearing key, raw error exposure | none — AST + runtime enforced |

## Failure-output safety rules

Test failures must **never** print:

- a health-bearing row or object;
- a mock-call payload;
- a raw database error;
- a date or identifier paired with a health value;
- a snapshot.

Every assertion is reduced **before** `expect` to a boolean, a count, a fixed
field-name list, a fixed rule name, or another non-health scalar. Identifiers are
mapped to fixed labels (`owner-a`, `team-a`, `athlete-a`) where they must appear at
all. A local `failure-probe.ts` reduces a caught rejection to a fixed vocabulary and
never rethrows, returns, or stringifies the caught value.

Handoff and verification output may report only safe counts, assertion names, exit
codes, and fixed summaries.

## Mutation evidence required

Temporarily weaken each safeguard, confirm a test fails, then restore:

1. exact `check_in` category filtering;
2. grant-to-team association validation;
3. latest-row referenced-table order/limit;
4. account-scoped cache isolation / hiding stale data during refresh;
5. the stage-d consent revalidation (Round 3): removing the check, making it
   bidirectional, and reusing the stage-b result instead of re-reading.

Every mutation is reverted before final verification. **No mutated code is
committed.** Only safe scalar results are recorded.

## Verification

From `platform/`:

```text
corepack pnpm install --frozen-lockfile
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm --filter @run-performance/mobile exec vitest run src/features/coach-check-in src/lib/query
corepack pnpm dlx expo-doctor@latest
Android Expo export
Web Expo export
git diff --check
```

Local database authorization suite (run even though no database file changes):

```text
db:start                 (every credential-bearing stream suppressed)
db reset --no-seed       (local only)
full local pgTAP suite
db lint  public + private, warnings fail the run
db:stop
```

Never run or print `supabase status` / `db:status`. Never use `--linked` or a remote
database URL. Report only sanitized exit codes, test-file/assertion counts, and a
count of remaining Supabase containers.

## Known limitations

1. Already-delivered screen data cannot be remotely recalled without Realtime.
   Stage d narrows this window — it now ends when the revalidation returns rather
   than when the health read does — but it cannot close it. A revocation landing
   after stage d is reflected on the next successful query.
2. An athlete with a null or blank `display_name` fails the whole load rather than
   rendering, because a raw UUID must never be displayed as a name.
3. Capacity is capped at 100 active pairs; beyond that the screen fails closed
   rather than paginating. The wording differs from a generic failure and points at
   escalation, but the deliberate retry control is still offered.
4. A revocation landing between stage b and stage c now fails the whole load as one
   retryable error, rather than rendering the athlete as "not submitted yet". A
   coach whose athletes revoke frequently therefore sees a retry instead of a
   silently wrong list — the deliberate trade, since the previous behaviour stated
   something false about a person's health record.
5. Stage d costs one extra `sharing_grants` read per load. Accepted: it is a small,
   indexed, non-health read, and it is skipped entirely when nobody shares.
6. Known pre-existing Expo/Expo Router patch drift is **out of scope**; it is
   reported if Expo Doctor still finds it, and no dependency is changed.

## Rollback

The whole task is additive on a dedicated branch. To roll back:

```text
git switch feat/mobile-foundation
git branch -D feat/TASK-016-coach-daily-check-in-review-mobile
```

`feat/mobile-foundation` is untouched at `4ac2bfe`. No migration ran, no remote
state changed, and no dependency moved, so nothing outside the branch needs
reverting.

## Handoff requirements

`docs/app/handoffs/TASK-016.md` records: commit SHAs, changed files, acceptance
status, safe verification counts, mutation evidence, privacy/security impact,
known limitations, and rollback — then stops for GPT/Codex read-only review. No
merge and no worktree cleanup.
