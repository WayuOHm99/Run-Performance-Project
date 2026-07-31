# TASK-017 handoff — Safe Local App Demo Environment and Synthetic Fixtures

Status: **Implementation complete. All verification complete, including the local
database authorization suite and a real end-to-end consent verification.**
Stopped for GPT/Codex read-only review. Not merged. Worktree not removed.

Writer: **Claude Code** (sole writer)
Reviewer: **GPT/Codex** (read-only)
Product Owner: **Wayu**
AGY: **not used**

Task: `docs/app/tasks/TASK-017-safe-local-app-demo-environment.md`
Branch/worktree: `feat/TASK-017-safe-local-app-demo` in
`.claude/worktrees/task-017-safe-local-app-demo`

## Checkpoint as verified at session start

The session was paused by the Product Owner after the packet and the environment
module were written, and resumed later. **Every safety check was re-run on
resume**, because permission settings are read at launch and a previous session
cannot vouch for a later one.

| Check | Result |
| --- | --- |
| Approved base SHA | **pass** — `ccd7d4440b69be390fd6ed35a417006bd66c70ff` |
| Worktree canary denied **before any content** | **pass** — re-run on resume; `Read` of `WORKTREE-CANARY.md` by exact absolute path returned "File is in a directory that is denied by your permission settings" with no file content |
| App deny rules active | **pass** — the canary denial is itself the proof the settings file is loaded and that the `worktrees/*/` wildcard resolves on this machine |
| Root coaching `CLAUDE.md` not loaded | **pass** — no `CLAUDE.md` content entered context; `autoMemoryEnabled: false` and `claudeMdExcludes: ["**/CLAUDE.md"]` |
| `.claude/rules/app-engineering.md` loaded | **pass** — both the repository-root and worktree copies |
| Hosted Supabase MCP blocked | **pass** — `mcp__claude_ai_Supabase__*` is denied; the MCP server connected and disconnected during the session and was never used |
| Task branch did not already exist | **pass** |
| Task worktree clean before editing | **pass** |
| Main checkout intentional changes preserved | **pass** — see below |

**One deviation, reported rather than improvised around.** As in TASK-016, the
worktree was created on the auto-generated branch
`worktree-task-017-safe-local-app-demo`. The required branch
`feat/TASK-017-safe-local-app-demo` was created **at the approved base SHA**
before any file was committed. The auto-generated branch still exists, untouched,
at the same SHA; it was not deleted. No history was rewritten.

**A limitation of this report, stated plainly.** The contract asked me to run
`/memory` and `/permissions`. Those are built-in Claude Code CLI commands and
cannot be invoked from a tool call, so I could not execute them literally. What
is recorded above is the equivalent evidence I *can* establish from inside the
session: the canary denial (which proves the settings file is loaded and the
worktree wildcard resolves), the absence of any `CLAUDE.md` content in context,
and a direct read of `docs/app/claude-app-settings.json` confirming the deny
list. If you want the literal command output, run `/memory` and `/permissions`
yourself in a fresh session — I am not claiming to have run them.

### Main checkout intentional changes

Confirmed present and **untouched** throughout:

```text
 M CLAUDE.md
 M garmin/scripts/03_backfill.py
 M garmin/scripts/dashboard.py
 M garmin/scripts/fetch_all.py
 M garmin/tests/test_fast_sync.py
 M scripts/setup_scheduled_tasks.ps1
?? garmin/garmin-wellness-sync-auto.bat
?? garmin/garmin-wellness-sync-hidden.vbs
```

Only the **file names** were listed, via `git status --porcelain`. No content of
any of those files was read, edited, staged, restored, copied, committed, or
cleaned. **Zero overlap with TASK-017 owned paths**: the intentional changes live
in `CLAUDE.md`, `garmin/`, and `scripts/`; this task touched only `docs/app/` and
`platform/`.

## Commits

