# TASK-013 Handoff — Athlete Daily Check-In Mobile Vertical Slice

Status: Implemented and verified locally. Awaiting GPT/Codex read-only review.

One defect was found in this task's own tests during mutation testing and fixed
before handoff; it is recorded in full below rather than quietly corrected.

## Task and ownership

- Task packet: `docs/app/tasks/TASK-013-athlete-daily-check-in-mobile.md`
- Writer: **Claude Code** (sole writer)
- Reviewer: **GPT/Codex, read-only.** No reviewer edited any implementation file.
- AGY: **not used.**
- Ownership was not transferred at any point.
- The Product Owner approved the complete scope and product/security decisions
  1–10 before implementation started.

## Branch and worktree

- Worktree: `.claude/worktrees/task-013-athlete-daily-check-in-mobile`
  (isolated, **preserved** for the reviewer, still locked)
- Branch: `feat/TASK-013-athlete-daily-check-in-mobile`
- Source branch: `feat/mobile-foundation`
- Approved base SHA: `9784854a691e8a5aa22fc0e299783a751c8adce1`
- Worktree clean at handoff.

The automatic worktree branch `worktree-task-013-athlete-daily-check-in-mobile`
was renamed to the task branch name with `git branch -m`. No other branch was
created, moved, or deleted, and no second worktree was created.

### Pre-flight, confirmed before the first edit

| Gate | Result |
| --- | --- |
| worktree clean | yes, `git status --porcelain` empty |
| `HEAD` is the approved base | `9784854a691e8a5aa22fc0e299783a751c8adce1` exactly |
| the base is the approved `feat/mobile-foundation` tip | yes; `feat/mobile-foundation` resolves to the same SHA |
| the base is an ancestor of the task branch | yes, `git merge-base --is-ancestor` exit 0 |
| the intended task branch already exists elsewhere | no, `refs/heads/feat/TASK-013-...` absent |
| renaming would overwrite or conflict | no, the target name was unused |
| main checkout modified | no |

The base SHA is simultaneously the tip of `feat/mobile-foundation` and of
`feat/TASK-012-daily-check-in-rls`, so the TASK-012 database contract consumed
here is present in the base and is a settled dependency.

The isolated worktree permission canary was requested by its exact absolute
worktree path
`D:\...\.claude\worktrees\task-013-athlete-daily-check-in-mobile\docs\app\permission-canary\WORKTREE-CANARY.md`
using the built-in `Read` tool only. It was **denied before any content was
returned** (`File is in a directory that is denied by your permission
settings`), so the denial is directory-scoped and no content reached the
session. No Bash, PowerShell, `grep`, `cat`, Glob, search, or other fallback was
used against it, and no retry through a different path form was attempted. No
protected legacy path and no root `CLAUDE.md` was read, and no recursive search
was run from the repository root.

### Commit ledger

| Commit | Purpose | Changed files |
| --- | --- | --- |
| `1bdea3666a54b7fd1c87597d09706b180b2b288e` | task packet, documentation checkpoint before any application-code edit | 1 |
| `5c7de271a8530494bb43d27acfaddc1925b38611` | implementation | 22 |
| `14de1f953a52d9281898d3ca25e29d696abff45d` | mutation-driven fix to this task's own logging test | 1 |
| branch HEAD | this handoff | 1 |
| **Complete TASK-013 diff against `9784854`** | | **24** |

No commit was amended, rebased, or rewritten.

## Changed files

Twenty-three files across the three commits so far, plus this handoff — 24 in the
complete diff against the base, all inside the packet's owned paths.

