# TASK-014: Athlete Check-in Sharing Controls Mobile

Status: Approved, not yet implemented

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

## Acceptance criteria

1. An active athlete sees every active athlete team by name.
2. Each team shows its own independently server-confirmed `check_in` sharing
   state.
3. A missing grant means off and creates nothing.
4. Grant calls only the approved RPC, with the selected team and the constant
   category.
5. Revoke calls only the approved revoke RPC with the same scope.
6. An action on Team A does not change Team B.
7. Sharing state is refetched from the server; there is no optimistic update.
8. A load failure is shown as an error, never as off and never as empty.
9. Malformed or inconsistent rows fail closed.
10. Identity always comes from verified auth state.
11. Account replacement during an in-flight action cannot redirect the refresh.
12. Offline actions are not paused, queued, retried, or executed on reconnect.
13. Duplicate presses produce one operation.
14. A revoked membership loses its control on the next successful load, and no
    old grant revives.
15. No health value, raw error, payload, token, or credential is logged, cached
    optimistically, persisted, or printed in failing test output.
16. No database, generated-type, dependency, lockfile, navigation, or
    shared-theme change.
17. Existing unit and database authorization suites remain passing.
18. Documentation matches the implementation and Git finishes clean.
19. Nothing is merged, pushed, deployed, linked, or remotely migrated.

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
