# TASK-014: Athlete Check-in Sharing Controls Mobile

Status: **Round 2 finding fixed and verified locally. Awaiting GPT/Codex
read-only Round 2 review.**

- Round 1 implementation commit: `107bea825a10a7b97917b1d9aa41d5f390c2900d`
- Round 2 fix commit: `2929bf76f049e2f1fefc23d6e844c87311b67b3c`

GPT/Codex reviewed Round 1 and raised **one Medium** finding — cross-account
mutation observer state. The Product Owner approved it and it is **fixed**; see
"Round 2" below and the Round 2 section of `docs/app/handoffs/TASK-014.md`, which
carries the reproduction, the test counts, and the mutation evidence.

Round 2 changed no database contract, no dependency, and no file outside the
already-owned paths.

Writer: Claude Code (sole writer)

Reviewer: GPT/Codex (read-only)

No AGY reviewer is assigned to this task. **AGY must not be used.**

Product Owner: the human repository owner. **The complete scope and the
product/security decisions 1–10 recorded below were approved before
implementation started.** This packet is committed before any application-code
edit so that approval is a matter of record rather than a claim made afterwards.

## Goal and user value

Add the smallest mobile vertical slice that lets an authenticated athlete
control whether each of their teams may read their Daily Check-in data.

TASK-011 built the consent boundary in PostgreSQL — `public.sharing_grants`, its
RLS, the two write RPCs, and the authorization helper — and recorded as a known
limitation that "no mobile UI is delivered, so the RPCs are unreachable from the
app in this task". TASK-013 then made the athlete produce the data those grants
govern: RPE, overall feeling, and pain-presence status.

The consequence today is that an athlete can create protected health data and has
no way to turn sharing on or off. This task closes that gap and nothing else.

The user value is direct and is the whole point of the consent design: sharing is
something the athlete turns on and turns off per team, deliberately, and the app
never claims a sharing state the server has not confirmed.

**This task creates and changes no database contract.** It consumes the existing
TASK-011 table, RLS, and RPCs exactly as they are.

## Base and ownership

- Source branch: `feat/mobile-foundation`
- Approved base SHA: `3b94742c3a5f28f82e8583b29957159fce9343a2`
- Task branch: `feat/TASK-014-athlete-check-in-sharing-controls-mobile`
- Isolated worktree:
  `.claude/worktrees/task-014-athlete-check-in-sharing-controls-mobile`
- Claude Code is the only writer. The reviewer does not edit implementation
  files.
- No merge, push, deploy, hosted link, remote migration, `db push`, branch
  deletion, worktree removal, main-checkout edit, or production operation is part
  of this task.

The automatically created worktree branch
`worktree-task-014-athlete-check-in-sharing-controls-mobile` is renamed to the
task branch name with `git branch -m`. No other branch is created, moved, or
deleted.

### Pre-flight gates, confirmed before the first edit

| Gate                                                  | Result                                             |
| ----------------------------------------------------- | -------------------------------------------------- |
| worktree clean                                        | yes, `git status --porcelain` empty                |
| `HEAD` is the approved base                           | `3b94742c3a5f28f82e8583b29957159fce9343a2` exactly |
| the base is the approved `feat/mobile-foundation` tip | yes, the branch resolves to the same SHA           |
| the base is an ancestor of the task branch            | yes, `git merge-base --is-ancestor` exit 0         |
| the intended task branch already exists               | no, `refs/heads/feat/TASK-014-…` absent            |
| renaming would overwrite a branch                     | no, the target name was unused                     |
| main checkout modified                                | no                                                 |

## Approved product and security decisions

1. **Placement.** A "Daily Check-in sharing" section is added to the existing
   Profile/Me screen. No route and no tab is added.
2. **Category.** Exactly `check_in` is supported. `workout_summary` and
   `sleep_summary` are neither displayed nor mutated.