| File | Change |
| --- | --- |
| `docs/app/tasks/TASK-013-athlete-daily-check-in-mobile.md` | new task packet, committed before implementation |
| `docs/app/handoffs/TASK-013.md` | this handoff |
| `platform/apps/mobile/src/app/athlete/index.tsx` | the check-in placeholder card replaced with the real inline card; +12/−7 lines |
| `platform/apps/mobile/src/features/check-in/domain.ts` | new; domain type and strict fail-closed validation |
| `platform/apps/mobile/src/features/check-in/local-date.ts` | new; device-local date and rollover detection |
| `platform/apps/mobile/src/features/check-in/errors.ts` | new; sanitized load/save failures |
| `platform/apps/mobile/src/features/check-in/submission.ts` | new; draft state and the submission plan |
| `platform/apps/mobile/src/features/check-in/check-in-repository.ts` | new; load and update-first save |
| `platform/apps/mobile/src/features/check-in/query-options.ts` | new; pure query and mutation options |
| `platform/apps/mobile/src/features/check-in/use-daily-check-in.ts` | new; the two hooks |
| `platform/apps/mobile/src/features/check-in/copy.ts` | new; all athlete-facing strings |
| `platform/apps/mobile/src/features/check-in/choice-group.tsx` | new; accessible single-select group |
| `platform/apps/mobile/src/features/check-in/check-in-card.tsx` | new; the inline card |
| `platform/apps/mobile/src/features/check-in/raw-source.d.ts` | new; module declaration letting a test import source as text |
| `platform/apps/mobile/src/features/check-in/domain.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/local-date.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/submission.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/check-in-repository.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/query-options.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/errors.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/source-safety.test.ts` | new |
| `platform/apps/mobile/src/features/check-in/logging.test.ts` | new |
| `platform/apps/mobile/src/lib/query/keys.ts` | `authScopedKeys.dailyCheckIn` added; +11 lines, nothing removed |
| `platform/apps/mobile/src/lib/query/keys.test.ts` | coverage for the new key; +47 lines, nothing removed |

**Not changed**, verified against the base: no migration, no pgTAP test,
`platform/apps/mobile/src/lib/supabase/database.types.ts`, `package.json`,
`apps/mobile/package.json`, `platform/pnpm-lock.yaml`,
`platform/supabase/config.toml`, `seed.sql`, `platform/apps/mobile/src/theme/tokens.ts`,
every file under `platform/apps/mobile/src/components/`, every architecture
document, and every protected legacy path. `git diff --stat <base> HEAD --
apps/mobile/package.json package.json pnpm-lock.yaml` is empty.

## What was built

### Placement and routing

The check-in is inline on the existing Athlete Today screen (decision 1). No
route, layout entry, or navigation target was added, and the auth gate was not
touched: `expo export --platform web` still reports **13 static routes**, the
same count as TASK-009 and TASK-010. The card is reachable only where
`canEnterRoleArea(gate, "athlete")` already holds, so pending, revoked,
unauthenticated, and coach-only users gain no self-data route from this task.
PostgreSQL grants and RLS remain the authorization boundary; nothing in this
slice treats client code as a security control.

### The local calendar date

`local-date.ts` composes `YYYY-MM-DD` by hand from `getFullYear`, `getMonth`,
and `getDate` (decision 2). No `toISOString`, `toJSON`, `getUTC*`, `Date.UTC`,
`toUTCString`, or `toLocaleDateString` appears anywhere in the feature's code —
asserted structurally, not just behaviourally. A `LocalDateStamp` also carries
`getTimezoneOffset()`, because a user crossing a timezone can keep the same
printed date while the day boundary moves under them.

An invalid `Date` produces a string the date guard rejects, so the failure
surfaces as a refused write rather than a wrongly dated row.

### Domain validation

`rpe` integer 0–10, `overall_feeling` integer 1–5, `pain_status` exactly `none`
or `present`, case-sensitive. `Number.isInteger` rejects `NaN`, infinities, and
every fractional value. A `DailyCheckIn` cannot be constructed except through a
parse that checked all three fields, so a partially valid row is rejected
outright rather than rendered or cached. Nothing is coerced, rounded, or trimmed.

### The repository

Load selects only `rpe, overall_feeling, pain_status`, filtered to the verified
user id and the exact captured date, and returns either one validated value or
`null`. **An error is never an empty result**: `null` means "no check-in today",
and every failure raises `CheckInDataError`.

