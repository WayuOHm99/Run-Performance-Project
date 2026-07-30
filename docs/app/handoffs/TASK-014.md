# TASK-014 Handoff — Athlete Check-in Sharing Controls Mobile

Status: Round 2 finding fixed and verified locally. **Awaiting GPT/Codex
read-only Round 2 review.**

GPT/Codex reviewed Round 1 and raised **one Medium** finding — cross-account
mutation observer state. The Product Owner approved it and it is **fixed**; see
"Round 2 — Codex finding and fix" at the end of this document, which carries the
reproduction, the implementation, the lifecycle regression, the mutation evidence,
and the commit SHA.

The Round 1 record below is retained as written. Where Round 2 supersedes a Round 1
figure or claim, the correction is made in place with the earlier value noted, and
the superseded text is not silently rewritten.

Round 2 changed no database contract, no dependency, and no file outside the
already-owned paths. A gap found in this task's own Round 2 mutation testing — one
mutation initially escaping detection — is recorded in full rather than quietly
corrected.

One process correction is recorded in full rather than quietly fixed: Codex
inspected the worktree mid-task and correctly found the implementation still
uncommitted, the packet still marked "not yet implemented", and no handoff
present. See "Process correction" below.

```text
Task:              docs/app/tasks/TASK-014-athlete-check-in-sharing-controls-mobile.md
Writer:            Claude Code (sole writer)
Branch/worktree:   feat/TASK-014-athlete-check-in-sharing-controls-mobile
                   .claude/worktrees/task-014-athlete-check-in-sharing-controls-mobile
Commit SHA:        see the commit ledger below
Changed files:     21 against the approved base
Acceptance:        19 of 19 satisfied
Commands run:      format:check, lint, typecheck, focused Vitest, full Vitest,
                   expo-doctor, expo web export, supabase db reset/test/lint,
                   git diff --check, changed-file audit
Privacy/security:  consent metadata and team names only; no health measurement
Known limitations: 8 recorded
Rollback:          git revert the three TASK-014 commits; additive and file-scoped
Reviewer findings: none yet — this is Round 1
```

The block above is the Round 1 record, retained as written. The current state of the
task is:

```text
Task:              docs/app/tasks/TASK-014-athlete-check-in-sharing-controls-mobile.md
Writer:            Claude Code (sole writer)
Branch/worktree:   feat/TASK-014-athlete-check-in-sharing-controls-mobile
                   .claude/worktrees/task-014-athlete-check-in-sharing-controls-mobile
Commit SHA:        2929bf76f049e2f1fefc23d6e844c87311b67b3c (Round 2 fix)
                   full ledger in "Round 2 commit ledger"
Changed files:     23 against the approved base (21 in Round 1, 6 touched in
                   Round 2 of which 2 are new)
Acceptance:        19 of 19 satisfied; criterion 11 extended in Round 2
Commands run:      format:check, lint, typecheck, focused Vitest (146), full
                   Vitest (614), expo web export, git diff --check, changed-file
                   and forbidden-path audits. The local database stack was not
                   started in Round 2 — the database contract is unchanged and the
                   Round 1 pgTAP evidence stands.
Privacy/security:  consent metadata and team names only; no health measurement.
                   Round 2 reduces exposure: the previous account's user id, team
                   id, and query key are no longer reachable from observer state.
Known limitations: 10 recorded (8 from Round 1, 2 added in Round 2)
Rollback:          git revert the four TASK-014 commits; additive and file-scoped
Reviewer findings: Round 1 Medium "cross-account mutation observer state" — fixed
                   in 2929bf7. No finding outstanding.
```

## Task and ownership

- Task packet: `docs/app/tasks/TASK-014-athlete-check-in-sharing-controls-mobile.md`
- Writer: **Claude Code** (sole writer)
- Reviewer: **GPT/Codex, read-only.** No reviewer edited any implementation file.
- AGY: **not used.**
- Ownership was not transferred at any point.
- The Product Owner approved the complete scope and the product/security
  decisions 1–10 before implementation started. That approval is recorded in the
  packet, which was committed **before** the first application-code edit.

## Branch and worktree

- Worktree: `.claude/worktrees/task-014-athlete-check-in-sharing-controls-mobile`
  (isolated, **preserved** for the reviewer, still locked)
- Branch: `feat/TASK-014-athlete-check-in-sharing-controls-mobile`
- Source branch: `feat/mobile-foundation`
- Approved base SHA: `3b94742c3a5f28f82e8583b29957159fce9343a2`
- Worktree clean at handoff.

The automatic worktree branch
`worktree-task-014-athlete-check-in-sharing-controls-mobile` was renamed to the
task branch name with `git branch -m`. No other branch was created, moved, or
deleted, and no second worktree was created.

### Pre-flight, confirmed before the first edit

| Gate                                                  | Result                                             |
| ----------------------------------------------------- | -------------------------------------------------- |
| worktree clean                                        | yes, `git status --porcelain` empty                |
| `HEAD` is the approved base                           | `3b94742c3a5f28f82e8583b29957159fce9343a2` exactly |
| the base is the approved `feat/mobile-foundation` tip | yes; the branch resolves to the same SHA           |
| the base is an ancestor of the task branch            | yes, `git merge-base --is-ancestor` exit 0         |
| the intended task branch already exists elsewhere     | no, `refs/heads/feat/TASK-014-…` absent            |
| renaming would overwrite or conflict                  | no, the target name was unused                     |
| main checkout modified                                | no                                                 |

`feat/mobile-foundation` and the base SHA are the same commit, so the TASK-011
consent contract and the TASK-013 check-in slice consumed here are both present
in the base and are settled dependencies.