3. **Per-team control.** One independent control per active athlete membership. A
   multi-team athlete manages each team separately.
4. **Consent meaning.** Consent is granted to the **team**, covering every active
   coach of that team including a coach who joins later. This is stated plainly
   in fixed Thai copy, so the athlete is not left believing they consented to one
   named person.
5. **Default and history.** No active grant means sharing is off. Consent is
   never created automatically. Revoked history stays in the database and no
   history screen is added.
6. **Deliberate action.** Explicit grant and revoke buttons with clear wording,
   not an optimistic switch. Both directions require a deliberate press.
7. **Server authority.** Sharing state is never changed optimistically. The RPC
   runs and the server state is refetched; the UI must not claim the new state
   before server confirmation.
8. **Online-only.** Mutation options use `networkMode: "always"` and `retry: 0`.
   An offline action attempts immediately, fails visibly, and needs a new
   deliberate press. No pause, queue, outbox, persistence, reconnect execution,
   or background retry.
9. **Identity and command scope.** The verified user id comes only from the auth
   provider. The UI supplies no athlete id. RPC arguments are only the selected
   server-loaded team id and the constant category `check_in`.
10. **Membership revocation.** Controls exist only for active athlete
    memberships. A revoked membership disappears on the next successful load,
    database triggers revoke its grants, and reactivation never restores old
    consent automatically.

## In scope

- A sharing section on `platform/apps/mobile/src/app/profile.tsx`.
- One feature module under `platform/apps/mobile/src/features/sharing/**`.
- Loading active athlete memberships together with their team names.
- Loading the caller's active `check_in` grants.
- Strict fail-closed runtime validation of every loaded row.
- Grant through `grant_team_data_sharing(p_team_id, "check_in")`.
- Revoke through `revoke_team_data_sharing(p_team_id, "check_in")`.
- One auth-scoped query key in `platform/apps/mobile/src/lib/query/keys.ts`.
- Query and mutation hooks.
- Loading, empty, error, retry, busy, success, granted, and not-granted states.
- Multiple teams with independent state.
- Fixed sanitized Thai user-facing copy.
- Accessible labels and disabled/busy state.
- Pure-logic, repository, query-option, source-safety, and failure-path tests
  using only dependencies already in the workspace.
- Local Supabase verification with synthetic fixtures only.
- A sanitized handoff at `docs/app/handoffs/TASK-014.md`.

## Out of scope / forbidden

- Any migration, RLS policy, grant, schema change, pgTAP edit, or generated
  database-type change.
- Workout or sleep sharing UI.
- Consent-history UI.
- Coach dashboard.
- Team or membership administration.
- Invitations.
- Check-in history.
- Training plans.
- HealthKit or Health Connect.
- Garmin, Strava, WHOOP, COROS, connected-device tokens, or any vendor API.
- Notifications, analytics, monitoring flags, or session replay.
- Offline drafts, outbox, persistence, background work, or automatic retry.
- New dependencies or lockfile changes.
- Shared design-system or navigation refactors.
- Hosted Supabase, remote migrations, push, deploy, or production data.

## Owned paths

Only these paths may be created or modified:

- `docs/app/tasks/TASK-014-athlete-check-in-sharing-controls-mobile.md`
- `docs/app/handoffs/TASK-014.md`
- `platform/apps/mobile/src/app/profile.tsx`
- `platform/apps/mobile/src/features/sharing/**`
- `platform/apps/mobile/src/lib/query/keys.ts`
- `platform/apps/mobile/src/lib/query/keys.test.ts`

If another path is genuinely required, stop and request Product Owner approval.
Scope must not be expanded silently.

### Forbidden paths (non-exhaustive, load-bearing)

