# TASK-016 handoff — Coach Daily Check-in Review (Mobile)

Status: **Implementation complete. All verification complete, including the local
database authorization suite.** Stopped for GPT/Codex read-only review. Not
merged. Worktree not removed.

Round 1 recorded the database suite as **blocked** — the Docker daemon was
unreachable in that session. **Round 2 was verification and documentation only:**
the suite has now been run in full and passed, and the corrections below bring
this document into line with the actual Git state and the actual implementation.
No implementation code, test, or migration was changed in Round 2.

Writer: **Claude Code** (sole writer)
Reviewer: **GPT/Codex** (read-only)
Product Owner: **Wayu**
AGY: **not used**

## Numbering

TASK-015 belongs to **Garmin Low-Latency Sync** (packet
`docs/app/tasks/TASK-015-garmin-low-latency-sync.md`, handoff
`docs/app/handoffs/TASK-015.md`, commit `716e004`). The approved app work is
**TASK-016**, renumbered with **no scope change**. Nothing in TASK-015 was
re-opened or amended.

## Checkpoint as verified at session start

| Check | Result |
| --- | --- |
| Session ran the isolated app-worktree procedure | **pass** — worktree canary denied **before any content** |
| `.claude/rules/app-engineering.md` loaded, root coaching `CLAUDE.md` not loaded | **pass** |
| Approved base is the `feat/mobile-foundation` tip | **pass** — `4ac2bfef3fdf10cdeaa28e0f7134d2589a21d594` |
| Worktree path | **pass** — `.claude/worktrees/task-016-coach-daily-check-in-review-mobile` |
| Task branch did not already exist | **pass** |
| Task worktree clean before editing | **pass** |
| Main checkout clean before editing | **pass for tracked files**; one untracked entry, `?? .claude/worktrees/`, which is the worktree container the launch procedure itself creates. No tracked file in the main checkout was modified, and the main checkout was never edited. |

**One deviation, reported rather than improvised around.** The worktree was
created on the auto-generated branch `worktree-task-016-coach-daily-check-in-review-mobile`
rather than the required `feat/TASK-016-coach-daily-check-in-review-mobile`. The
required branch was created **at the approved base SHA** with `git switch -c
feat/TASK-016-coach-daily-check-in-review-mobile 4ac2bfe` before any file was
edited. The auto-generated branch still exists, untouched, at the same SHA; it
was not deleted. No history was rewritten to achieve this.

## Commits

| # | SHA | Round | Subject |
| --- | --- | --- | --- |
| 1 | `a6229ff` | 1 | `docs(task-016): add the coach daily check-in review packet` |
| 2 | `c31dbdb` | 1 | `feat(coach): show the latest check-in shared with a coached team` |
| 3 | `fadf512` | 1 | `docs(task-016): record the implementation handoff` |
| 4 | *this commit* | 2 | `docs(task-016): close out verification and correct the handoff` |

All four are on `feat/TASK-016-coach-daily-check-in-review-mobile`, cut from
`4ac2bfe`. **No existing commit was amended or rewritten.** Commit 4 is the only
Round 2 change and touches this file alone; its SHA cannot be printed inside
itself, so it is identified by position here and resolvable with
`git log --oneline 4ac2bfe..HEAD`.

Exactly **one** commit (`c31dbdb`) contains implementation. The other three are
documentation.

One correction to disclose: the packet commit was first created with a shell
here-string that the Bash tool mangled into the literal subject `@`. It was
immediately re-created with `git reset --soft HEAD~1` plus a fresh commit,
before any other work. That touched only the commit this session had just
created seconds earlier; no pre-existing commit and no approved-base history was
altered. `a6229ff` is the corrected commit.

## Changed files

**22 files changed, 5378 insertions(+), 6 deletions(−)** against the approved
base `4ac2bfe` (`git diff --shortstat 4ac2bfe..HEAD`).

Round 1 stated 21 files and +5079/−6. That was measured *before* the handoff was
committed, so it omitted `docs/app/handoffs/TASK-016.md` itself. The figures
above are the actual ones and include this document.

Line counts per file, from `git diff --numstat 4ac2bfe..HEAD`:

| File | + | − |
| --- | --- | --- |
| `docs/app/tasks/TASK-016-coach-daily-check-in-review-mobile.md` | 454 | 0 |
| `docs/app/handoffs/TASK-016.md` | 299 | 0 |
| `platform/apps/mobile/src/app/coach/index.tsx` | 10 | 6 |
| `.../coach-check-in/domain.ts` | 501 | 0 |
| `.../coach-check-in/coach-review-repository.ts` | 270 | 0 |
| `.../coach-check-in/coach-check-in-section.tsx` | 207 | 0 |
| `.../coach-check-in/view-state.ts` | 184 | 0 |
| `.../coach-check-in/failure-probe.ts` | 133 | 0 |
| `.../coach-check-in/athlete-check-in-card.tsx` | 122 | 0 |
| `.../coach-check-in/copy.ts` | 114 | 0 |
| `.../coach-check-in/query-options.ts` | 98 | 0 |
| `.../coach-check-in/errors.ts` | 94 | 0 |
| `.../coach-check-in/use-coach-check-in-review.ts` | 36 | 0 |
| `.../coach-check-in/test-fixtures.ts` | 297 | 0 |
| `.../coach-check-in/source-safety.test.ts` | 742 | 0 |
| `.../coach-check-in/coach-review-repository.test.ts` | 451 | 0 |
| `.../coach-check-in/domain.test.ts` | 448 | 0 |
| `.../coach-check-in/query-options.test.ts` | 358 | 0 |
| `.../coach-check-in/logging.test.ts` | 233 | 0 |
| `.../coach-check-in/view-state.test.ts` | 215 | 0 |
| `platform/apps/mobile/src/lib/query/keys.test.ts` | 94 | 0 |
| `platform/apps/mobile/src/lib/query/keys.ts` | 18 | 0 |

The `docs/app/handoffs/TASK-016.md` row is Round 1's 299 lines; Round 2 edits
this file further, so its final size is larger. `coach/index.tsx` is the **only**
pre-existing file with deletions, and its 6 removed lines are exactly the Team
placeholder `InfoCard`.

**Route wiring (owned):**

- `platform/apps/mobile/src/app/coach/index.tsx` — Team placeholder replaced by
  `<CoachCheckInReviewSection />`; the monitoring-flags and training-plan
  `InfoCard`s are unchanged.

**Feature (owned, all new) — `platform/apps/mobile/src/features/coach-check-in/`:**

| File | Role |
| --- | --- |
| `domain.ts` | stage parsers, grant-pair composition, fail-closed validation |
| `coach-review-repository.ts` | the three-stage read against an injected client |
| `errors.ts` | sanitized failures, including the distinct `capacity` category |
| `query-options.ts` | the cache contract |
| `view-state.ts` | identity boundary + the only function that can carry a check-in |
| `copy.ts` | every fixed Thai string |
| `use-coach-check-in-review.ts` | the single hook |
| `coach-check-in-section.tsx` | the section, and the identity boundary |
| `athlete-check-in-card.tsx` | one athlete's latest reading |
| `failure-probe.ts`, `test-fixtures.ts` | test support (not runtime, not bundled) |
| `domain.test.ts`, `coach-review-repository.test.ts`, `query-options.test.ts`, `view-state.test.ts`, `source-safety.test.ts`, `logging.test.ts` | tests |

**Query keys (owned):**

- `platform/apps/mobile/src/lib/query/keys.ts` — added `coachCheckInReview`
- `platform/apps/mobile/src/lib/query/keys.test.ts` — added its assertions

**Docs (owned):** the packet and this handoff.

**Nothing else changed.** No migration, policy, grant, function, view, pgTAP
file, config, or seed; no `database.types.ts`; no `package.json`,
`pnpm-lock.yaml`, dependency, Expo version, or tooling config; no existing auth,
athlete check-in, sharing, profile, component, theme, test-support, or
navigation file; no protected legacy path.

## Acceptance status

