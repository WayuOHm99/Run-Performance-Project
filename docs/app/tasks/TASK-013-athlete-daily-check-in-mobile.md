# TASK-013: Athlete Daily Check-In Mobile Vertical Slice

Status: **Round 3 findings fixed and verified locally. Awaiting GPT/Codex
read-only Round 3 review.**

The Product Owner approved the complete scope and product/security decisions 1–10
below before implementation started, then approved the eight Round 2 findings (one
high, five medium, two low) and the three Round 3 findings (one medium, two low)
before each of those rounds started. Results, evidence, the verification record,
and the mutation and leak-scan records for every round are in
`docs/app/handoffs/TASK-013.md`.

No approved decision was changed in Round 2 or Round 3. Every fix stayed inside
the owned paths listed below, and `src/test-support/capture-error.ts` was
deliberately not modified. Round 3 changed no runtime application code and no
database contract — the only source file it touched is a test.

Date: 2026-07-30

Writer: **Claude Code** (sole writer)

Reviewers: **GPT/Codex, read-only.** A reviewer does not edit the implementation.

AGY: **not used** for this task.

Ownership does not transfer during this task.

## Base and branch

- Source branch: `feat/mobile-foundation`
- Approved base SHA: `9784854a691e8a5aa22fc0e299783a751c8adce1`
- Task branch: `feat/TASK-013-athlete-daily-check-in-mobile`
- Worktree: `.claude/worktrees/task-013-athlete-daily-check-in-mobile` (isolated,
  created by the required Claude `-w` launch, preserved for the reviewer)

The base SHA is simultaneously the tip of `feat/mobile-foundation` and the tip of
`feat/TASK-012-daily-check-in-rls`, so the TASK-012 database contract this task
consumes is present in the base rather than being a moving dependency.

Verified before the first edit: worktree clean, `HEAD` exactly the approved base,
the approved base an ancestor of the task branch, and no pre-existing
`feat/TASK-013-athlete-daily-check-in-mobile` branch anywhere. The automatic
worktree branch `worktree-task-013-athlete-daily-check-in-mobile` was renamed to
the task branch name; no other branch was created, moved, or deleted.

## Goal and user value

The smallest mobile vertical slice that lets an authenticated user with an active
athlete membership **load, create, and update their own daily check-in for the
device-local current calendar date** from the existing Athlete Today screen.

The normal flow is intended to take about 30 seconds, which is the charter's
success measure for check-in.

This task **consumes** the TASK-012 database contract and RLS. It does not change
the schema, grants, policies, migrations, or generated database types.

## In scope

- Inline daily-check-in card on the existing Athlete Today screen.
- Device-local date utility.
- Fail-closed domain validation of data received from the server.
- Supabase repository for loading and saving the current user's current-date row.
- TanStack Query hook.
- Authentication-scoped query key containing the verified user id and local date.
- Loading state, empty state, prefilled/edit state, busy/disabled state.
- Fixed sanitized success and error feedback.
- Date/timezone rollover handling.
- Pure-logic and repository tests using existing dependencies only.
- Task packet and sanitized handoff.
- Local and synthetic verification only.

## Out of scope

Coach view. Check-in history. Past- or future-date entry. Team administration,
membership management, or invitations. Sharing-grant UI. Deletion or export UI.
Training plans. Sleep or workout ingestion. Monitoring flags. Garmin, Strava,
WHOOP, COROS, Health Connect, or HealthKit integration. Offline drafts, outbox,
background sync, or notifications. New database migration. RLS or grant changes.
Generated database-type changes. Dependency or lockfile changes. Shared
design-system/theme refactors. Hosted Supabase or production operations.

## Owned paths

TASK-013 may create or modify only:

- `docs/app/tasks/TASK-013-athlete-daily-check-in-mobile.md`
- `docs/app/handoffs/TASK-013.md`
- `platform/apps/mobile/src/app/athlete/index.tsx`
- `platform/apps/mobile/src/features/check-in/**`
- `platform/apps/mobile/src/lib/query/keys.ts`
- `platform/apps/mobile/src/lib/query/keys.test.ts`

If the implementation requires any path outside this list, stop and request
Product Owner approval. Scope is not silently expanded.