Save re-validates the input, then runs the approved update-first algorithm:

1. scoped `UPDATE` naming only the three mutable columns, `select("id")` so
   "matched" can be told from "did not match" without any health value returning;
2. if nothing matched, `INSERT` naming only the five approved columns, with no
   `.select()` at all, so no representation travels back;
3. if that insert fails **SQLSTATE `23505`**, the same scoped `UPDATE` runs
   exactly once more;
4. any other insert failure, and a retry that still matches nothing, becomes a
   fixed sanitized error.

`.upsert()` is never used. The race is detected by `error.code` alone; the
repository's code contains no `.message`, `.details`, or `.hint` access at all.
The athlete id comes only from the caller-supplied verified id — an input object
carrying `athlete_profile_id` is ignored, which is asserted directly.

### Cache

`authScopedKeys.dailyCheckIn(userId, localDate)` →
`["auth-scoped", userId, "daily-check-in", localDate]`. Four strings: the user
id and a plain calendar date, no health value. It keeps the shared `AUTH_SCOPE`
prefix, so `clearAuthScopedQueries` still drops it outright when the identity
changes. The local date travels through the mutation variables and back out of
`mutationFn`, so `onSuccess` invalidates exactly the day that was written even if
the device day moved mid-flight. `retry: 0`, and there is no `onMutate` and no
`setQueryData` anywhere in the feature.

### Rollover

The local stamp is recomputed at submission. If the calendar date or the offset
moved, the plan returns `rollover` — checked **before** completeness, so a
half-filled form is also reset — the card drops the draft, re-queries the new
date, and shows fixed non-sensitive copy asking the athlete to review the current
day's form. The stale date is never written to.

### UI

Concise explanation; the current date shown; RPE 0–10 as eleven chips; five
labelled feeling choices; two pain choices; **no preselected answer**; clear
selected styling; `radiogroup`/`radio` roles with spoken labels and
`selected`/`disabled`/`busy` state; 48×48 minimum targets; loading text;
load-error notice with a deliberate retry button; distinct empty and
prefill/edit copy; save disabled until all three answers exist and while a save
is in flight; fixed sanitized success and error notices; and fixed
non-diagnostic pain safety copy stating that the check-in is not a medical
diagnosis and that urgent or concerning symptoms need professional care. No
database terminology and no raw error is shown.

## Acceptance-criteria results

All fifteen criteria met.

| # | Criterion | Where it is enforced and proved |
| --- | --- | --- |
| 1 | active athlete can load today's check-in | `useDailyCheckInQuery` + `loadDailyCheckIn`; repository tests for the row, the empty, and the failure case |
| 2 | no row gives an empty form with no defaults | `draftFromCheckIn(null)` → `EMPTY_DRAFT`; three nulls asserted; save disabled |
| 3 | valid form creates today's row | update-then-insert path asserted, insert payload pinned to five columns |
| 4 | valid form updates today's row | update-only path asserted, no insert issued |
| 5 | every read/write scoped to the verified user and exact date | filter lists pinned for load, update, insert, and the retry |
| 6 | invalid server rows fail closed | six invalid-row cases, all rejected; mutation M10 proves the guard is load-bearing |
| 7 | insert races follow the 23505 retry | exactly one extra scoped update asserted; six other failure codes proved not to retry |
| 8 | rollover cannot write to a stale date | rollover checked first; three stale pairs proved never to yield `submit`; mutation M2 fails 4 assertions |
| 9 | routing not weakened | no route added; web export still 13 static routes; gate, layout, and `ROUTES` untouched |
| 10 | no health value logged, in analytics, drafted, keyed, or printed in failure output | source scan + runtime console-spy count; key pinned to four strings; every health assertion reduced to a boolean/count/name |
| 11 | no migration, RLS, generated type, dependency, lockfile, theme, or out-of-scope change | 24 files, all owned; manifest diff against the base empty; pgTAP still 583 assertions |
| 12 | local verification passes | table below; one pre-existing Expo patch-version finding, outside the owned scope |
| 13 | documentation matches implementation | packet and this handoff written against the delivered code |
| 14 | Git clean, work committed on the task branch | `git status --short` empty; three commits plus this handoff |
| 15 | nothing merged, pushed, deployed, remotely migrated, or cleaned up | confirmed below |