- every file under `platform/supabase/`
- `platform/apps/mobile/src/lib/supabase/database.types.ts`
- `platform/apps/mobile/src/features/check-in/**`
- `platform/apps/mobile/src/features/auth/**`
- `platform/apps/mobile/src/features/profile/**`
- `platform/apps/mobile/src/components/**`
- `platform/apps/mobile/src/theme/**`
- `platform/apps/mobile/src/app/_layout.tsx` and every other route file
- `platform/apps/mobile/src/lib/query/client.ts`
- `platform/apps/mobile/src/test-support/**`
- `platform/package.json`, `platform/apps/mobile/package.json`,
  `platform/pnpm-lock.yaml`
- every `docs/app/architecture/` file
- `athletes/`, `team_data/`, `garmin/`, `scripts/`, root `supabase/`
- `CLAUDE.md`, `.agents/AGENTS.md`, `.claude/settings.json`,
  `.claude/settings.local.json`

`components/**` and `theme/**` are read-only imports here. In particular
`components/primary-button.tsx` exposes no `accessibilityLabel` prop and may not
be given one by this task, so the per-team action control is a small
sharing-owned pressable that carries its own accessible label.

## Repository contract

### Load

- Accept the verified authenticated user id explicitly as an argument.
- Query only that user's memberships.
- Require `role = 'athlete'` and `status = 'active'`.
- Load the team name through RLS. A raw team id is never displayed as the team
  label.
- Load only the caller's **active** `check_in` grants.
- Select only the fields needed to determine the team and the current grant
  state.
- Return a strictly validated, stably ordered list.
- **A load failure is not an empty list and not "sharing off".**
- A missing or inaccessible team row, a malformed row, an unexpected
  role/status/category, a duplicate active state, or an inconsistent response
  fails closed.
- Revoked history is never returned to the UI.

### Write

- The grant repository accepts only a **server-loaded** team id, carried in a
  branded value that only the loaded list can produce.
- Grant calls `grant_team_data_sharing` with that team id and the constant
  `check_in`.
- Revoke uses the same restricted arguments.
- Neither accepts an athlete id.
- A grant counts as successful only when the expected non-health sentinel — the
  grant row id — is returned.
- A repeated revoke returning `null` is safe and produces the server-confirmed
  off state.
- Resolved errors, synchronous throws, rejected builders and thenables, and
  unexpected failures are all sanitized.
- No raw `message`, `details`, `hint`, `cause`, payload, row, or RPC argument is
  retained in the error exposed to React Query.
- Nothing logs.

## Query and mutation contract

- One auth-scoped key for the caller's check-in-sharing list.
- The key contains the verified user id and no health value.
- It keeps the shared `AUTH_SCOPE` prefix so `clearAuthScopedQueries` still
  removes it.
- The exact auth-scoped key is captured inside `mutationFn` **before** the write
  is awaited.
- An identity change during an in-flight mutation must not redirect the refresh
  to the new account.
- No `onMutate`, no `setQueryData`, no optimistic state, no automatic retry, no
  pause, no persistence.
- `networkMode: "always"` and `retry: 0` are mandatory.
- A successful action refetches the exact server list before the UI presents the
  confirmed state.
- One in-flight action disables all sharing actions, which is both the
  duplicate-submit guard and the cross-team guard.

## UI requirements

The Profile/Me sharing section must include:

- a concise explanation that Daily Check-in contains RPE, overall feeling, and
  pain-presence status;
- clear wording that consent applies to the active coaches of the selected team,
  not to one named coach;
- one card per active athlete team;
- the team name;
- the current state, sharing or not sharing;
- an explicit "allow team to view" or "stop sharing" action;
- no preselected and no automatic consent;
- a loading state;
- a real empty state when there is no active athlete team;
- a load-error state with a deliberate retry;
- a busy state that prevents a duplicate press and a cross-team mutation;
- fixed sanitized success and error feedback.

No raw team id, database wording, error code, RPC name, or raw server message is
ever shown to the user. Coach-only, pending, revoked, and unauthenticated states
gain no grant capability.

## As implemented

Every file below is inside the owned paths. Nothing else was created or changed.