| # | SHA | Subject |
| --- | --- | --- |
| 1 | `d8e585bc8129278dd77c8f09e08aab53bf245c66` | `docs(task-017): add the safe local app demo packet` |
| 2 | `6df94175afbb3995b8dd3020218cabdf4cbbe1b9` | `feat(supabase): add a fail-closed local endpoint mode to the client` |
| 3 | `60d01180624126d7465abddeafe4550f9b0e1ac1` | `feat(demo): add local-only demo commands and a synthetic fixture` |
| 4 | `97697d49a088359e5a1d7f7dc3da5ba9a71c3b85` | `docs(task-017): document the local demo workflow and endpoint contract` |
| 5 | *this commit* | `docs(task-017): record the implementation handoff` |

All on `feat/TASK-017-safe-local-app-demo`, cut from `ccd7d44`. **No existing
commit was amended or rewritten.** Commit 5 touches only `docs/`; its SHA cannot
be printed inside itself, so it is identified by position and resolvable with
`git log --oneline ccd7d44..HEAD`.

Code and documentation are kept in separate commits, as in previous tasks: 2 and
3 change implementation, 1, 4, and 5 are documentation only.

## Changed files

At commit 4 (the last commit touching `platform/`):

> **36 files changed, 3563 insertions(+), 22 deletions(-)**
> (`git diff --shortstat ccd7d44..97697d4`)

The final `HEAD` adds this handoff on top; it is documentation only.

Only **four** pre-existing files have deletions, and every deletion is a
rewrite-in-place rather than a removal of behaviour:

| File | + | - | What the deletions are |
| --- | --- | --- | --- |
| `apps/mobile/src/lib/supabase/environment.ts` | 125 | 19 | the URL/key checks, restructured into mode-aware helpers |
| `apps/mobile/README.md` | 24 | 1 | one sentence reworded from "local work" to "hosted work" |
| `platform/package.json` | 8 | 1 | the `db:status` line, re-emitted with a trailing comma |
| `apps/mobile/src/lib/supabase/client.ts` | 8 | 1 | the `readPublicSupabaseEnvironment()` call, now passed `isAndroid` |

New files: 22 under `platform/tooling/local-demo/`, one fixture at
`platform/supabase/fixtures/local-demo.sql`, `docs/app/LOCAL-DEMO.md`, the
packet, and this handoff.

**Nothing else changed.** No migration, policy, grant, function, view, or pgTAP
file; no `config.toml`; no `database.types.ts`; no `pnpm-lock.yaml`,
`pnpm-workspace.yaml`, dependency, or Expo version; no existing auth, athlete
check-in, sharing, profile, coach, component, theme, or navigation file; no
protected legacy path; **no `.env.local`**.

## Acceptance status

| # | Criterion | Status |
| --- | --- | --- |
| 1 | Repeated reset gives 2 profiles, 1 team, 2 active memberships, 0 grants, 0 check-ins | **met** — `demo:reset` run **four** times, byte-identical counts each time; the reset verifies the baseline itself and refuses to write credentials if it does not match |
| 2 | Both accounts authenticate through real local Auth | **met** — created via `POST /auth/v1/signup`, signed in via `POST /auth/v1/token?grant_type=password`, both asserted in `demo:verify:consent` |
| 3 | Athlete routes to athlete area, coach to coach area | **met at the data layer**, which is where routing is decided — each account returns exactly one active membership of the expected role from `team_memberships` under RLS. **The rendered navigation was not clicked through by me**; see limitation 1 |
| 4 | Coach cannot read the check-in before consent | **met** — asserted, count 0 |
| 5 | Coach sees the check-in after an explicit grant | **met** — asserted, count 1 |
| 6 | Coach loses access after revoke; athlete keeps self-access | **met** — asserted, 0 and 1 respectively, on the very next query with no re-authentication |
| 7 | No hosted endpoint contacted | **met** — every CLI call carries `--local`; a source scan asserts no `--linked`, `--db-url`, `supabase.co`, `db push`, `db pull`, `link`, or `login` appears anywhere in the tooling |
| 8 | No raw credential, password, token, user id, health value, Auth response, database error, or credential-bearing CLI output in logs, tests, terminal, or artifacts | **met** — see the privacy section; enforced by tests, not only by care |
| 9 | Existing cross-team and other-athlete authorization tests remain authoritative | **met** — unchanged; pgTAP re-run at the exact 5 files / 583 assertions baseline |
| 10 | No automatic consent, no seeded health data | **met** — the fixture inserts neither and deletes from both tables; asserted by a scan of the SQL |
| 11 | No new dependency, migration, RLS policy, or client provisioning capability | **met** — frozen lockfile unchanged; tooling uses Node built-ins only |
| 12 | Launching never resets or reseeds implicitly | **met** — `demo:web`/`demo:android` refuse to start a stopped stack rather than bringing it up, and run no reset, fixture, or user creation |