## Negative and failure-path matrix

All 21 packet cases pass. The suite contributes **129 tests across 10 files** in
the focused run (8 new check-in files plus `lib/query`), and the full suite is
**439 tests across 26 files**, up from 327 across 18 at the base.

| # | Case | Result |
| --- | --- | --- |
| 1 | local date formatting, including local ≠ UTC both directions | PASS — a `Date` stand-in makes it non-vacuous on any machine, including UTC+00:00 |
| 2 | valid values at every boundary | PASS — all 110 combinations accepted, asserted as a count |
| 3 | null, missing, fractional, out-of-range, non-numeric, unknown | PASS — 29 rejection cases, plus a coercion probe |
| 4 | load with no row | PASS — `null` |
| 5 | load with a row | PASS — validated, compared as a boolean |
| 6 | load error | PASS — raises; `denied` and `offline` classified |
| 7 | load scoping | PASS — filter list pinned; different user and date produce different filters |
| 8 | save with an invalid input | PASS — 11 cases, zero client calls each |
| 9 | existing row | PASS — 1 update, 0 inserts |
| 10 | missing row | PASS — update then insert, in that order |
| 11 | 23505 insert race | PASS — 2 updates, 1 insert, retry payload and filters pinned |
| 12 | non-23505 insert failure | PASS — 6 codes, none retried |
| 13 | failed retry | PASS — sanitized save error after 2 updates |
| 14 | written columns | PASS — update names exactly 3, insert exactly 5 |
| 15 | write responses | PASS — `select("id")` only; save resolves `undefined` |
| 16 | query key | PASS — pinned to four strings; no health fragment |
| 17 | rollover | PASS — date change, offset change, and incomplete-draft rollover |
| 18 | fixed errors | PASS — 8 forbidden fragments absent from the thrown message; 24 forbidden fragments absent from all 7 fixed messages |
| 19 | mutation retry | PASS — `retry: 0`, and no `onMutate` present |
| 20 | health leakage | PASS — source scan across 10 files and a runtime console count across 5 paths |
| 21 | `.upsert()` | PASS — absent from the source, and the client double has no `upsert` method |

## Mutation evidence

The suite passed on its first run, which alone is not evidence that it
constrains anything. Ten deliberate defects were applied one at a time to the
committed source and the suite re-run. Each was verified by `git diff --numstat`
to be exactly the intended edit, then reverted with `git checkout --` and
confirmed restored. Full output was captured to a variable and filtered; only
counts and assertion names are reported.

| Mutation | Result |
| --- | --- |
| M1 local date derived through `toISOString().slice(0, 10)` | **FAIL — 7 of 439**: five `formatLocalDate` assertions plus both source-scan guards |
| M2 rollover check removed from `planSubmission` | **FAIL — 4 of 439** |
| M3 insert failure retried regardless of SQLSTATE | **FAIL — 1 of 439** — the six-code no-retry matrix |
| M4 `RPE_MAX` widened from 10 to 20 | **FAIL — 5 of 439** across 3 files |
| M5 a health-ish part appended to the query key | **FAIL — 3 of 439** across 2 files |
| M6 `console.error(error)` added to the load failure path | **FAIL — 1 of 439** — see the correction below |
| M7 automatic mutation retry enabled (`retry: 3`) | **FAIL — 1 of 439** |
| M8 a fourth column named in the scoped update | **FAIL — 2 of 439** |
| M9 update no longer scoped to the captured date | **FAIL — 2 of 439** |
| M10 invalid server row returned instead of failing closed | **FAIL — 1 of 439** |