No protected legacy path was read or written. No root `CLAUDE.md`, `athletes/`,
`team_data/`, `garmin/`, `scripts/`, or root `supabase/` file was accessed, and
no recursive search was run from the repository root.

### Commit ledger

| Commit                                       | Purpose                                                          | Changed files |
| -------------------------------------------- | ---------------------------------------------------------------- | ------------- |
| `0974b43eba0836018b0c8e3957738c24eaf5715f`   | approved task packet, committed before any application-code edit | 1             |
| `107bea825a10a7b97917b1d9aa41d5f390c2900d`   | implementation and tests                                         | 19            |
| branch HEAD                                  | this handoff and the packet closeout                             | 2             |
| **Complete TASK-014 diff against `3b94742`** |                                                                  | **21**        |

No commit was amended, rebased, squashed, or rewritten. The packet commit
`0974b43` is untouched by the later commits.

## Changed files

Nineteen in the implementation commit, all inside the owned paths.

New, under `platform/apps/mobile/src/features/sharing/`:

| File                         | Responsibility                                                               |
| ---------------------------- | ---------------------------------------------------------------------------- |
| `domain.ts`                  | the `check_in` constant, fail-closed validation, the branded `SharingTarget` |
| `errors.ts`                  | sanitized `load`/`grant`/`revoke` failures from fixed tables                 |
| `sharing-repository.ts`      | the two scoped reads and the two approved RPCs                               |
| `action-plan.ts`             | the press decision: refuse while busy, direction from loaded state           |
| `query-options.ts`           | the auth-scoped key, `networkMode`, `retry`, the captured-key refetch        |
| `use-check-in-sharing.ts`    | binds the above to the verified identity and query client                    |
| `copy.ts`                    | every user-facing string and the two accessible-label builders               |
| `sharing-section.tsx`        | the Profile/Me section and all display states                                |
| `sharing-action-button.tsx`  | the per-team control, carrying its own accessible label                      |
| `failure-probe.ts`           | test support; reduces a rejection to a safe vocabulary                       |
| `domain.test.ts`             | validation and composition                                                   |
| `sharing-repository.test.ts` | reads, RPCs, and every failure shape                                         |
| `query-options.test.ts`      | key, cache rules, offline, replaced options                                  |
| `action-plan.test.ts`        | busy and unknown-team refusals                                               |
| `source-safety.test.ts`      | AST structural guards                                                        |
| `logging.test.ts`            | runtime console silence                                                      |

Modified:

| File                                              | Change                                                                                   |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `platform/apps/mobile/src/app/profile.tsx`        | renders `CheckInSharingSection` between the name form and sign-out; doc comment extended |
| `platform/apps/mobile/src/lib/query/keys.ts`      | adds the `checkInSharing` auth-scoped key                                                |
| `platform/apps/mobile/src/lib/query/keys.test.ts` | adds coverage for that key                                                               |

**Not changed**, confirmed by an exact audit against the base: every file under
`platform/supabase/`, `platform/apps/mobile/src/lib/supabase/database.types.ts`,
`platform/package.json`, `platform/apps/mobile/package.json`,
`platform/pnpm-lock.yaml`, `features/check-in/**`, `features/auth/**`,
`features/profile/**`, `components/**`, `theme/**`, `lib/query/client.ts`,
`test-support/**`, `app/_layout.tsx`, and every other route file.

## What was implemented

An athlete opening Profile/Me now sees a "Daily Check-in sharing" section: what
the check-in contains, that consent goes to the **team** and covers coaches who
join later, that the default is off, and then one card per active athlete team
with its team name, its current server-confirmed state, and an explicit
"allow team to view" or "stop sharing" button.

The database contract is consumed unchanged. Grant goes through
`grant_team_data_sharing(p_team_id, 'check_in')`, revoke through
`revoke_team_data_sharing(p_team_id, 'check_in')`, and the reads go through the
existing `team_memberships`, `teams`, and `sharing_grants` policies.

### Two design points that differ from the obvious reading of the contract

Both are deliberate and are the main thing to review.

1. **There is no `onSuccess`.** The contract asks that an identity change during
   an in-flight mutation must not redirect invalidation. TanStack swaps a pending
   mutation's options on rerender, so a settle-time callback belonging to a
   _later_ render is the one that runs. Rather than guard that, the callback was
   removed: `mutationFn` is read once when execution begins, so the key it
   captures before the write and the refetch it awaits after the write both
   belong to the identity the write was made as. The options object is exactly
   `{ mutationFn, networkMode, retry }`. The mid-flight replacement test proves
   the replacement identity is never written to and never refreshed.
2. **A failed refresh does not fail a successful action.** If the RPC succeeded
   and the refetch then failed, reporting the action as failed would tell the
   athlete "ยังไม่ได้เริ่มแชร์" — sharing is still off — when it is on. The
   refetch rejection is therefore swallowed inside `mutationFn`; the query owns
   its own error state and the section shows the load error with its retry.

### Fail-closed loading

The load rejects the **whole** list rather than rendering a valid subset, because
a dropped grant row reads as "not sharing", which silently understates what the
coach can see. Rejected: a non-array response, a malformed membership or grant
row, an unexpected role/status/category, a missing or inaccessible team name, a
duplicate team in either response, and an active grant naming a team the caller
holds no active athlete membership in.

The membership read runs **before** the grant read on purpose. The reverse order
would let a membership activated between the two reads produce a grant with no
matching membership, which the validation refuses. The residual window in the
chosen order shows one retryable error rather than a wrong list.

### Write-target safety