| Module                                       | Responsibility                                                                                 |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `features/sharing/domain.ts`                 | the `check_in` constant, fail-closed validation of both responses, the branded `SharingTarget` |
| `features/sharing/errors.ts`                 | sanitized `load`/`grant`/`revoke` failures from fixed tables                                   |
| `features/sharing/sharing-repository.ts`     | the two scoped reads and the two approved RPCs                                                 |
| `features/sharing/action-plan.ts`            | the press decision: refuse while busy, direction from loaded state                             |
| `features/sharing/query-options.ts`          | the auth-scoped key, `networkMode`, `retry`, the captured-key refetch                          |
| `features/sharing/use-check-in-sharing.ts`   | binds the above to the verified identity and the query client                                  |
| `features/sharing/copy.ts`                   | every user-facing string, plus the two accessible-label builders                               |
| `features/sharing/sharing-section.tsx`       | the Profile/Me section and all seven display states                                            |
| `features/sharing/sharing-action-button.tsx` | the per-team control, with its own accessible label                                            |
| `features/sharing/identity-boundary.ts`      | the identity-keyed observer boundary and `readSharingOutcome` (Round 2)                        |
| `features/sharing/failure-probe.ts`          | test support; reduces a rejection to a safe vocabulary                                         |
| `app/profile.tsx`                            | renders the section between the name form and sign-out                                         |
| `lib/query/keys.ts`                          | the `checkInSharing` auth-scoped key                                                           |

Seven test files accompany them: `domain.test.ts`, `sharing-repository.test.ts`,
`query-options.test.ts`, `action-plan.test.ts`, `identity-boundary.test.ts`,
`source-safety.test.ts`, and `logging.test.ts`, plus additions to
`lib/query/keys.test.ts`.

Two design points are worth a reviewer's attention because they differ from the
obvious reading of the contract:

1. **There is no `onSuccess`.** The contract asks that an identity change cannot
   redirect invalidation. Rather than guard a settle-time callback, the callback
   was removed: `mutationFn` is read once when execution begins, so the key it
   captures and the refetch it awaits both belong to the identity the write was
   made as. The mutation options are exactly `mutationFn`, `networkMode`, and
   `retry`.
2. **A failed refresh does not fail a successful action.** If the RPC succeeded
   and the refetch then failed, reporting the action as failed would tell the
   athlete sharing is still off when it is on. The refetch rejection is therefore
   swallowed inside `mutationFn`; the query owns its own error state and the
   section shows the load error and its retry instead.
3. **The section is an identity boundary, not a hook holder** (Round 2). The
   exported component reads the verified identity and renders the hook-owning
   subtree under a key derived from it. See "Round 2" below.

## Round 2 — cross-account mutation observer state

Status: **fixed and proved by a lifecycle regression.** Approved by the Product
Owner. Fix commit `2929bf76f049e2f1fefc23d6e844c87311b67b3c`.

### The finding

`CheckInSharingSection` consumed `mutation.isPending`, `mutation.isSuccess` /
`mutation.data`, and `mutation.isError` / `mutation.variables` without proving they
belonged to the current verified identity.

An **active** `MutationObserver` survives removal of its mutation from the
`MutationCache`. `clearAuthScopedQueries` calls `MutationCache.clear()`, which
removes the mutation but neither aborts it nor detaches its observers. Reproduced
against the installed TanStack version:

1. an old-identity action starts and stays pending;
2. the auth-scoped query and mutation caches are cleared;
3. the observer's options are replaced for a new identity;
4. the old action settles;
5. the still-active observer becomes **success with the old result**, even though
   the mutation cache is empty.

Consequences: the new account could receive the previous account's success or
failure banner; its controls could stay disabled by the previous account's pending
request; and the previous account's user id, team id, and query key remained
readable from observer state.