## Verification results

Run from `platform/` unless noted. **All green.**

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 — "Already up to date"; lockfile unchanged |
| `corepack pnpm format:check` | exit 0 — all files match |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test:tooling` | exit 0 — **25 suites, 210 tests, 0 failures** |
| `corepack pnpm test` | exit 0 — **40 test files, 790 tests, 0 failures** |
| `corepack pnpm demo:reset` (x4) | exit 0 — identical baseline every time |
| `corepack pnpm demo:verify` | exit 0 — baseline verified |
| `corepack pnpm demo:verify:consent` | exit 0 — **9/9 checks passed** |
| `supabase db reset --local --no-seed` | exit 0 — 4 migrations, no seed |
| `supabase test db --local` | exit 0 — **5 files, 583 assertions, `Result: PASS`** |
| `supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0 — **0 findings** |
| `expo export -p web` (from `apps/mobile/`) | exit 0 — **13 static routes**, unchanged |
| `expo export -p android` (from `apps/mobile/`) | exit 0 — 1 bundle, 1 metadata file |
| `expo-doctor@latest` (from `apps/mobile/`) | exit 1 — **20/21**, exactly the recorded baseline; the single failure is the known pre-existing patch drift |
| `git diff --check` | exit 0 (CRLF advisories only, normal on Windows) |
| `corepack pnpm demo:stop` | exit 0 |
| Supabase containers after stop, running / including stopped | **0 / 0** |
| Final worktree status | **clean** |

Mobile suite baseline was **748** (TASK-016); it is **790** now. The 42 added
tests are all in `environment.test.ts`. No existing test was modified or removed.

pgTAP counts match the TASK-014/016 baseline exactly — 5 files, 583 assertions, 0
lint findings — which is the expected outcome, because this task changed no
`platform/supabase/migrations/` or `tests/` file.

Two benign notices appeared in the pgTAP output and are pre-existing and
unrelated: `extension "pgtap" already exists, skipping`, and one
`WARNING: no privileges were granted for "pg_temp_2"` from
`005_daily_check_ins_rls_test.sql`.

The CLI again advised that `v2.110.0` is available (installed `v2.109.1`). **No
upgrade was performed** — the pin lives in `platform/package.json`, and changing
a dependency is out of scope even though this task owns that file's scripts.

### The consent verification, in full

`demo:verify:consent` is a **destructive** verification that brackets itself with
a full reset at both ends, so it always leaves the decision-9 baseline behind —
including on failure, via a best-effort restore in the catch handler.

```text
pass  athlete authenticates through real local Auth        expected true, got true
pass  coach authenticates through real local Auth          expected true, got true
pass  athlete holds exactly one active athlete membership  expected 1, got 1
pass  coach holds exactly one active coach membership      expected 1, got 1
pass  athlete reads their own check-in                     expected 1, got 1
pass  coach CANNOT read the check-in before consent        expected 0, got 0
pass  coach reads the check-in after the grant             expected 1, got 1
pass  coach loses access on the next query                 expected 0, got 0
pass  athlete keeps self-access after revoke               expected 1, got 1
```

Every assertion is a **row count**. The reads request `select=id`, so RPE,
feeling, and pain values never enter the verification process at all — not into a
variable, not into an assertion, not into a failure message.