`SharingTarget` is branded with a module-private `unique symbol`, and
`resolveSharingTarget` is its only producer. A team id that is not in the
successfully loaded list yields `null` and no RPC is attempted. Neither write
function accepts an athlete id — the athlete is `auth.uid()` inside the RPC — and
a grant counts as successful only when the expected non-health sentinel, the
grant row id, arrives in UUID shape.

## Acceptance criteria

All 19 are satisfied; the packet carries the per-criterion evidence mapping.
Summarized:

| #   | Criterion                                     | Evidence                                                                                            |
| --- | --------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 1   | every active athlete team by name             | embedded `teams(name)`; a missing name is refused                                                   |
| 2   | independently server-confirmed state per team | per-team composition; both cross-team directions asserted                                           |
| 3   | missing grant means off, creates nothing      | `SELECT`-only load; no write on any load path                                                       |
| 4   | grant RPC, selected team, constant category   | RPC name, argument keys, team, and category asserted                                                |
| 5   | revoke RPC, same scope                        | same assertions                                                                                     |
| 6   | Team A action does not change Team B          | asserted in four modules                                                                            |
| 7   | refetched, no optimistic update               | options are exactly three keys; refetch awaited in `mutationFn`                                     |
| 8   | load failure is an error, not off/empty       | 17 failure cases raise a sanitized `load` error                                                     |
| 9   | malformed/inconsistent rows fail closed       | 49 rejection cases                                                                                  |
| 10  | identity from verified auth state             | only `useAuth`; 5 non-identity values refused pre-query                                             |
| 11  | replacement identity cannot redirect          | `MutationObserver.setOptions` mid-flight                                                            |
| 12  | offline not paused/queued/retried             | plus a positive control proving the default _would_ pause                                           |
| 13  | duplicate presses produce one operation       | `planSharingAction` refuses while busy, same team and other teams                                   |
| 14  | revoked membership loses its control          | control, write target, and press all refused; grant revocation is the TASK-011 trigger, still green |
| 15  | nothing logged/persisted/leaked               | AST scan, runtime console silence, leak scan reporting 0                                            |
| 16  | no db/type/dep/lockfile/nav/theme change      | exact changed-file audit; web export still 13 routes                                                |
| 17  | existing suites still pass                    | 596 workspace tests; 5 pgTAP files, 583 assertions                                                  |
| 18  | docs match, Git clean                         | this handoff; `git status --short` empty                                                            |
| 19  | nothing merged/pushed/deployed                | confirmed below                                                                                     |

## Negative tests

Every case the packet required is covered. Counts are safe aggregates.

| Case                                                        | Where                                                                                                       |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| no authenticated identity                                   | repository (5 non-identity values, no query issued) and mutation options                                    |
| coach-only user                                             | a `role: "coach"` row is refused; an empty list is the honest empty state                                   |
| revoked athlete membership                                  | a `status: "revoked"` row is refused; a team that stops being returned loses its control, target, and press |
| forged / unowned team id                                    | `resolveSharingTarget` (9 candidates), mutation options (3 cases)                                           |
| category cannot vary from `check_in`                        | RPC category asserted; `workout_summary`/`sleep_summary` refused on read; AST literal rule                  |
| another athlete's grants never enter                        | grant read filtered to the caller, asserted privately both ways                                             |
| Team A grant leaves Team B unchanged                        | domain, repository, mutation options                                                                        |
| Team A revoke leaves Team B unchanged                       | domain, repository                                                                                          |
| duplicate grant remains one active state                    | idempotent repeat asserted; the DB partial unique index is the authority                                    |
| repeat revoke is safe                                       | `null` return treated as the confirmed off state                                                            |
| membership / team / grant query error is not empty or off   | 17 repository failure cases                                                                                 |
| missing team name                                           | 10 team-embed rejection cases                                                                               |
| malformed team / membership / category / grant row          | 49 domain rejection cases                                                                                   |
| synchronous throw, rejected query, rejected RPC             | covered for load, grant, and revoke                                                                         |
| raw `message`, `details`, `hint`, `cause` discarded         | probe reports `messageIsFixed`, `withoutCause`, and safe field names only                                   |
| duplicate press while busy                                  | `action-plan.test.ts`                                                                                       |
| offline immediate attempt, no pause, no reconnect execution | `query-options.test.ts`                                                                                     |
| positive control: default would pause                       | `query-options.test.ts`                                                                                     |
| retry remains zero                                          | asserted as an option and behaviourally against a client default of 3                                       |
| no optimistic cache write                                   | option-key list; AST rule for `onMutate`/`setQueryData`                                                     |
| pending options replaced by another identity                | `query-options.test.ts`                                                                                     |
| revoked membership disappears after refetch                 | domain, action plan, mutation options                                                                       |
| failing assertions emit only safe values                    | see below                                                                                                   |

## Failure-output safety

Sharing metadata is not a health measurement, but it is sensitive authorization
data and was treated as such throughout.

- Team ids are reduced to the fixed case labels `A`, `B`, `C`, or `unknown`
  before any assertion, so a forged or unexpected id prints as `unknown`.
- A parsed list is reduced to strings like `A:on`; a rejection to the single word
  `rejected`.
- Query keys are reduced to `auth-scoped|owner-a|check-in-sharing|3` — fixed
  literals, an owner _label_, and a length.
- Team names, filter values, and RPC arguments are compared inside private
  helpers (`namesMatch`, `filtersMatch`, `rpcArgsMatch`) that return booleans.
- The client double records **names only**: a filter as `profile_id`, never
  `profile_id=<value>`; an RPC as its function name and its argument _keys_.