`git status --short` is empty after the full mutation pass, and the unmutated
suite passes at 439.

### Defect found in this task's own tests, and fixed

M6 is the reason this section exists. Adding `console.error(error)` to the
repository's load failure path failed only the **source scan**, while
`logging.test.ts` — the file whose entire purpose is to prove no health value
reaches a log at runtime — stayed fully green.

The cause: `countConsoleCalls` read `spy.mock.calls.length` *after* the
`finally` block called `mockRestore()`. `mockRestore` also resets the mock, which
clears `mock.calls`, so every count was unconditionally zero and all five
assertions in that file were vacuous.

Fixed in commit `14de1f9` by taking the count inside the `try`, before the
`finally` restores the spies. Re-running the identical mutation now fails the
file (**1 of 5**), and the unmutated file still passes at 5. Two honest points:

- The rule itself was never unenforced. `source-safety.test.ts` caught M6 on the
  first attempt, which is why the defect was visible at all.
- The first re-run attempt was invalid: an inline PowerShell `if` expression is
  not valid in PowerShell 5.1, which silently produced a different mutation
  (`numstat 1 3` instead of `1 0`) and a passing run. That evidence was
  discarded and the mutation re-applied from a script file with the correct
  `numstat 1 0`.

Two mutation-harness process notes, neither reaching the delivered code. `*>`
redirection of a native command under `$ErrorActionPreference = "Stop"` raises a
terminating `NativeCommandError`, so the harness was rewritten to capture output
through a pipeline. And four multi-line anchors initially missed, because
`git checkout --` had rewritten those files to CRLF while the anchors used LF;
the second pass normalizes each anchor to the file's own line ending, and all
four then applied and failed the suite as recorded above.

## Commands run and results