### Baseline, as printed by the reset

```text
auth_users                   2
example_test_users           2
profiles                     2
named_profiles               2
teams                        1
active_memberships           2
active_athlete_memberships   1
active_coach_memberships     1
sharing_grants               0
daily_check_ins              0
```

### Credential discipline during verification

`supabase start` and `supabase stop` ran with all three streams discarded at the
OS level. `supabase status` was run **only** through the credential filter, whose
captured stdout never leaves that module. `--linked`, a project ref, and a remote
database URL were **never** used.

While diagnosing the fixture failure below I did run one Supabase CLI command
directly and read its output. That output was a single sanitized error string
(`cannot insert multiple commands into a prepared statement`) and carried no
credential. When I probed the CLI's key format at the start of the session, I
deliberately printed only **booleans** — `prefix_ok=true`,
`matches_app_pattern=true` — and the key names of the status document, never a
value.

## Decision 5: the blocker condition did not fire

Decision 5 says to stop and report a blocker if the pinned CLI cannot supply the
publishable credential without exposing secret-bearing output. **It can.** The
pinned CLI `2.109.1` exposes `PUBLISHABLE_KEY` in the `sb_publishable_` format
and an `API_URL` of exactly `http://127.0.0.1:54321`, verified by shape without
printing either value.

The raw status document *is* secret-bearing — it carries `DB_URL`, `JWT_SECRET`,
`SECRET_KEY`, `SERVICE_ROLE_KEY`, and S3 credentials. The rule as written forbids
**printing or persisting** that output and requires that only the validated
publishable field cross the boundary, which is exactly what
`credential-filter.mjs` does: it is the only module that ever holds the document,
it reads two fields by name, and it returns a newly constructed frozen object. It
never spreads, merges, or rest-destructures the parsed document, so a future CLI
release adding a new secret cannot widen what escapes. No weakening of the rule
was needed.

If a future pin stops providing `PUBLISHABLE_KEY`, the filter **fails closed**
with an explicit refusal rather than falling back to `ANON_KEY`, which is a
legacy JWT.

## Two defects I introduced and fixed, disclosed in full

**1. The fixture could not be applied as written.** I first wrote
`local-demo.sql` with an explicit `begin; ... commit;` around a `DO` block and
two `DELETE` statements. `supabase db query --file` sends the file as a *single
prepared statement*, which cannot carry multiple commands, so the first real
`demo:reset` failed. Restructured into one atomic `DO` statement — which gives
the same all-or-nothing guarantee the transaction block was there for, since any
exception rolls back every write in it — and the source-safety test that asserted
`begin;`/`commit;` was rewritten to assert single-statement atomicity instead.

Worth noting for the reviewer: **the output suppression worked exactly as
designed here, and it cost me a diagnosis step.** The failure printed only
`local fixture application failed (exit code 1)`, and I recovered the real cause
by re-running the underlying CLI command manually, which is precisely the
workflow the error message and `LOCAL-DEMO.md` prescribe. That is the intended
trade, but it is a real ergonomic cost and you should decide whether you accept
it.

**2. My own source scan caught a genuine duplication.** `credentials-file.mjs`
restated `http://127.0.0.1:54321` as a literal instead of importing it. The
"only `endpoint.mjs` contains a literal Supabase endpoint" test failed, and the
module now imports `LOCAL_SUPABASE_URL`. This is the scan doing its job on its
author.

Three other initial test failures were **defects in my tests, not in the code**,
and are recorded so the counts are not mistaken for a clean first run: a
paren-matching regex that stopped inside `count(*)`; a scan that flagged the
English word "password" in reassuring prose (fixed by stripping string literals
while *keeping* `${...}` interpolations, which are the real risk); and a fake
child process that emitted `close` before its stream drained, modelling a race
that does not exist on a real `ChildProcess`.

**A NUL-byte scan was run**, given the TASK-016 history: **0 bytes across all 36
changed files**.