- Rejections go through the local `failure-probe.ts`, which never rethrows and
  never passes a captured value to `expect`. `.rejects.toThrow` is used nowhere,
  because it prints the received error on a mismatch.
- Sets of cases are asserted as lists of **case names**.
- `src/test-support/capture-error.ts` was deliberately **not** used: it rethrows a
  value that is not the expected class, which would let a raw PostgREST error be
  reported and printed. That file is not owned by this task, so a local probe was
  written instead.
- All identifiers and names are synthetic. Team names are `Alpha/Beta/Gamma
Runners`; ids are structured synthetic UUIDs.

## Commands run and results

From `platform/` unless noted. No output containing a credential was printed.

| Command                                                                                                 | Result                                                                           |
| ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `corepack pnpm install --frozen-lockfile`                                                               | exit 0, already up to date, lockfile unchanged                                   |
| `corepack pnpm format:check`                                                                            | exit 0, all files match Prettier style                                           |
| `corepack pnpm lint`                                                                                    | exit 0, no ESLint output                                                         |
| `corepack pnpm typecheck`                                                                               | exit 0, `tsc --noEmit` clean                                                     |
| focused Vitest (`src/features/sharing`, `src/lib/query/keys.test.ts`)                                   | **7 files, 128 tests, all passing**                                              |
| `corepack pnpm test`                                                                                    | **33 files, 596 tests, all passing**                                             |
| `corepack pnpm dlx expo-doctor@latest` (from `apps/mobile/`)                                            | 20 of 21 checks pass; the one failure is pre-existing — see "Known limitations"  |
| `corepack pnpm exec expo export --platform web` (from `apps/mobile/`)                                   | exit 0, 34 output files, **13 static routes — unchanged, so no route was added** |
| `corepack pnpm db:start *> $null`                                                                       | exit 0, 10 containers                                                            |
| `corepack pnpm exec supabase db reset --local --no-seed`                                                | exit 0                                                                           |
| `corepack pnpm exec supabase test db --local`                                                           | exit 0, **5 files, 583 assertions, `Result: PASS`, 0 failures**                  |
| `corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0, 0 warnings                                                               |
| `corepack pnpm db:stop *> $null`                                                                        | exit 0, **0 remaining containers**                                               |
| `git diff --check`                                                                                      | clean                                                                            |
| changed-file audit                                                                                      | 21 files, all inside the owned paths                                             |
| `git status --short`                                                                                    | empty                                                                            |

The database suite was run because this feature depends on the existing TASK-011
RPC and RLS contract. It confirms that contract is intact and that TASK-014
changed nothing in it: `platform/supabase/` and the generated types were verified
byte-identical to the base after the reset.

`supabase status` and `db:status` were never run. `db:start` and `db:stop` used
`*> $null`, which redirects every PowerShell stream, so the API URL, anon key,
service-role key, JWT secret, and database URL never reached the terminal or this
transcript. No `--linked`, project ref, remote URL, service-role credential, or
production data was used at any point.

## Mutation evidence

Twelve reversible source mutations, applied **one at a time**. For each: the file
was hashed, mutated, verified changed, the focused suite was run with output
captured to a file that was never printed, the file was restored from the backup,
and the restored hash was compared to the original. Every restore was
byte-identical.

| Mutation                                                            | Failing tests | Files | Output leak count | Restored |
| ------------------------------------------------------------------- | ------------- | ----- | ----------------- | -------- |
| remove `networkMode: "always"`                                      | 4             | 1     | 0                 | yes      |
| enable mutation retry (`retry: 3`)                                  | 2             | 1     | 0                 | yes      |
| move the refresh into a swappable `onSuccess` that rebuilds the key | 6             | 1     | 0                 | yes      |
| treat a membership-read failure as an empty list                    | 2             | 1     | 0                 | yes      |
| let the grant category vary from `check_in`                         | 4             | 2     | 0                 | yes      |
| add optimistic state (`onMutate`)                                   | 2             | 2     | 0                 | yes      |
| let a raw thrown error escape the load                              | 2             | 1     | 0                 | yes      |
| weaken cross-team independence                                      | 3             | 2     | 0                 | yes      |
| skip a malformed membership row instead of failing closed           | 3             | 2     | 0                 | yes      |
| skip a malformed grant row instead of failing closed                | 3             | 2     | 0                 | yes      |
| accept any grant response instead of the sentinel                   | 1             | 1     | 0                 | yes      |
| accept a forged team id as a write target                           | 6             | 2     | 0                 | yes      |

Every mutation was detected. No mutation survived, so no defect was found in this
task's own tests by mutation testing.

The "output leak count" column is a scalar produced by scanning the captured
runner output programmatically for synthetic team ids, user ids, grant ids, team
names (`Alpha/Beta/Gamma Runners`), and raw server message fragments
(`permission denied`, `active athlete membership required`,
`sharing_grants_select_own_history`, `p_team_id`). Every scan returned **0**, so
no failing assertion printed a sensitive value even while nine of the twelve
mutations were producing genuine failures. The captured output itself was
discarded and never printed.

After the last restore, the unmutated suite was re-run: 128 focused and 596
workspace tests pass.

## Privacy and security impact

- **No health measurement is read, transported, cached, or logged by this
  feature.** The three protected check-in values — RPE, overall feeling, and
  pain-presence status — are named only in explanatory Thai copy, so consent is
  informed. Naming a field is not disclosing a value.
- The data actually handled is consent metadata plus a team name: a team id, a
  team name, a role, a status, a category name, and whether an active grant
  exists. That is PII and authorization-relevant, and gets the same discipline.
- Nothing logs. Proved twice: an AST scan finds no `console`/`Sentry`/analytics
  identifier in any owned runtime file, and a runtime suite counts console calls
  across the pure paths, a refused read, a raw rejection, a refused grant, a
  refused revoke, and an action refused before any request — zero in every case.
- Nothing persists. No `AsyncStorage`, `SecureStore`, `expo-file-system`, or
  query persister is imported or referenced; the cache stays memory-only and
  auth-scoped, and `clearAuthScopedQueries` drops the new entry outright on an
  identity change.
- No server error text reaches the user. Every failure is classified from
  `code`/`status`/constructor name only, and the message shown comes from a fixed
  Thai table. No raw `message`, `details`, `hint`, `cause`, payload, row, or RPC
  argument is retained on the error handed to React Query. The repository's
  source is scanned to confirm it never even names those fields.
- No raw team id, database wording, SQLSTATE, policy name, RPC name, or column
  name appears in user-facing copy. A team is always named; a team with no
  visible name is a refusal, not a row labelled with its identifier.
- The UI supplies no athlete id, and neither RPC accepts one. The athlete is
  `auth.uid()` inside the function, so a forged owner is not expressible.
- Failure wording never implies a state change that did not happen: a failed
  grant says sharing was not started, a failed revoke says it was not stopped.
- All fixtures are synthetic. No real athlete name, email, measurement, token, or
  credential was introduced anywhere, including in tests and this handoff.
- No new dependency, so no new supply-chain surface.

## Known limitations

1. Sharing is per team by TASK-011 decision 1. An athlete cannot exclude one
   coach of a team they have consented to; leaving the team or revoking the
   category is the only control.
2. There is still no client-reachable path to create teams or memberships, so an
   athlete with no membership sees the empty state, and the grant flow can only
   be exercised end to end against trusted fixtures until a
   membership-administration task exists. **This slice has therefore not been
   driven against a live signed-in athlete with a real active membership.**
3. Only `check_in` is controllable. `workout_summary` and `sleep_summary` grants
   exist in the database and have no UI, by decision 2.
4. No consent-history view, so the athlete cannot see when they previously
   granted or revoked. The history is retained in the database.
5. Online-only by decision 8. There is no offline affordance beyond a visible
   failure and a new deliberate press.
6. The load fails closed when a returned active grant names a team that is not in
   the caller's active athlete membership list. Safe direction, but a membership
   activated between the two reads shows one retryable error rather than a partial
   list.
7. The section renders its loading state while no identity exists. The route is
   gated upstream, so this is unreachable in the running app, but it is not
   defended in the component itself.
8. `expo-doctor` reports one **pre-existing** failure unrelated to this task:
   installed `expo` 56.0.17 and `expo-router` 56.2.16 are behind the SDK's
   current `~56.0.18` and `~56.2.17`. TASK-014 owns no dependency manifest and no
   lockfile, and all three files were confirmed byte-identical to the approved
   base, so this was reported rather than fixed. It needs a separate dependency
   task with a serial owner for the lockfile.

## Process correction

The task instructions required the packet to be committed before application-code
work, which was done (`0974b43`), and the implementation to be committed before
stopping for review, which initially was **not**.

Codex inspected the worktree read-only partway through and correctly reported
that `HEAD` was still the packet commit, the implementation was
modified/untracked, the packet still said "Approved, not yet implemented", no
handoff existed, and the worktree was not clean. That report was accurate.

The cause was sequencing, not lost work: verification and mutation testing were
run against the dirty tree and the commit had not yet been made. Nothing was
discarded or reset. Before continuing, the dirty state was audited and confirmed
to be exactly TASK-014 work — three modified owned files, all additive, plus
sixteen new files under the owned `features/sharing/` directory — with no
unrelated user change, no protected legacy path, no database file, and no
dependency or lockfile change. The full verification suite was then re-run on the
restored, unmutated tree before committing.

## Rollback

The task is additive and file-scoped. To roll back:

1. `git revert` the three TASK-014 commits, **or** delete
   `platform/apps/mobile/src/features/sharing/`, this handoff, and the packet,
   and restore `platform/apps/mobile/src/app/profile.tsx`,
   `platform/apps/mobile/src/lib/query/keys.ts`, and
   `platform/apps/mobile/src/lib/query/keys.test.ts` from
   `3b94742c3a5f28f82e8583b29957159fce9343a2`.

No migration, generated type, dependency, lockfile, or configuration file was
touched, and nothing was applied to a remote database, so **no database and no
remote rollback exists or is needed**. The local stack was reset and stopped and
holds only what `db reset` produced from the committed migrations.

## Explicit confirmations

- Nothing was **merged**.
- Nothing was **pushed**.
- Nothing was **deployed** or published.
- No hosted Supabase project was **linked**; no project ref, remote URL, or
  service-role credential was used.
- No **remote migration** and no `db push` was run.
- No branch was deleted; no worktree was removed. The worktree is preserved and
  still locked for the reviewer.
- The **main checkout was not modified**. All work happened in the isolated
  worktree.
- **AGY was not used.**
- No protected legacy path was accessed.
- No real athlete data, credential, or token was used.
- No commit was amended, rebased, squashed, or rewritten.

## Remaining reviewer questions

1. **Is removing `onSuccess` entirely the right reading of the invalidation
   contract?** The packet says to capture the key before awaiting the write and
   not to let an identity change redirect invalidation. Awaiting the refetch
   inside `mutationFn` satisfies both and leaves nothing swappable, but it means
   the mutation's own success is gated on a refresh round trip. Confirm this is
   preferred over keeping an `onSuccess` that invalidates the returned key.
2. **Is swallowing a refetch rejection acceptable?** The alternative reports a
   successful consent change as failed, which is a worse lie. `invalidateQueries`
   does not reject in practice, so this is defence against an injected function.
3. **Is failing the whole list closed too aggressive for the "active grant with
   no active membership" case?** It is the safe direction and the TASK-011 trigger
   should make the state impossible, but a membership activated between the two
   reads produces one retryable error. An accepted alternative would be to ignore
   such a grant, which risks understating coach access.
4. **Should the section defend against the no-identity state itself** rather than
   relying on the upstream route gate, given it currently shows a loading state
   forever in that case?
5. **Is the `unique symbol` brand on `SharingTarget` worth its one `as` cast?**
   The cast in `resolveSharingTarget` is the single place the brand is applied,
   and only after the id was matched against server-loaded state.
6. **Should the pre-existing `expo`/`expo-router` patch drift be raised as its own
   dependency task?** It is out of TASK-014's owned paths and was not touched.
7. **Is the per-team accessible label wording correct in Thai**, given the visible
   label is identical on every row and only the spoken label names the team?

That concluded Round 1. Codex then reviewed it and raised the finding below.

---

# Round 2 — Codex finding and fix

Status: **fixed and verified locally.** Awaiting GPT/Codex read-only Round 2
review.

Codex raised one **Medium** finding against Round 1. The Product Owner approved it.
It is fixed in commit `2929bf76f049e2f1fefc23d6e844c87311b67b3c`.

## Pre-flight, confirmed before the first Round 2 edit

| Gate                                           | Result                                                   |
| ---------------------------------------------- | -------------------------------------------------------- |
| worktree                                       | the existing TASK-014 worktree, still locked             |
| branch                                         | `feat/TASK-014-athlete-check-in-sharing-controls-mobile` |
| starting `HEAD`                                | `ffcca606441f1223aa594fe7ff7ae90d81df9a5e` exactly       |
| worktree clean                                 | yes, `git status --porcelain` empty                      |
| approved base still an ancestor                | yes, `git merge-base --is-ancestor` exit 0               |
| `feat/mobile-foundation` unchanged at the base | yes, `3b94742c3a5f28f82e8583b29957159fce9343a2`          |
| existing commits amended, rebased, or squashed | no                                                       |

## The finding

`CheckInSharingSection` consumed three pieces of mutation state without proving
they belonged to the current verified identity: `mutation.isPending`,
`mutation.isSuccess` / `mutation.data`, and `mutation.isError` /
`mutation.variables`.

## Root cause

An **active** `MutationObserver` survives the removal of its mutation from the
`MutationCache`. `clearAuthScopedQueries` calls `MutationCache.clear()`, which
removes the mutation from the cache but neither aborts it nor detaches its
observers. The observer keeps pointing at the old mutation, so when that mutation
settles the observer transitions to success or error and reports the **previous
account's** result and variables.

I reproduced this independently against the installed TanStack version before
writing any fix, with a throwaway probe that was deleted afterwards. Asserted
directly, and all assertions passed:

1. the old action is in flight — `client.isMutating()` is 1;
2. `MutationCache.clear()` runs — `getAll().length` is 0;
3. the observer's options are replaced for a new identity;
4. the old action settles;
5. the **same** observer reports `status: "success"`, holds the old result, and
   holds the old variables;
6. a **freshly constructed** observer, by contrast, is `status: "idle"` with no
   data, no variables, and not pending.

Step 5 is the defect and step 6 is the fix, both established as facts about the
installed library rather than assumptions.

Consequences, as Codex described them:

- the new account could receive the previous account's success or failure banner;
- the new account's controls could stay disabled by the previous account's pending
  request;
- the previous account's user id, team id, and query key remained readable from
  observer state.

The database write and the refetch key remained correctly scoped to the original
account. **This was a UI, privacy, and correctness defect, not a cross-account
database write.** Round 1's guarantees on the write and the refetch were correct,
and their tests are untouched and still pass.

## The fix

Three changes, all inside `features/sharing/`.

### 1. An identity-keyed observer boundary

`sharingIdentityBoundaryKey(userId)` produces a React `key` for the subtree that
owns the hooks. `CheckInSharingSection` is now **only** the boundary: it reads the
verified identity from `useAuth` and renders `SharingControls` under that key.
`SharingControls` owns `useCheckInSharingQuery` and `useSharingAction`.

On a verified identity change the key changes, so React unmounts the old subtree —
destroying its mutation observer and its query observer — and mounts fresh ones. A
freshly constructed observer holds no current mutation, so the new identity begins
fully idle.

Keyed, **not** reset by an effect. A reset effect would render one frame of the
previous account's outcome before clearing it; a changed key means the old observer
does not exist when the new one is created. Signing out is an identity change like
any other, so it also remounts.

`MutationCache.clear()` is unchanged and still necessary — it stops the old
mutation being found again — but relying on it alone was the defect.

### 2. One place observer state becomes something rendered

`readSharingOutcome` maps mutation state to exactly what the section renders:
`busy`, `busyTeamId`, `successAction`, `failedAction`. Pure, total, and defensive —
each branch requires **both** the status flag and the value it uses, so a state
claiming success without data, or an error without variables, renders no banner
rather than a partial one. Busy is checked first, so a second action starting
disables everything even if a previous outcome lingers.

This makes "the new identity begins fully idle" a property of a tested function
rather than a hope about lifecycle ordering, and it is what lets the regression feed
a **genuine `MutationObserver` result** through the exact function the component
uses.

### 3. Mutation data minimized

`SharingActionResult` is now `{ action }`. The auth-scoped key, the owner, and the
team were only ever needed _inside_ `mutationFn`, and mutation data outlives its
identity on an active observer, so keeping authorization metadata there was part of
the leak. They are now locals; the captured key is still proved to be used, by the
existing refetch assertion.

## What was NOT changed

`auth-provider.tsx`, `lib/query/client.ts`, and their tests are outside TASK-014
ownership and were **not modified**. The regression _imports_ the real
`clearAuthScopedQueries` rather than reimplementing or changing it.

The Round 1 pending-options test is **not weakened**. It still proves the old
action and its key cannot be redirected. The new tests prove the separate property
that the old observer's state cannot appear in the new account.

## Changed files

Six, all inside the already-owned paths.

| File                                         | Change                                                                              |
| -------------------------------------------- | ----------------------------------------------------------------------------------- |
| `features/sharing/identity-boundary.ts`      | **new** — the boundary key and `readSharingOutcome`                                 |
| `features/sharing/identity-boundary.test.ts` | **new** — the lifecycle regression and the outcome audit                            |
| `features/sharing/sharing-section.tsx`       | split into the boundary and `SharingControls`; reads state via `readSharingOutcome` |
| `features/sharing/query-options.ts`          | `SharingActionResult` minimized to `{ action }`; key kept as a local                |
| `features/sharing/query-options.test.ts`     | updated for the minimized result                                                    |
| `features/sharing/source-safety.test.ts`     | two AST guards for the boundary; scanned-file count 9 → 10                          |

No database file, generated type, dependency, lockfile, navigation, shared
component, theme file, or runtime auth/cache module was touched — audited
explicitly with `git status --porcelain` over each forbidden path.

## The lifecycle regression

`features/sharing/identity-boundary.test.ts`, using the installed TanStack
implementation and no component renderer.

The core test drives the real sequence for **both** old-action success and
old-action failure:

1. the old identity's action starts; `client.isMutating()` is asserted to be 1, so
   it is genuinely in flight;
2. the real `clearAuthScopedQueries(client)` runs; the mutation cache is asserted
   empty;
3. `sharingBoundaryChanged(OLD, NEW)` is asserted true — the key changed, which is
   what makes React remount — and the old observer is detached exactly as an unmount
   detaches it;
4. the new identity's observer is created fresh and subscribed;
5. only then does the old action settle;
6. assertions, all reduced to safe values:
   - the new observer received **zero notifications**;
   - the new observer reduces to
     `idle|no-data|no-error|no-variables|not-pending|not-success|not-failure`;
   - the derived outcome reduces to `idle|no-busy-team|no-success|no-failure`, and
     `isIdleSharingOutcome` is true, so the new account's controls are not disabled;
   - the old write recorded only `grant:A`;
   - the old refetch owner label is only `owner-old`, never `owner-new` or
     `unknown`;
   - the replacement identity was never written to and never refreshed.

Supporting tests:

- **the positive control** — reusing the same observer with swapped options, which
  is what `clearAuthScopedQueries` alone leaves you with, is asserted to notify the
  observer and to leave it non-idle. This is the guard required by the task: it
  fails if TanStack ever starts detaching observers on `MutationCache.clear()`, at
  which point the boundary would be belt-and-braces rather than load-bearing;
- **an unchanged identity keeps a live action visible** — the boundary must not be
  so eager that an ordinary rerender cancels an action or hides its busy state.
  Asserted as `busy|busy-team-A|no-success|no-failure` then
  `idle|no-busy-team|success-grant|no-failure`;
- **boundary key behaviour** — distinct per identity, distinct for signed out,
  stable for an unchanged identity, empty id treated as no identity, and three
  distinct keys across the four transitions the app can make (a count only);
- **the outcome audit** — success path, error path, busy-team selection, busy
  preferred over a lingering outcome, no banner from an inconsistent state, and no
  busy team when pending variables are absent;
- **result minimization** — `Object.keys(result)` is exactly `["action"]`, and the
  serialized result is scanned for the old user id, the new user id, both team ids,
  `auth-scoped`, and the team-name fragment, reporting no leaks.

### Structural guards for the `key` prop

The boundary is a `key` prop, which cannot be exercised behaviourally without a
component renderer this task may not add. Two AST guards in `source-safety.test.ts`
pin it instead:

- exactly **one** JSX `key` in `sharing-section.tsx` is derived from
  `sharingIdentityBoundaryKey`, and the section names `useAuth`;
- the only properties read off `mutation` in the section are `error` and `mutate`,
  so every piece of mutation _state_ must arrive through `readSharingOutcome`.

## Safe mutation evidence

Five reversible mutations, applied one at a time with the Round 1 harness: hash the
file, mutate, verify changed, run the focused suite with output captured to a file
that is never printed, restore from backup, compare hashes. Every restore was
byte-identical and every leak scan returned **0**.

| Mutation                                                | Failing tests | Files | Leak count | Restored |
| ------------------------------------------------------- | ------------- | ----- | ---------- | -------- |
| make the boundary key constant                          | 4             | 1     | 0          | yes      |
| remove the boundary key from the section                | 1             | 1     | 0          | yes      |
| read `mutation.isPending` directly in the section again | 1             | 1     | 0          | yes      |
| put the user id and team id back into mutation data     | 2             | 2     | 0          | yes      |
| make the outcome ignore the busy state                  | 4             | 1     | 0          | yes      |

The two boundary mutations were additionally confirmed to fail **for the intended
reason** by extracting the failing test _names_. Test titles are fixed English
strings authored in this repository, so printing them discloses nothing; assertion
diffs were still never printed and the leak scan still ran over the full output.

- constant key → `distinguishes two verified identities`,
  `distinguishes signing out from being signed in`,
  `never collides across the transitions the app can make`, and the lifecycle
  regression `never updates the new identity's rendered state`;