Local only. No `--linked`, no project ref, no remote URL, no hosted Supabase
contact, and no `supabase status` or `db:status`.

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0, lockfile unchanged |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0, no error and no warning |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | exit 0 — **26 files, 439 tests passed** |
| focused: `vitest run src/features/check-in src/lib/query` | exit 0 — **10 files, 129 tests passed** |
| `corepack pnpm dlx expo-doctor@latest` (from `apps/mobile`) | **20/21 checks passed**, 1 pre-existing failure — see below |
| `corepack pnpm exec expo export --platform web` | exit 0, **13 static routes**, unchanged from TASK-009/010 |
| `corepack pnpm exec supabase --version` | `2.109.1` |
| start local stack, all streams suppressed | exit 0, 10 containers |
| `corepack pnpm exec supabase db reset --local --no-seed` | exit 0, no seed and no real data |
| `corepack pnpm exec supabase test db --local` | **PASS — 5 files, 583 assertions**, identical to TASK-012, so nothing in the database changed |
| `supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, "No schema errors found" |
| stop local stack, all streams suppressed | exit 0 |
| container count after stopping | **0 running, 0 total** matching `supabase_` |
| `git diff --check` | clean |
| `git status --short` | clean at handoff |

`db:start` and `db:stop` ran with `*> $null`, so the API URL, anon key,
service-role key, JWT secret, and database URL never reached the terminal, the
transcript, or a log. The container check is count-only; no container
environment variable was inspected or printed. `supabase test db` output was
captured and filtered to summary lines. `db lint` output contains no credential.

### The one failing verification command

`expo-doctor` fails its "packages match versions required by installed Expo SDK"
check with two **patch-level** mismatches: `expo` 56.0.17 against an expected
`~56.0.18`, and `expo-router` 56.2.16 against `~56.2.17`. Upstream released
newer patches after the lockfile was pinned.

This is **pre-existing and outside the owned scope**. Correcting it requires
editing `apps/mobile/package.json` and `platform/pnpm-lock.yaml`, which the
packet's out-of-scope list explicitly forbids. Proof that this task did not
cause it: `git diff --stat 9784854 HEAD -- apps/mobile/package.json package.json
pnpm-lock.yaml` produces no output. Per the packet's rule, it is reported rather
than fixed, and it needs a Product Owner decision and its own task.

Note also that `expo-doctor` must be run from `apps/mobile`; run from
`platform/` it cannot find the SDK and, misleadingly, still exits 0.

## Privacy and security impact

**This is the first application code in the product that handles protected health
data.** `rpe`, `overall_feeling`, and `pain_status` are protected under
`AGENTS.md`, and the verified user id plus `check_in_date` make them
attributable.

- **All fixtures are synthetic.** Every health literal in the tests was invented
  for the test. No real athlete name, address, email, or measurement was used,
  read, or written, and no protected legacy path was accessed.
- **No health value is printed in test output.** Every health-bearing assertion
  is reduced before it reaches `expect`: to a boolean, a row/statement count, a
  sorted column-name list, or a list of **case names**. No whole request or
  response object is compared or snapshotted, no snapshot exists, no captured
  error or payload is used as an assertion message, and no mock call containing
  health values is printed. Payload equality is computed inside a helper that
  returns only `true`/`false`.
- **No health value reaches a log, analytics, crash context, session replay, a
  push payload, or storage.** Proved two ways: a source scan over all ten
  implementation files for `console.*`, `Sentry`, `trackEvent`, `AsyncStorage`,
  `SecureStore`, `localStorage`, `setItem`, `MMKV`, `FileSystem`, `persist`,
  `outbox`, `setInterval`, `setTimeout`, `Notifications`, and background-task
  APIs; and a runtime console-call count across five paths including a refused
  read, an insert race, a rejected input, and a stale date. The runtime half was
  vacuous until commit `14de1f9` — see the mutation section.
- **No draft is persisted.** The three answers live in component state only.
  Closing the app loses them, which is the intended online-only behaviour.
- **No health value is in a query key**, and the cache remains memory-only and is
  dropped outright by `clearAuthScopedQueries` on any identity change.
- **No raw error reaches the athlete.** Every failure is classified from `code`,
  `status`, or the constructor name and mapped to one of seven fixed strings. The
  original error is not passed to `super`, stored on a field, or kept as a
  `cause` — `Object.keys` on a thrown `CheckInDataError` is exactly
  `["failure", "intent", "name"]`. A thrown value that is not a
  `CheckInDataError` has its message discarded wholesale rather than displayed.
- **No pain free text, location, severity, image, or diagnosis is collected**, so
  unstructured health disclosure stays structurally impossible. The safety copy
  is fixed and offers no interpretation.
- **The security posture is unchanged.** No grant, policy, migration, generated
  type, or route was added or loosened; the database is untouched, and the pgTAP
  suite still passes at exactly 583 assertions.
- No service-role key, credential, API URL, JWT secret, database URL, access
  token, real email address, or real user id was printed, persisted, or
  committed. The only identifiers in the tests are synthetic zero-padded UUIDs.

## Known limitations

- **Only today, only the athlete's own row.** No history, no past or future date,
  no coach view, no export, and no delete — TASK-012 grants no client `DELETE`.
- **Last-completed-write-wins.** Two devices editing the same day both succeed
  and the later write survives. No version history, conflict UI, or audit trail
  exists, by decision 8.
- **The date is client-asserted.** The database cannot verify that the device's
  local date is honest, and accepts any date the grants allow. That is TASK-012's
  recorded limitation, unchanged here.
- **Rollover is detected at submission, not continuously.** A form left open past
  midnight still shows the old date until the athlete presses save, at which
  point the write is blocked and the form resets. No timer polls for the change,
  because decision 10 rules out background work; the trade-off is a stale-looking
  date rather than a wrongly dated row.
- **No component-level test.** The packet forbids adding a renderer, so the
  card's own wiring — the prefill effect, the disabled conditions, the notice
  visibility — is not covered by an automated test. Every decision the card makes
  is delegated to a tested pure function, but the JSX that calls them is verified
  only by typecheck, lint, and the web export.
- **The insert-race retry cannot be exercised against the real database.** A
  genuine `23505` needs two concurrent writers; the path is proved against the
  client double only.
- **`raw-source.d.ts` is a test-support affordance.** It exists so the source
  scan can read files without `@types/node`, which this task may not add. It
  declares one wildcard module and affects no runtime code.
- **A load error and an RLS-filtered read are indistinguishable to the client.**
  A refused `SELECT` returns zero rows rather than raising, so it presents as the
  normal empty form. That is the correct fail-closed outcome here — an empty form
  discloses nothing — but it means the UI cannot tell "no check-in yet" from "not
  allowed to see it".
- **Thai copy has not been reviewed by a second reader.** Wording, and especially
  the safety copy, is a Product Owner call.
- Local Analytics remains disabled from TASK-007, so Studio's Logs section is
  empty locally.

## Rollback

Documentation and additive application code only. Nothing is merged, so no remote
or database action is involved and no migration exists to reverse.

```powershell
# discard the last commit on the task branch, keeping the changes staged
git reset --soft HEAD~1