## Forbidden paths

Never requested, read, searched, edited, enumerated, or accessed:

- root `athletes/`
- root `team_data/`
- root `garmin/`
- root `scripts/`
- root `supabase/`
- root `CLAUDE.md`
- root `.agents/AGENTS.md`
- root `.claude/settings.json`
- root `.claude/settings.local.json`

No broad recursive search runs from the repository root. Inspection and search are
restricted to `platform/` and `docs/app/`.

Additionally not modified by this task, though not legacy: any migration, any
pgTAP test, `platform/apps/mobile/src/lib/supabase/database.types.ts`, any
dependency manifest, `platform/pnpm-lock.yaml`, `platform/supabase/config.toml`,
`platform/apps/mobile/src/theme/tokens.ts`, and every shared component under
`platform/apps/mobile/src/components/`.

## References

- `AGENTS.md`, `platform/AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md` — 30-second check-in; RPE, feeling, and
  pain/injury status are protected health data and must not appear in push
  payloads, analytics, crash context, or logs
- `docs/app/AI-WORKING-AGREEMENT.md` — ownership, handoff format, privacy rules
- `docs/app/architecture/ADR-0001-platform-boundary.md`
- `docs/app/tasks/TASK-012-daily-check-in-rls-foundation.md` and
  `docs/app/handoffs/TASK-012.md` — the database contract consumed here
- Existing mobile patterns: `features/auth/gate.ts`, `features/auth/errors.ts`,
  `features/profile/account-repository.ts`, `features/profile/use-account.ts`,
  `lib/query/keys.ts`, `lib/query/client.ts`, `lib/supabase/app-client.ts`

Chat history is context only. The approved decisions are recorded here, in Git.

## Consumed TASK-012 database contract

`public.daily_check_ins`, unchanged by this task:

- `unique (athlete_profile_id, check_in_date)` — one row per athlete per date.
- `authenticated` holds table-wide `SELECT`,
  `INSERT (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)`,
  and `UPDATE (rpe, overall_feeling, pain_status)` only. Naming any other column
  in a write fails `42501` at the privilege layer.
- No `DELETE` privilege and no `DELETE` policy for any client role.
- Self policies: `daily_check_ins_select_own`, `daily_check_ins_insert_own`,
  `daily_check_ins_update_own`, each constrained to `auth.uid()`.
- `id`, `created_at`, `updated_at` are database-controlled.
- Range and value violations are refused with one fixed sanitized `22023`.
- A duplicate `(athlete_profile_id, check_in_date)` is refused with `23505`.

The database is the authorization boundary. Nothing in this task treats client
code as a security control.

## Approved product and security decisions

**1. Placement.** The check-in is inline on the existing Athlete Today screen. No
new route is added.

**2. Date.** The official UI may write only the device-local current calendar
date, formatted manually as `YYYY-MM-DD` from the local year, local month, and
local day. `toISOString()` and any other UTC conversion are prohibited for this
purpose.

**3. RPE.** Overall exertion from all training performed that day, `0`–`10`,
where `0` is rest/no exertion and `10` is maximum exertion. The UI recommends
completing it after the final session or during the evening.

**4. Overall feeling.** Exactly five values, higher is better: `1` very poor,
`2` poor, `3` normal, `4` good, `5` very good.

**5. Pain status.** Exactly `none` or `present`. No pain location, free text,
image, severity, diagnosis, or medical interpretation is collected. Fixed
non-diagnostic safety copy states that the check-in does not provide a medical
diagnosis and that urgent or concerning symptoms require appropriate professional
care.

**6. No defaults.** No health answer is preselected or defaulted. The athlete must
explicitly choose RPE, overall feeling, and pain status before saving. Controls
expose clear selected, disabled, and busy states, accessible labels and state, and
suitable mobile touch targets.

**7. Update-first save.** Validate the complete input; `UPDATE` the row scoped to
the verified authenticated user and the captured local date, touching only `rpe`,
`overall_feeling`, and `pain_status`, returning only a non-health sentinel such as
`id`; if no row matched, `INSERT` only `athlete_profile_id`, `check_in_date`,
`rpe`, `overall_feeling`, `pain_status`. `.upsert()` is prohibited.