- removed key → `keys the hook-owning subtree by the verified identity`.

### A gap found in this task's own tests

Recorded rather than quietly corrected.

On its first run, the mutation that **removes the boundary key from the section**
was **not detected**: 0 failing tests, 144 passing. The behavioural regression
constructs its observers directly, so it could not see a missing `key` prop in JSX,
and this task may not add a component renderer.

The two AST guards above were added specifically to close that gap, and the mutation
was re-run to confirm it now fails with 1 failing test in
`source-safety.test.ts > keys the hook-owning subtree by the verified identity`.
Both the escape and its closure happened before the fix was committed.

After the last restore, the unmutated suite was re-run and passes.

## Commands run and results — Round 2

The database contract is unchanged, so per the task instruction the local Supabase
stack was **not started** for Round 2. No database dependency was discovered. The
Round 1 pgTAP evidence stands as recorded: 5 files, 583 assertions,
`Result: PASS`, DB lint 0 warnings, stack stopped with 0 containers remaining.

| Command                                                               | Result                                                          |
| --------------------------------------------------------------------- | --------------------------------------------------------------- |
| focused Vitest (`src/features/sharing`, `src/lib/query/keys.test.ts`) | **8 files, 146 tests, all passing** (Round 1: 7 / 128)          |
| `corepack pnpm test`                                                  | **34 files, 614 tests, all passing** (Round 1: 33 / 596)        |
| `corepack pnpm format:check`                                          | exit 0, all files match Prettier style                          |
| `corepack pnpm lint`                                                  | exit 0, no ESLint output                                        |
| `corepack pnpm typecheck`                                             | exit 0, `tsc --noEmit` clean                                    |
| `corepack pnpm exec expo export --platform web`                       | exit 0, 34 output files, **13 static routes — still unchanged** |
| `git diff --check`                                                    | clean                                                           |
| changed-file audit                                                    | 6 files, all inside the owned paths                             |
| forbidden-path audit                                                  | none touched                                                    |
| `git status --short`                                                  | empty                                                           |