The database write and the refetch key remained correctly scoped to the original
account, so this was a **UI, privacy, and correctness defect, not a cross-account
database write.** Round 1's guarantees on the write and the refetch were correct
and are unchanged.

### The fix

`sharingIdentityBoundaryKey(userId)` produces a React `key` for the subtree that
owns the hooks. On a verified identity change the key changes, React **unmounts**
the old subtree — destroying its mutation and query observers — and mounts fresh
ones. A freshly constructed observer holds no current mutation, so the new identity
begins fully idle.

Keyed rather than reset by an effect: a reset effect would render one frame of the
previous account's outcome before clearing it, whereas a changed key means the old
observer no longer exists when the new one is created.

`MutationCache.clear()` is unchanged and still necessary — it stops the old
mutation being found again — but relying on it alone was the defect.

`readSharingOutcome` is now the single place observer state becomes something
rendered. It is pure and total, and each branch requires **both** the status flag
and the value it uses, so a state claiming success without data renders no banner.

`SharingActionResult` is minimized to `{ action }`. The key, owner, and team were
only ever needed inside `mutationFn`, and mutation data outlives its identity on an
active observer, so they are now locals.

### Required behaviour, and where it is proved

| Requirement                                                                  | Proof                                                                                                      |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| a verified identity change creates a fresh observer boundary                 | `sharingBoundaryChanged` is true across identities and false for an unchanged one                          |
| the new identity begins not busy, with no banner, no old variables or result | the new observer reduces to `idle\|no-data\|no-error\|no-variables\|not-pending\|not-success\|not-failure` |
| controls not disabled by the previous account                                | the derived outcome reduces to `idle\|no-busy-team\|no-success\|no-failure`                                |
| the old action may finish but never updates the new rendered state           | the new observer receives **zero** notifications while the old action settles                              |
| the old write is never redirected                                            | the old harness recorded only `grant:A`                                                                    |
| the old refetch is never redirected                                          | the old refetch owner label is only `owner-old`; never `owner-new`                                         |
| query state stays auth-scoped and cleared by the existing mechanism          | the real `clearAuthScopedQueries` is invoked and the mutation cache is asserted empty                      |
| removing the boundary makes the regression fail                              | a positive control proves the hazard is still reproducible, and two mutations make the regression fail     |

Both directions of the old action are covered — success and failure — and the
signed-out transition is covered as an identity change like any other.

Because the boundary is a `key` prop and this task may not add a component
renderer, two AST guards pin it structurally: exactly one JSX `key` in the section
is derived from `sharingIdentityBoundaryKey`, and the only properties read off
`mutation` are `error` and `mutate`.

`auth-provider.tsx`, `lib/query/client.ts`, and their tests were **not modified**.
`clearAuthScopedQueries` is imported by the regression, not changed.

## Acceptance criteria

All nineteen are satisfied. The evidence column names the test or check that
proves each one; full counts are in the handoff.

- [x] 1. An active athlete sees every active athlete team by name — the
      membership read embeds `teams(name)` and a row without a visible team name
      is refused (`domain.test.ts`, `sharing-repository.test.ts`).
- [x] 2. Each team shows its own independently server-confirmed `check_in`
      sharing state — `parseCheckInSharingList` composes per team and both
      cross-team directions are asserted.
- [x] 3. A missing grant means off and creates nothing — the read is a `SELECT`
      only; no write happens on any load path, including every failure path.
- [x] 4. Grant calls only the approved RPC, with the selected team and the
      constant category — the RPC name, its two argument keys, its team argument,
      and its category are all asserted.
- [x] 5. Revoke calls only the approved revoke RPC with the same scope — same
      assertions for `revoke_team_data_sharing`.
- [x] 6. An action on Team A does not change Team B — asserted in the domain
      composition, the repository, the mutation options, and `action-plan.ts`.
- [x] 7. Sharing state is refetched from the server; there is no optimistic
      update — the options object has exactly `mutationFn`, `networkMode`, and
      `retry`, and the refetch is awaited inside `mutationFn`.