| # | Criterion | Status |
| --- | --- | --- |
| 1 | Team placeholder replaced, other two unchanged | **met** — AST-asserted: exactly 2 `InfoCard`, exactly 1 section |
| 2 | No route, detail screen, or tab | **met** — AST-asserted; web export lists the same 10 routes |
| 3 | Only the six approved fields selected and displayed | **met** — select lists pinned exactly in the scan |
| 4 | No `select("*")` | **met** — exact and fragment scan, incl. `(*)` |
| 5 | Stage c skipped with no active grants | **met** — asserted on the recorded table list |
| 6 | Overflow above 100 fails, never truncates | **met** — `capacity` failure with its own escalation wording; retry control still offered per the packet |
| 7 | Every fail-closed condition rejects the whole load | **met** |
| 8 | Key auth-scoped and health-free | **met** |
| 9 | Eight cache overrides hold against real `QueryClient`/`QueryObserver` | **met** — verified against deliberately hostile defaults |
| 10 | Health hidden during refresh and after a failed refresh | **met** |
| 11 | No logging, persistence, or write | **met** — AST + runtime |
| 12 | Every failure message from a fixed sanitized set | **met** |
| 13 | All verification commands pass | **met** — including the local database suite, run in Round 2 |
| 14 | Mutation evidence recorded | **met** — 7 mutations, all detected, all reverted |

## Safe verification counts

Run from `platform/` unless noted.

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 |
| `corepack pnpm format:check` | exit 0, all files match |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | exit 0 — **40 test files, 720 tests, 0 failures** |
| focused `vitest run src/features/coach-check-in src/lib/query` | exit 0 — **8 test files, 135 tests, 0 failures** |
| `corepack pnpm dlx expo-doctor@latest` (from `apps/mobile/`) | exit 1 — **20/21 checks pass**; the single failure is the known pre-existing patch drift (see limitations) |
| Android Expo export | exit 0 — 1 bundle, 1 metadata file |
| Web Expo export | exit 0 — **10 routes, unchanged from before this task** |
| `git diff --check` | exit 0, clean |
| working tree after all verification | clean |

Baseline before this task was 596 workspace tests (TASK-014) and 720 now,
including TASK-015's additions; this task contributes the 135 focused tests
above minus the pre-existing `src/lib/query` ones.

### Local database authorization suite — **RUN AND PASSED** (Round 2)

Run from `platform/` against the **local** stack only.

| Step | Result |
| --- | --- |
| `docker info` | exit 0 — daemon reachable (it was not in Round 1) |
| `corepack pnpm db:start`, stdout and stderr both redirected to `/dev/null` | **exit 0** |
| `corepack pnpm exec supabase db reset --local --no-seed` | **exit 0** — 4 migrations applied, no seed |
| `corepack pnpm exec supabase test db --local` | **exit 0** — **5 files, 583 assertions, `Result: PASS`, 0 failures** |
| `corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning` | **exit 0** — **0 findings** in `public` and `private` |
| `corepack pnpm db:stop`, both streams suppressed | **exit 0** |
| Supabase containers running afterwards | **0** |
| Supabase containers including stopped | **0** |

Counts match the TASK-014 baseline exactly — 5 files, 583 assertions, 0 lint
findings — which is the expected outcome, because this task changed no
`platform/supabase/` file. Round 1 cited that baseline; it is now
**independently re-verified** rather than cited.

Migrations applied by the reset, in order: `20260727120000_identity_teams_membership_rls`,
`20260727130000_profile_display_name_self_update`,
`20260728120000_consent_sharing_grants_rls`, `20260728140000_daily_check_ins_rls`.
All four are pre-existing and unmodified.

**Credential discipline.** `db:start` and `db:stop` had every stream redirected
to `/dev/null`; no output from either was displayed, stored, or classified.
`supabase status` and `db:status` were **never** run. `--linked` and a remote
database URL were **never** used. The reset, test, and lint outputs shown above
carry no credential material — the CLI prints only migration names, TAP results,
and a JSON lint envelope.

Two benign notices appeared in the pgTAP output and are pre-existing, unrelated
to this task, and not failures: `extension "pgtap" already exists, skipping`, and
one `WARNING: no privileges were granted for "pg_temp_17"` from
`005_daily_check_ins_rls_test.sql`. The suite still reported `Result: PASS` with
0 failures, and `db lint` — the check where warnings are configured to fail the
run — returned 0 findings.

The CLI also advised that Supabase CLI `v2.110.0` is available (installed
`v2.109.1`). **No upgrade was performed**: the CLI version is pinned in
`platform/package.json`, which this task may not modify.

## Mutation evidence