## Round 2 commit ledger

| Commit                                       | Purpose                                          | Changed files |
| -------------------------------------------- | ------------------------------------------------ | ------------- |
| `ffcca606441f1223aa594fe7ff7ae90d81df9a5e`   | Round 1 documentation closeout (starting `HEAD`) | 2             |
| `2929bf76f049e2f1fefc23d6e844c87311b67b3c`   | Round 2 fix and regression                       | 6             |
| branch `HEAD`                                | Round 2 documentation closeout                   | 2             |
| **Complete TASK-014 diff against `3b94742`** |                                                  | **23**        |

No commit was amended, rebased, squashed, or rewritten. `0974b43`, `107bea8`, and
`ffcca60` are all untouched.

## Privacy impact — Round 2

Round 2 **reduces** exposure; it adds none.

- The previous account's user id, team id, and query key are no longer reachable
  from observer state, because they are no longer in mutation data.
- One person can no longer be shown another person's consent outcome, busy control,
  or disabled control.
- Still no health measurement anywhere in this feature, still nothing logged, still
  nothing persisted to disk, and the cache remains memory-only and auth-scoped.
- No new dependency, so no new supply-chain surface.
- All identifiers and names in the new tests are synthetic. Observer results,
  variables, keys, user ids, team ids, and captured errors are reduced to fixed
  words, booleans, counts, owner labels, or case names before any assertion; no
  `MutationObserverResult` is ever passed to `expect`.