**8. Creation race.** If the `INSERT` loses a creation race with SQLSTATE `23505`,
retry the same scoped `UPDATE` exactly once. No branching on raw error-message
text. Concurrent edits are last-completed-write-wins; this task adds no version
history, conflict UI, or audit history.

**9. Routing.** The slice is available only through the existing active-athlete
route. Pending, revoked, unauthenticated, coach-only, and otherwise unauthorized
users gain no self-data route through this task.

**10. Online-only.** No persisted draft, no outbox, no optimistic health cache, no
automatic retry of health-bearing mutations, no health values in logs, analytics,
crash context, session replay, notifications, or storage outside the approved
server row, and no raw error shown to users.

## Domain contract

A check-in is represented only when all three values pass strict runtime
validation:

- `rpe` — integer, `0` through `10`
- `overall_feeling` — integer, `1` through `5`
- `pain_status` — exactly `none` or `present`

Malformed, null, missing, out-of-range, fractional, and unknown server values are
rejected. The failure is closed and produces a fixed sanitized application error.
Invalid values are never silently coerced. A partially valid server row is never
displayed or cached.

## Repository contract

**Load.** Accepts the verified authenticated user id and the captured local date
explicitly. Queries only the row for that user and date. Selects only `rpe`,
`overall_feeling`, `pain_status`. Returns one fully validated domain check-in, or
`null` when no row exists. A query error is not an empty result. Internal failures
become fixed sanitized errors before crossing the repository boundary.

**Save.** Accepts the verified user id, the captured local date, and a complete
input that it re-validates. Never obtains or trusts an athlete id from UI input.
Performs the decision-7 algorithm. Scopes every write to the verified user and the
exact captured date. Updates only the three mutable health columns. Inserts only
the five approved columns. Returns no health-bearing row. Handles only SQLSTATE
`23505` as the insert-race case and then retries the scoped update once. Any other
failure, and an impossible retry result, becomes a fixed sanitized error. Raw
errors and payloads are never logged.

## Query contract

- Add `authScopedKeys.dailyCheckIn(userId, localDate)`.
- The key contains the user id and the local date and no health value.
- It keeps the shared `AUTH_SCOPE` prefix, so it stays covered by
  `clearAuthScopedQueries`.
- A mutation captures the exact key/date it used and invalidates that exact key
  after success.
- No optimistic update for the health values.
- No automatic mutation retry.

## Date rollover

The device-local date is recalculated immediately before submission. If the local
calendar date or the timezone offset changed since the form/query was created, the
answers are not written to the stale date; the check-in is reset and refreshed
against the new local date, and fixed non-sensitive feedback asks the user to
review the current-day form again. Rollover is never resolved through UTC
conversion.

## UI requirements

A concise explanation of the daily check-in; RPE choices `0`–`10`; five
overall-feeling choices; two pain-status choices; no default selections; clear
selected states; accessible labels and selected/disabled/busy state; save disabled
until all three fields are selected; loading feedback; a load-error state with a
deliberate retry action; an empty state; an existing-row prefill/edit state; a
save-busy state preventing duplicate submission; sanitized success feedback;
sanitized error feedback; and fixed non-diagnostic pain safety copy. No database
terminology and no raw error is exposed to the athlete.

## Acceptance criteria

All met, re-checked against the Round 2 evidence. Evidence per criterion is
tabulated in `docs/app/handoffs/TASK-013.md`.

Round 2 strengthened criteria 5, 6, 8, and 10 in particular:

- **10** — the highest-severity Round 1 defect was found here: the mutation
  inherited TanStack's default `networkMode: "online"`, which paused an offline
  write and held the three health values in memory for automatic execution on
  reconnect. That in-memory outbox is gone; the mutation declares
  `networkMode: "always"` and its offline behaviour is proved with a positive
  control.
- **5** — the exact auth-scoped key is now captured before the write and
  invalidated from the returned value, so replacing a pending mutation's options
  cannot redirect the invalidation to another account.
- **6** — every unexpected throw or rejection from the client is now sanitized,
  not only resolved `{ error }` responses.