- [x] 8. A load failure is shown as an error, never as off and never as empty —
      seventeen repository failure cases each raise a sanitized `load` error, and
      the section's error branch precedes and replaces the list branch.
- [x] 9. Malformed or inconsistent rows fail closed — 49 rejection cases.
- [x] 10. Identity always comes from verified auth state — the user id comes only
      from `useAuth`; five non-identity values are refused before any query.
- [x] 11. Account replacement during an in-flight action cannot redirect the
      refresh — proved with `MutationObserver.setOptions` mid-flight. **Extended in
      Round 2:** the old action's observer state also cannot appear under the new
      identity, proved by the lifecycle regression driving the real
      `clearAuthScopedQueries` and asserting the new observer receives zero
      notifications and stays fully idle, for both old-action success and failure.
- [x] 12. Offline actions are not paused, queued, retried, or executed on
      reconnect — plus a positive control showing the library default _would_
      pause.
- [x] 13. Duplicate presses produce one operation — `planSharingAction` refuses
      while busy, for the same team and for any other team.
- [x] 14. A revoked membership loses its control on the next successful load, and
      no old grant revives — the control, the write target, and the press are all
      refused once the team stops being returned; the grant revocation itself is
      the TASK-011 trigger, still covered by the passing pgTAP suite.
- [x] 15. No health value, raw error, payload, token, or credential is logged,
      cached optimistically, persisted, or printed in failing test output — an
      AST source scan, a runtime console-silence suite, and a programmatic leak
      scan of the captured mutation output reporting zero occurrences.
- [x] 16. No database, generated-type, dependency, lockfile, navigation, or
      shared-theme change — confirmed by an exact changed-file audit; the web
      export still reports the same 13 static routes.
- [x] 17. Existing unit and database authorization suites remain passing — 596
      workspace tests and 5 pgTAP files / 583 assertions.
- [x] 18. Documentation matches the implementation and Git finishes clean.
- [x] 19. Nothing is merged, pushed, deployed, linked, or remotely migrated.

## Required negative tests

At minimum:

- no authenticated identity;
- coach-only user;
- revoked athlete membership;
- forged or unowned team id;
- category cannot vary from `check_in`;
- another athlete's grants never enter the result;
- a Team A grant leaves Team B unchanged;
- a Team A revoke leaves Team B unchanged;
- a duplicate grant remains one active state;
- a repeat revoke is safe;
- a membership, team, or grant query error is not empty and not off;
- a missing team name;
- a malformed team, membership, category, or grant row;
- a synchronous throw and a rejected query or RPC;
- a raw Supabase `message`, `details`, `hint`, and `cause` are discarded;
- a duplicate press while busy;
- an offline immediate attempt with no pause and no reconnect execution;
- a positive control proving the library default would pause without
  `networkMode: "always"`;
- retry remains zero;
- no optimistic cache write;
- pending mutation options replaced by another identity;
- a revoked membership disappears after a refetch;
- failing assertions emit only booleans, counts, safe field names, or case names.

## Failure-output safety

Sharing metadata is not a health measurement, but it is sensitive authorization
data and is treated as such.

- Team and grant objects, RPC arguments, mock calls, user ids, and raw errors are
  reduced **privately** to booleans, counts, fixed safe field-name lists, or
  synthetic case names before reaching any assertion.
- Complete rows, requests, responses, captured errors, mutation variables, and
  mock calls are never compared or snapshotted.
- Captured failing output is never printed. Where mutation testing captures
  output, it is scanned programmatically and only scalar leak counts are
  reported.
- Only synthetic names and identifiers are used.

## Privacy classification

The data this feature reads and writes is consent metadata plus a team name: a
team id, a team name, a role, a status, a category name, and the existence of an
active grant. **It contains no health measurement.** The three protected
check-in values are named only in explanatory copy, never read, transported, or
cached by this feature.