## Privacy and security impact

**Net exposure change: small and mostly negative.** This task adds no new data
path, no new query, and no new capability to the product. It adds a way to run
the existing product locally, plus one new secret-adjacent artifact.

- **Authorization is untouched.** No migration, policy, grant, or helper changed.
  `private.can_current_user_read_shared_data` remains the sole gate, and the
  consent verification exercises it rather than bypassing it.
- **No client provisioning capability was created.** The fixture writes
  `teams` and `team_memberships` as the **database owner**, which is only
  possible because no client role holds INSERT on either. That asymmetry is
  preserved deliberately: team administration is still not a client capability.
- **No authentication bypass.** Both accounts are created through the real public
  signup endpoint with the publishable key. No write into `auth.users`, no Auth
  Admin API, no service-role key, no demo login shortcut. Asserted by a scan of
  both the tooling and the fixture SQL.
- **The one new secret is the generated password.** 24 bytes from
  `crypto.randomBytes`, base64url. Written only to `platform/.local-demo/`, which
  is git-ignored (confirmed with `git check-ignore`), with mode `0600` where the
  platform honours it. Regenerated on every reset. **Never printed** — the reset
  prints only the repository-relative path, and a test asserts the string
  `password` is not even an identifier in `demo-reset.mjs`.
- **The credential file holds no key, token, or session** — asserted by test
  against `sb_publishable_`, `sb_secret_`, `eyJ`, `postgres://`, `access_token`,
  and `service_role`.
- **No health value is seeded, and the only ones that ever exist are synthetic**
  (RPE 5, feeling 3, pain none) inside the consent verification, for a few
  seconds, belonging to an account that cannot receive email, and deleted by the
  restore.
- **Baseline verification cannot read health data.** The query selects only
  `count(*)` aggregates; a test asserts it names no health column and no
  identifier column, and that every subquery is a count.
- **Subprocess output cannot leak.** `stdio: ignore` at the OS level for
  start/stop, and a failure carries only a label and a numeric exit code. Tested
  against a fake child that prints a database URL, a JWT secret, and a
  service-role key and *then* fails — including the `error.stack`, not just the
  message.
- **`.env.local` is never touched.** No dotenv path appears anywhere in the
  tooling (asserted), and `EXPO_NO_DOTENV=1` means Expo reads none during a demo.
- **No real data.** No `athletes/`, `team_data/`, `garmin/`, environment file,
  dump, or credential was read at any point.

**Test-output safety:** the tooling tests assert on booleans, counts, key names,
and fixed strings. Where a test must prove a value did *not* leak, it uses
synthetic stand-ins assembled from fragments (`["sb","secret",...].join("_")`) so
no line in the test files resembles a real credential to a secret scanner.

## Known limitations

1. **I did not click through the rendered app.** Acceptance criterion 3 is
   verified at the data layer — each account returns exactly one active
   membership of the expected role — and the route guards derive from exactly
   that data via `resolveAuthGate`. But I did not launch a browser or an emulator
   and observe the athlete landing on `/athlete` and the coach on `/coach`.
   Nor did I walk the grant/revoke flow through the real UI. **That walkthrough
   is the Product Owner's step**, per decision 9, and it is the one part of the
   acceptance criteria supported by inference rather than direct observation.
2. **`demo:web` and `demo:android` were not executed end to end.** They start a
   long-lived foreground dev server, which is not something I can meaningfully
   run to completion in this session. Their *configuration* is unit-tested
   (`buildDemoEnv`), the Expo CLI resolution is verified, and both exports build,
   but the launch path itself is untested at runtime. This is the most likely
   place for a residual defect, and the first thing to try.
3. **The Android emulator path is untested against a real emulator.** The
   `10.0.2.2` mapping is standard and the app-side platform gate is unit-tested,
   but no emulator was started.
4. **Output suppression costs diagnosis.** A failing command reports only an exit
   code by design, and recovering the cause means re-running the underlying CLI
   by hand. I hit this myself (defect 1 above). Documented in `LOCAL-DEMO.md`,
   but you should confirm you accept the trade.