- **8** — an offset-only rollover now refreshes and rehydrates the same calendar
  date, so the form can no longer claim today was checked in while the controls
  sit empty.

Criterion 12 still carries one pre-existing `expo-doctor` patch-version finding
that lies outside the owned paths and is reported rather than fixed.

- [x] 1. An authenticated active athlete can load today's check-in from Athlete
      Today.
- [x] 2. No existing row produces an empty form with no default health answers.
- [x] 3. A valid complete form can create today's row.
- [x] 4. A valid complete form can update today's existing row.
- [x] 5. Every read and write is scoped to the verified user and the exact
      device-local date.
- [x] 6. Invalid server rows fail closed.
- [x] 7. Insert races follow the approved `23505` retry behaviour.
- [x] 8. Date/timezone rollover cannot silently write answers to a stale date.
- [x] 9. Pending, revoked, unauthenticated, and non-athlete routing behaviour is
      not weakened.
- [x] 10. Health data is not logged, placed in analytics, persisted as a draft,
      added to query keys, or printed in test/handoff failure output.
- [x] 11. No migration, RLS, generated type, dependency, lockfile, shared theme,
      or out-of-scope file change.
- [x] 12. Relevant local verification passes, with one pre-existing
      `expo-doctor` patch-version finding that lies outside the owned paths and
      is reported rather than fixed.
- [x] 13. Documentation matches the implementation.
- [x] 14. Git ends clean with the work committed on the task branch.
- [x] 15. Nothing is merged, pushed, deployed, remotely migrated, or cleaned up.

## Privacy classification

**Protected health data.** `rpe`, `overall_feeling`, and `pain_status` are
protected health values under `AGENTS.md`, and the verified user id plus
`check_in_date` make them attributable. This is the first task in the product that
handles protected health data in application code.

Development and tests use synthetic fixtures only. No real athlete name, address,
or measurement is used, read, or written.

## Negative and failure-path test matrix

Existing dependencies only. Pure-logic and repository-level tests; no component
renderer and no new dependency.

| # | Case | Expected |
| --- | --- | --- |
| 1 | local date formatting, including a local date that differs from the UTC date | manual `YYYY-MM-DD` from local parts, both ahead of and behind UTC |
| 2 | valid domain values at every boundary | accepted |
| 3 | null, missing, fractional, out-of-range, non-numeric, and unknown values | rejected, fail closed |
| 4 | load with no row | `null` |
| 5 | load with a row | validated domain value |
| 6 | load error | sanitized error, never an empty result |
| 7 | load query scoping | filtered to the exact verified user and exact date |
| 8 | save with an invalid input | sanitized error, zero client calls |
| 9 | existing row | one scoped `UPDATE`, no `INSERT` |
| 10 | missing row | scoped `UPDATE` then the five-column `INSERT` |
| 11 | `INSERT` fails `23505` | exactly one additional scoped `UPDATE`, success |
| 12 | `INSERT` fails with a non-`23505` code | no retry |
| 13 | retry `UPDATE` matches nothing | sanitized error |
| 14 | written columns | update names exactly the three health columns; insert names exactly the five approved columns |
| 15 | write responses | repository returns no health-bearing row |
| 16 | query key | contains the user id and the date, no health value |
| 17 | rollover | a stale captured date or changed offset blocks the write and resets the form |
| 18 | fixed errors | no raw Supabase/database message, code, hint, or detail reaches the user-facing message |
| 19 | mutation retry | disabled |
| 20 | health leakage | no health value logged, persisted as a draft, or placed in a query key |
| 21 | `.upsert()` | never used |

### Failure-output safety

Health literals may be synthetic, but a failing assertion must not print a
health-bearing payload.

- Assertions on repository calls and health-bearing objects are reduced to
  booleans, counts, fixed field-name lists, or other non-health diagnostics
  **before** reaching the assertion.
- Whole health-bearing request/response objects are never compared or snapshotted.
- Raw captured errors and payloads never appear in assertion messages.
- Mock calls containing health values are never printed.
- No snapshot contains a health value.

Test failures and the handoff may report assertion names and counts, never the
underlying health payloads.

## Verification