Each safeguard was weakened on the committed code, the focused suite was run,
and the file was restored with `git checkout`. Baseline is **135 passed / 0
failed**. Only counts are recorded.

| # | Safeguard weakened | File | Result |
| --- | --- | --- | --- |
| M1 | exact `check_in` category filtering removed | `domain.ts` | **2 files, 2 tests failed** |
| M2 | grant-to-team association check removed (stage b only) | `domain.ts` | **1 file, 1 test failed** |
| M2b | both association layers removed (stage b **and** the composition guard) | `domain.ts` | **2 files, 3 tests failed** |
| M3 | referenced-table `order` removed, `limit` kept | `coach-review-repository.ts` | **2 files, 2 tests failed** |
| M3b | referenced-table `limit` removed, `order` kept | `coach-review-repository.ts` | **1 file, 1 test failed** |
| M4a | coach user id dropped from the cache key | `lib/query/keys.ts` | **2 files, 6 tests failed** |
| M4b | failed refresh allowed to keep showing previous health values | `view-state.ts` | **2 files, 4 tests failed** |
| M4c | in-flight refresh allowed to render the previous list | `view-state.ts` | **1 file, 2 tests failed** |

M2 and M3 were each run twice because the first variant left a second defence in
place; M2b and M3b remove that too, which is what shows both layers are covered
rather than only one.

**Every mutation was reverted.** After the last revert, `git status --porcelain`
was empty and the full suite returned 40 files / 720 tests / 0 failures. **No
mutated code is committed**; the mutations were applied only after `c31dbdb`
existed, precisely so `git checkout` could prove the restoration.

One void run is disclosed for honesty: the first M4a attempt used a pattern that
did not match (the file has CRLF endings), so nothing was mutated and the suite
passed. That run proves nothing and was re-done correctly; the table records only
the valid run.

## Privacy and security impact

**Increase in exposure, stated plainly:** this is the first screen in the
application that shows one person protected health data belonging to **another
person**. That is the approved purpose of the task, and it is why the controls
below are stricter than anything else in the codebase.

- **Authorization is unchanged and remains in PostgreSQL.** No migration, policy,
  grant, or function was touched. Visibility is decided by
  `private.can_current_user_read_shared_data` via
  `daily_check_ins_select_shared_for_coach` and
  `sharing_grants_select_active_for_coach`. The route gate is UX only, and every
  client filter is re-validated against the response rather than trusted.
- **Consent is the association, not the roster.** `profiles_select_self_or_coached`
  makes coached athletes' identities broadly visible and the check-in policy is
  athlete-scoped rather than team-scoped, so composing on visibility alone would
  file a check-in under a team it was never shared with. The composition walks
  validated `(team, athlete)` grant pairs instead.
- **Dual-role self-leak is closed.** A grant naming the caller as the athlete in a
  team the caller coaches is impossible (`team_memberships` is unique on
  `(team_id, profile_id)`) and is treated as a closed failure, not filtered out.
  Stage b is additionally scoped to the coached team ids, so a dual-role user's
  legitimate athlete-side grants for other teams never enter this path.
- **Nothing protected is logged or persisted.** No console call happens on any
  path (runtime-verified); no AsyncStorage, SecureStore, filesystem, persister,
  analytics, crash context, session replay, notification, or background work
  exists (AST-verified).
- **Nothing raw is displayed.** No SQLSTATE, table name, RPC name, Supabase
  message, `details`, `hint`, `cause`, or payload; the repository does not read
  those fields at all. No raw UUID reaches the screen — the athlete card cannot
  even read `athleteProfileId`.
- **Cache exposure is minimized.** One auth-scoped entry per coach, no health
  value or identifier in the key, `gcTime: 0` so it is collectible on leaving the
  screen, and `clearAuthScopedQueries` plus an identity-keyed remount on any
  identity change.
- **No new write surface.** No mutation, no RPC, no insert/update/upsert/delete —
  AST-enforced, and the client double owns real write methods so a write would be
  counted rather than throwing and passing as a sanitized failure.
- **No real data.** Every fixture is synthetic. No `athletes/`, `team_data/`,
  `garmin/`, environment file, dump, or credential was read.