## Remaining limitations — Round 2

The eight Round 1 limitations stand. Round 2 adds two:

9. **The `key`-prop boundary is verified structurally, not by rendering.** The
   behavioural regression proves that a fresh observer is idle and that the old
   action cannot notify it; the AST guards prove the section actually wires the key
   and never reads mutation state directly. Neither renders the component, because
   this task may not add a component renderer. A component-level test would close
   the last inch and needs a task that owns a renderer dependency.
10. **The old action is allowed to run to completion** under its original scope
    rather than being aborted. That is deliberate — the athlete asked for it and its
    write and refetch are correctly scoped — but it means a revoke started just
    before signing out still completes, invisibly to the new session. Aborting it
    instead would need an abort signal threaded through the repository and is a
    product decision, not a bug fix.

## Remaining reviewer questions — Round 2

The seven Round 1 questions stand where not superseded. Question 1 is partly
answered by this round: removing `onSuccess` was necessary but not sufficient, and
the observer boundary is the other half.

New:

8. **Is the identity-keyed remount the right boundary**, or would you prefer the
   inner component to take the verified user id as an explicit prop as well, so the
   dependency is visible in its signature rather than only in its key?
9. **Should the old in-flight action be aborted** on an identity change rather than
   allowed to finish under its original scope? See limitation 10.
10. **Are the two AST guards an acceptable substitute** for a rendered assertion on
    the `key` prop, given the no-renderer constraint — and should a follow-up task
    own a component renderer so this and the section's other display rules can be
    tested by rendering?
11. **Is `readSharingOutcome` preferring `busy` over a lingering success the right
    precedence** for the moment a second action starts while a previous banner is
    still shown?

Stopping here for **GPT/Codex read-only Round 2 review**. Nothing is merged, the
worktree is preserved, and nothing in the Round 1 record above has been rewritten.