Inspect the package scripts and use the repository's canonical commands. Run from
`platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm --filter @run-performance/mobile exec vitest run src/features/check-in src/lib/query
corepack pnpm dlx expo-doctor@latest
corepack pnpm --filter @run-performance/mobile exec expo export --platform web
```

Local database only, with every credential-bearing stream suppressed:

```powershell
corepack pnpm db:start *> $null
"start exit: $LASTEXITCODE"

corepack pnpm exec supabase db reset --local --no-seed
corepack pnpm exec supabase test db --local
corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning

corepack pnpm db:stop *> $null
"stop exit: $LASTEXITCODE"

(docker ps -a --filter 'name=supabase_' --format '{{.Names}}' | Measure-Object -Line).Lines
```

Repository checks:

```powershell
git diff --check
git status --short
git diff --name-only
```

`*> $null` redirects every PowerShell stream, so the API URL, anon key,
service-role key, JWT secret, and database URL printed by `supabase start` and
`supabase stop` never reach the terminal, the transcript, or a log. Never run bare
`supabase start`, `supabase stop`, `supabase status`, or `db:status` while a
transcript is capturing output, and never run any command with `--linked` or a
remote database URL. The container check is **count-only**; container environment
variables are never inspected or printed.

Report only sanitized exit codes, test-file counts, assertion counts, and safe
fixed summaries.

If a verification command fails: diagnose only within the owned scope; do not
weaken tests; do not broaden the task; do not print raw health-bearing or
credential-bearing output; stop and report if the correction requires an unowned
path.

## Prohibited operations

For the duration of this task, none of the following happens:

- merge, push, deploy, or publish;
- `supabase link`, `db push`, any remote migration, or any hosted Supabase
  contact;
- printing `supabase status` output or any credential-bearing stream;
- removing the worktree or deleting any branch;
- modifying the main repository checkout;
- transferring ownership, or asking Codex to edit implementation files;
- using AGY;
- creating a second worktree.

Work stops after committing and producing the handoff for Codex read-only review.

## Dependencies and open decisions

- Depends on the TASK-012 contract at base SHA `9784854`, which is settled and
  merged into `feat/mobile-foundation`, not a moving dependency.
- No open decision. Decisions 1–10 are approved as recorded above.

## Required handoff

`docs/app/handoffs/TASK-013.md`, in the canonical format from
`docs/app/AI-WORKING-AGREEMENT.md`, recording task and ownership, branch/worktree,
approved base SHA, final commit SHA(s), changed files, acceptance-criteria result,
sanitized commands and results, test counts, privacy/security impact,
confirmation that fixtures are synthetic, known limitations, rollback
instructions, remaining reviewer questions, and explicit confirmation that nothing
was merged, pushed, deployed, linked, remotely migrated, or cleaned up.

No health-bearing payload, raw error, credential, credential-bearing URL, or
status output appears in the handoff.

## Rollback

TASK-013 delivers documentation **plus additive mobile application code and
tests**: a new `platform/apps/mobile/src/features/check-in/` module, one added
key in `lib/query/keys.ts`, and one edit to `app/athlete/index.tsx` that replaces
the check-in placeholder card with the real inline card.

The change is additive rather than documentation-only, but it is still fully
reversible with Git alone. Nothing outside those owned paths was touched: no
migration, RLS policy, grant, generated type, dependency, lockfile, configuration,
shared component, or theme token. The task branch is separate from
`feat/mobile-foundation` and nothing is merged, so rollback needs no remote or
database action:

```powershell
# discard one commit on the task branch, keeping the changes staged
git reset --soft HEAD~1

# discard the whole task, returning the branch to the approved base
git reset --hard 9784854a691e8a5aa22fc0e299783a751c8adce1

# or simply abandon the branch; feat/mobile-foundation is untouched
```

No migration was added, so no database rollback exists or is required, and the
TASK-012 contract this task consumes is unaffected by any of the commands above.
The local database is rebuilt with `supabase db reset --local --no-seed` if a
verification run left it dirty.

Reverting `platform/apps/mobile/src/app/athlete/index.tsx` alone removes the card
from the screen while leaving the feature module in place but unreachable, which
is the smallest useful rollback if the slice needs to be withdrawn without
discarding the work.