Consent metadata and team names are still PII and authorization-relevant, so the
same discipline applies: nothing is logged, nothing is persisted to disk, the
cache is memory-only and auth-scoped, and no server error text reaches the user.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm --filter @run-performance/mobile exec vitest run src/features/sharing src/lib/query/keys.test.ts
corepack pnpm test
```

From `platform/apps/mobile/`:

```powershell
corepack pnpm dlx expo-doctor@latest
corepack pnpm exec expo export --platform web --output-dir <scratch>
```

Because this mobile feature relies on the existing TASK-011 RPC and RLS
contract, the existing local database suite is also run:

```powershell
corepack pnpm db:start *> $null
"start exit: $LASTEXITCODE"
corepack pnpm exec supabase db reset --local --no-seed
corepack pnpm exec supabase test db --local
corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning
corepack pnpm db:stop *> $null
"stop exit: $LASTEXITCODE"
```

Only safe exit codes, file and assertion counts, and container counts are
reported. `supabase status` and `db:status` are never run or printed.
`--linked`, a project ref, a remote URL, a service-role credential, and
production data are never used. `*> $null` redirects every PowerShell stream so
the API URL, anon key, service-role key, JWT secret, and database URL printed by
`supabase start` and `supabase stop` never reach the terminal or a transcript.

Repository checks:

```powershell
git diff --check
git status --short
git diff --name-only
```

## Mutation evidence

Safe, reversible mutations are applied one at a time to prove the material
controls are actually tested. At minimum:

- remove `networkMode: "always"`;
- enable mutation retry;
- redirect the refresh to the replacement identity;
- treat a load failure as empty or off;
- allow the category to vary;
- add optimistic state;
- let a raw thrown error escape;
- weaken cross-team independence;
- weaken malformed-row validation.

Output is captured without printing sensitive content, the exact file is
restored, and the final unmutated suite is confirmed passing.

### Result

Twelve mutations were applied one at a time. Each changed the file (verified by
hash), was detected by at least one failing test, and was restored
byte-identically (verified by hash). The captured runner output was scanned
programmatically for synthetic team ids, user ids, grant ids, team names, and raw
server messages; every mutation reported a leak count of **0**.

| Mutation                                                            | Failing tests | Files |
| ------------------------------------------------------------------- | ------------- | ----- |
| remove `networkMode: "always"`                                      | 4             | 1     |
| enable mutation retry (`retry: 3`)                                  | 2             | 1     |
| move the refresh into a swappable `onSuccess` that rebuilds the key | 6             | 1     |
| treat a membership-read failure as an empty list                    | 2             | 1     |
| let the grant category vary from `check_in`                         | 4             | 2     |
| add optimistic state (`onMutate`)                                   | 2             | 2     |
| let a raw thrown error escape the load                              | 2             | 1     |
| weaken cross-team independence                                      | 3             | 2     |
| skip a malformed membership row instead of failing closed           | 3             | 2     |
| skip a malformed grant row instead of failing closed                | 3             | 2     |
| accept any grant response instead of the sentinel                   | 1             | 1     |
| accept a forged team id as a write target                           | 6             | 2     |

The unmutated suite was re-run afterwards: 128 focused and 596 workspace tests
pass.

### Round 2 result

Five further mutations, same harness and same discipline. Each changed the file,
was detected, and was restored byte-identically; every leak scan returned **0**.

| Mutation                                                | Failing tests | Files |
| ------------------------------------------------------- | ------------- | ----- |
| make the boundary key constant                          | 4             | 1     |
| remove the boundary key from the section                | 1             | 1     |
| read `mutation.isPending` directly in the section again | 1             | 1     |
| put the user id and team id back into mutation data     | 2             | 2     |
| make the outcome ignore the busy state                  | 4             | 1     |

The two boundary mutations were additionally confirmed to fail **for the intended
reason** by extracting the failing test _names_ — fixed English titles authored in
this repo, so printing them discloses nothing:

- constant key → `distinguishes two verified identities`,
  `distinguishes signing out from being signed in`,
  `never collides across the transitions the app can make`, and the lifecycle
  regression `never updates the new identity's rendered state`;