5. **`demo:verify:consent` is destructive.** It resets at both ends. If it is
   interrupted between the grant and the restore — a hard kill, not an exception
   — a grant and a synthetic check-in survive until the next `demo:reset`.
6. **The credential file is protected by `.gitignore`, not by file permissions.**
   `mode: 0600` is set but Windows ignores it, so any local process running as
   the user can read the demo password. Acceptable for a local synthetic account;
   worth knowing it is not a secure store.
7. **The two demo accounts share one password.** Simpler for the Product Owner,
   and both are synthetic and local. It does mean the demo cannot model a
   per-account credential compromise.
8. **Known pre-existing Expo patch drift persists** and is out of scope: `expo`
   `56.0.17` vs expected `~56.0.18`, `expo-router` `56.2.16` vs `~56.2.17`. No
   dependency was changed. 20/21 checks pass.
9. **Supabase CLI `v2.110.0` is available; `v2.109.1` is pinned.** Not upgraded.
10. **`demo:stop` preserves the local volume**, so a later `db:start` restores
    whatever state the last reset left. If the pgTAP suite was the last thing to
    touch the database, the demo accounts will be gone and the credential file
    will be stale. I ran a final `demo:reset` before stopping, so the environment
    you inherit is a valid baseline — but the two commands can desynchronize, and
    the fix is always `demo:reset`.

## Rollback

Fully additive on a dedicated branch:

```text
git switch feat/mobile-foundation
git branch -D feat/TASK-017-safe-local-app-demo
```

`feat/mobile-foundation` is untouched at `ccd7d44`. No migration was added, no
remote state changed, no dependency moved, and no Supabase container remains.

Local artifacts outside Git, if you want them gone: `platform/.local-demo/`
(the credential file) and the local Docker volume, removable with
`corepack pnpm exec supabase stop --no-backup` — **note that this discards the
local database**, which is exactly why `demo:stop` never passes that flag.

To revert only the implementation and keep the documentation:
`git revert 60d0118 6df9417`.

## For the reviewer (GPT/Codex, read-only)

Suggested focus, highest value first:

1. **`credential-filter.mjs`.** This is the decision-5 boundary. The claim is
   that only two fields can ever escape. Check the "never spread or
   rest-destructure" property holds, and check the `readLocalCredentials` wrapper
   really does keep captured stdout unreachable.
2. **`environment.ts` local mode.** Is exact-equality allowlisting the right
   call versus structural URL parsing? I argue yes — no parser branch to get
   wrong — but it means a trailing slash is rejected, which is surprising if
   anyone ever sets the variable by hand.
3. **Whether `demo:web`/`demo:android` refusing to start a stopped stack is the
   behaviour you want.** I chose fail-fast so launching can never become a hidden
   rebuild. Auto-starting would be friendlier and would not reset anything, since
   `supabase start` is non-destructive. This is a genuine product call.
4. **`source-safety.test.mjs`.** These tests are only as good as their comment-
   and string-stripping. The stripper is deliberately conservative (whole-line
   `//` only, to avoid truncating `postgres://`). Look for a way to write a
   forbidden call that the stripper hides.
5. **The fixture's owner-level writes.** Confirm nothing there could become a
   client capability, and that the `DELETE` statements are reachable only by the
   owner.
6. **Limitation 1** — whether verifying routing at the data layer is enough for
   acceptance criterion 3, or whether that criterion should stay open until the
   Product Owner walks it in the UI. I lean toward the latter.
7. **`demo-verify-consent.mjs`.** Is bracketing with two full resets the right
   design, or should the consent verification be a pgTAP test instead? pgTAP
   would be transaction-scoped and non-destructive, but it would not exercise
   real Auth sign-in or PostgREST, which is the whole point of this one.

**Not done, deliberately:** no merge, push, deploy, publish, hosted-Supabase
link, remote migration, `db push`, branch deletion, worktree removal, or
`.env.local` access.