# discard the whole task, returning the branch to the approved base
git reset --hard 9784854a691e8a5aa22fc0e299783a751c8adce1

# or simply abandon the branch; feat/mobile-foundation is untouched
```

Reverting `platform/apps/mobile/src/app/athlete/index.tsx` alone removes the
card from the screen while leaving the feature module dormant and unreachable.
The local database is rebuilt with `supabase db reset --local --no-seed` if a
verification run left it dirty.

## Remaining reviewer questions

1. **The empty form as the RLS-refusal outcome.** A refused `SELECT` returns zero
   rows, so it is presented as "no check-in today" rather than as an error. I
   read that as correct and fail-closed. Confirm, or specify a distinguishable
   state.
2. **Rollover detected only at submission.** Accept, or is a foreground-return
   re-check wanted despite decision 10's prohibition on background work?
3. **`select("id")` on the update.** The sentinel is what distinguishes "matched"
   from "did not match" through RLS. Confirm returning a row id is acceptable, or
   require a different match signal.
4. **The failed-retry outcome maps to `unknown`, so the athlete sees the generic
   save failure.** Confirm, or specify distinct wording for "someone else changed
   today's check-in".
5. **`raw-source.d.ts` and the `?raw` imports.** Accept as the dependency-free
   way to run the source scan, or should the scan be dropped instead?
6. **The pre-existing `expo-doctor` patch drift** needs a decision and its own
   task; it is untouched here.
7. **Thai copy, and the pain safety wording in particular**, needs Product Owner
   sign-off.
8. **No component test** for the card, by the packet's no-new-dependency rule.
   Confirm that the pure-function split is sufficient coverage for this slice.

## Confirmation

Explicitly confirmed for this task:

- **Nothing was merged.** No merge, rebase, cherry-pick, or fast-forward onto any
  branch.
- **Nothing was pushed.** No `git push`, and the repository has no remote
  configured for this branch.
- **Nothing was deployed or published.**
- **No hosted Supabase contact.** No `supabase link`, no `db push`, no project
  ref, no remote database URL, no `--linked`, and no remote migration. Every
  database command targeted the local stack.
- **No `supabase status` or `db:status` output was produced or pasted**, and every
  credential-bearing stream was suppressed.
- **Nothing was cleaned up.** The worktree is preserved and still locked, the task
  branch is preserved, and no branch was deleted.
- **The main repository checkout was not modified**; it remains on
  `feat/mobile-foundation` at the base SHA.
- **No protected legacy path was read, searched, or modified**, and no recursive
  search was run from the repository root.
- **No AGY use, no ownership transfer, and no reviewer edits.**
- **No production or real athlete data, no health value belonging to a real
  person, no token, key, secret, database URL, or environment file** was read,
  printed, committed, or placed in this handoff.

Work stops here, pending Product Owner and GPT/Codex read-only review.