**Test-output safety:** no assertion in this task receives a health-bearing row,
object, mock payload, raw database error, or snapshot; results are reduced to
booleans, counts, fixed rule/case names, and identifier *labels* before `expect`.

## Known limitations

1. **Already-delivered screen data cannot be remotely recalled without Realtime.**
   A revocation while a card is on screen takes effect on the next successful
   query, not instantly. Accepted for this task; Realtime is out of scope.
2. **A null or blank `display_name` fails the whole load** rather than rendering,
   because a raw UUID must never be shown as a person's name. If real accounts can
   have blank display names, this will surface as a retryable error for the whole
   team list — worth a product decision before rollout.
3. **Capacity is capped at 100 active pairs.** Beyond that the screen fails
   closed rather than paginating or truncating. The **wording** differs from a
   generic failure — the title is `ข้อมูลเกินขนาดที่รองรับ` and the message asks
   the coach to contact the administrator, instead of the generic "please try
   again" — but the **deliberate retry control is still offered**, exactly as the
   task packet's UI-states table specifies ("sanitized capacity notice + retry,
   no partial list"). Pressing it will fail identically until the underlying
   number of active pairs drops, which is why the message points at escalation
   rather than at retrying. *(Round 1 described this as "non-retryable wording",
   which overstated it: only the message differs, not the availability of the
   control.)*
4. **A revoked grant racing the health-bearing read is shown as "not checked in
   yet".** If consent is revoked between stage b and stage c, stage b has already
   returned the pair, while `daily_check_ins_select_shared_for_coach` now refuses
   the embedded row, so the athlete renders as `ยังไม่ได้เช็กอิน` until the next
   successful load rather than disappearing. No health value is disclosed — the
   database refuses it — but for one load the state is misleading in the *safe*
   direction. A membership revocation in the same window instead makes an expected
   profile invisible, which fails the whole load as one retryable error.

   *(Round 1 claimed "a grant activated between stage a and stage b produces one
   retryable error." That was wrong and is corrected here. Stage b is filtered
   with `.in("team_id", <stage-a team ids>)` and re-validated against the same
   set, so a grant for an uncoached team is never returned in the first place, and
   a grant appearing for an already-coached team is simply included. That window
   produces no error at all. The genuine races are the two described above, both
   of which sit between stage b and stage c.)*
5. **Known pre-existing Expo patch drift persists** and is **out of scope**:
   `expo` found `56.0.17` vs expected `~56.0.18`, `expo-router` found `56.2.16` vs
   expected `~56.2.17`. **No dependency was changed.** 20/21 Expo Doctor checks
   pass.
6. **Supabase CLI `v2.110.0` is available; `v2.109.1` is pinned and installed.**
   Not upgraded — the pin lives in `platform/package.json`, which this task may
   not modify.

## Rollback

Fully additive on a dedicated branch:

```text
git switch feat/mobile-foundation
git branch -D feat/TASK-016-coach-daily-check-in-review-mobile
```

`feat/mobile-foundation` is untouched at `4ac2bfe`. No migration ran, no remote
state changed, no dependency moved, and no Supabase container remains, so nothing
outside the branch needs reverting. To revert only the implementation and keep
the packet, `git revert c31dbdb`.

## For the reviewer (GPT/Codex, read-only)

Suggested focus, highest value first:

1. `domain.ts` — the grant-pair composition and every fail-closed branch. This is
   where a wrong athlete could be attached to a team.
2. `view-state.ts` — the branch order in `readCoachReviewView`. The error check
   preceding the data check is the whole "hide stale health on a failed refresh"
   guarantee.
3. `coach-review-repository.ts` — stage ordering, the skip conditions, and the
   referenced-table `order`/`limit` pair.
4. Whether limitation 2 (blank display name fails the load) is the right product
   call.
5. Whether the 100-pair cap is right, and whether offering the retry control on a
   capacity failure — which the packet specifies and the UI does — is the
   behaviour you want, given that retrying cannot succeed until the number of
   active pairs drops.
6. Limitation 4: a grant revoked between stage b and stage c renders as
   "ยังไม่ได้เช็กอิน" for one load. No data is disclosed, but the wording is
   briefly misleading.

**Not done, deliberately:** no merge, push, deploy, publish, hosted-Supabase
link, remote migration, branch deletion, or worktree removal.