- removed key → `keys the hook-owning subtree by the verified identity`.

Removing the boundary key from the section initially escaped detection, because no
test renders the component and this task may not add a component renderer. That gap
was closed with the two AST guards before the fix was committed, and the mutation
was re-run to confirm it now fails. The gap and its closure are recorded rather
than quietly fixed.

The unmutated suite was re-run afterwards: 146 focused and 614 workspace tests
pass.

## Known limitations (recorded before implementation)

- Sharing is per team by TASK-011 decision 1. An athlete cannot exclude one coach
  of a team they have consented to.
- There is still no client-reachable path to create teams or memberships, so an
  athlete with no membership sees the empty state and the grant path can only be
  exercised end to end against trusted fixtures until a membership-administration
  task exists.
- Only `check_in` is controllable. `workout_summary` and `sleep_summary` grants
  exist in the database and have no UI, by decision 2.
- No consent-history view is offered, so the athlete cannot see when they
  previously granted or revoked.
- The section is online-only by decision 8. There is no offline affordance beyond
  a visible failure and a new press.
- The load fails closed when a returned active grant names a team that is not in
  the caller's active athlete membership list. That is the safe direction, but it
  means a membership activated between the two reads shows a retryable error
  once rather than a partial list.
- The section renders its loading state while no identity exists. The route is
  gated upstream, so this is unreachable in the running app.

### Found during verification

- `expo-doctor` reports 20 of 21 checks passing. The one failure is a
  **pre-existing** patch-version drift unrelated to this task: the installed
  `expo` 56.0.17 and `expo-router` 56.2.16 are behind the SDK's current
  `~56.0.18` and `~56.2.17`. TASK-014 owns no dependency manifest and no
  lockfile, and all three files were confirmed byte-identical to the approved
  base, so this is reported rather than fixed. It needs a separate dependency
  task with a serial owner for the lockfile.
- The load orders the membership read before the grant read specifically to
  avoid a false fail-closed. Reading grants first would let a membership
  activated between the two reads produce a grant with no matching membership,
  which the validation refuses. The residual window in the chosen order is a
  membership activated _between_ the reads, which shows one retryable error.

## Rollback

The task is additive and file-scoped. To roll back:

1. `git revert` the TASK-014 commits, or delete
   `platform/apps/mobile/src/features/sharing/`, this packet, and
   `docs/app/handoffs/TASK-014.md`, and restore
   `platform/apps/mobile/src/app/profile.tsx`,
   `platform/apps/mobile/src/lib/query/keys.ts`, and
   `platform/apps/mobile/src/lib/query/keys.test.ts` from the base SHA.

No migration, generated type, dependency, lockfile, or configuration file is
touched, and nothing was applied to a remote database, so no database or remote
rollback exists or is needed.

## Required handoff

Sanitized, at `docs/app/handoffs/TASK-014.md`, in the canonical format from
`docs/app/AI-WORKING-AGREEMENT.md`, recording: task and writer; branch and
worktree; base and final commit SHAs; changed files; acceptance evidence; safe
test counts; mutation evidence; privacy and security impact; known limitations;
rollback; and remaining reviewer questions.

Then stop for GPT/Codex read-only review. Do not merge and do not remove the
worktree.

## References

- `AGENTS.md`
- `platform/AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/AI-WORKING-AGREEMENT.md`
- `docs/app/tasks/TASK-011-consent-sharing-grants-rls.md`
- `docs/app/handoffs/TASK-011.md`
- `docs/app/tasks/TASK-013-athlete-daily-check-in-mobile.md`
- `docs/app/handoffs/TASK-013.md`
