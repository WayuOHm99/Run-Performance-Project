# TASK-017 handoff — Safe Local App Demo Environment and Synthetic Fixtures

Status: **Round 2 complete.** Every Codex round 1 finding is fixed, with a test
for each. All verification re-run, including the local database authorization
suite, a real end-to-end consent verification, and a live two-process test of the
new lock. Stopped for GPT/Codex read-only review. Not merged. Worktree not
removed.

**One acceptance criterion is deliberately still open — AC3.** See the acceptance
table. It is not "met at the data layer" any more; it is open until someone
observes the routing in a real Web or Android run.

Writer: **Claude Code** (sole writer)
Reviewer: **GPT/Codex** (read-only)
Product Owner: **Wayu**
AGY: **not used**

Task: `docs/app/tasks/TASK-017-safe-local-app-demo-environment.md`
Branch/worktree: `feat/TASK-017-safe-local-app-demo` in
`.claude/worktrees/task-017-safe-local-app-demo`

**No acceptance criterion was reworded, narrowed, or removed in this round.** The
packet is byte-identical to the approved version; the only thing that changed
about AC3 is that this report stopped claiming it.

## Checkpoint, re-verified at the start of this round

Permission settings are read at launch, and a previous session cannot vouch for a
later one, so the safety checks were re-run rather than carried forward.

| Check | Result |
| --- | --- |
| Approved base SHA | **pass** — branch still cut from `ccd7d4440b69be390fd6ed35a417006bd66c70ff` |
| Worktree canary denied **before any content** | **pass** — re-run this session; `Read` of `docs/app/permission-canary/WORKTREE-CANARY.md` by exact path returned "File is in a directory that is denied by your permission settings" with no file content |
| App deny rules active | **pass** — the canary denial is itself the proof the settings file is loaded and that the worktree wildcard resolves on this machine |
| Root coaching `CLAUDE.md` not loaded | **pass** — no `CLAUDE.md` content entered context |
| `.claude/rules/app-engineering.md` loaded | **pass** |
| Hosted Supabase MCP blocked | **pass** — `mcp__claude_ai_Supabase__*` was never called in this session |
| Task worktree clean before editing | **pass** |
| Main checkout intentional changes preserved | **pass** — see below |

Round 1 also recorded one deviation, unchanged and still true: the worktree was
created on the auto-generated branch `worktree-task-017-safe-local-app-demo`, and
the required branch `feat/TASK-017-safe-local-app-demo` was created **at the
approved base SHA** before any file was committed. The auto-generated branch still
exists, untouched; it was not deleted, and no history was rewritten in either
round.

**The same limitation of this report stands.** The contract asks for `/memory` and
`/permissions`. Those are built-in CLI commands and cannot be invoked from a tool
call, so they were not run. What is recorded above is the equivalent evidence
obtainable from inside the session — the canary denial, and the absence of any
`CLAUDE.md` content in context. If you want the literal command output, run them
yourself in a fresh session; I am not claiming to have run them.

### Main checkout intentional changes

Confirmed present and **untouched** throughout this round:

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

## Round 2: the findings and what was done

Nine findings, in the order they were raised. Each one is closed by code plus a
test that fails without the fix.

### 1. Malformed `response.json()` parse failures were printable

`await response.json()` surfaces `JSON.parse`'s own error, and that error quotes
its input verbatim — `Unexpected token 'x', "…" is not valid JSON`. A malformed
body is precisely the case where the body is most likely to be a PostgREST or
GoTrue error document carrying a database error string, a hint naming a column,
or a partially written session. So the one path that must never print a body was
the one that would have.

`api.mjs` now reads the body as text and parses it inside a `catch` that discards
the parse error entirely; the text goes out of scope unreferenced. New
`api.test.mjs` (17 tests) asserts the failure output — message, `stack`, cause
chain, and an own-property serialization — carries nothing from the body, for a
malformed body, an unreadable body, a well-formed body of the wrong shape, and
every non-ok status across all five request helpers.

### 2. A signal-terminated subprocess was read as a success

Node reports `code === null` when a child is killed by a signal, and
`resolve({ exitCode: code ?? 0 })` turned that into exit 0. A `supabase db reset`
killed part-way leaves a half-migrated database, and the reset pipeline would
have carried on, verified nothing meaningful, and written a credential file for a
baseline that was never built.

Results now carry `signal` alongside `exitCode`; a killed child reports
`SIGNAL_TERMINATION_EXIT_CODE` (128); `succeeded()` is the single definition of
success in the tooling and requires both a zero code and no signal. The signal
name reaches the failure message, so it goes through a shape check
(`/^SIG[A-Z0-9]{1,12}$/`) first — nothing else can arrive through that parameter.
Tests cover a killed child, a killed child that *also* reports code 0, a
non-signal value in the signal position, and the captured-stdout path the
credential filter depends on.

One documented exception: `demo:web`/`demo:android` treat `SIGINT`/`SIGTERM`/
`SIGHUP` on the foreground Expo dev server as a clean stop, because Ctrl-C is how
that process is meant to end.

### 3. Destructive workflows could interleave

Nothing stopped two `demo:reset` runs, or a `demo:stop` racing a reset. The
consequences are not theoretical:

- two resets interleaved leave a database built by one run and a credential file
  written by the other, so the recorded password does not open the accounts that
  exist;
- a reset landing between the consent verification's grant and its restore leaves
  a sharing grant and a synthetic check-in behind, which is exactly the decision-9
  violation the bracketing exists to prevent;
- a stop racing a reset kills the stack mid-migration.

New `lock.mjs`: an exclusive `open(..., "wx")` on `platform/.local-demo/demo.lock`,
which the OS resolves atomically, so two separate processes cannot both hold it.
It **fails fast rather than queueing** — a destructive command that waits silently
and fires minutes later, after the person who ran it has moved on, is worse than
one that refuses and says why. It detects a lock abandoned by a dead process
(pid liveness plus a 30-minute age bound), never assumes a lock written by another
host is dead, treats an unreadable lock file as abandoned, and is **reentrant
within one process** so `demo:verify:consent` can hold it across the resets it
calls, including its failure-path restore.

Taken by `demo:reset`, `demo:stop`, `demo:start`, and `demo:verify:consent`.
`demo:verify` is read-only and takes nothing.

**Verified live, not only in unit tests.** Two `demo:reset` processes were started
two seconds apart against the real stack:

```text
demo:reset failed — Another destructive demo command is already running
(demo:reset, pid 7140). Only one may touch the local demo at a time.
```

The second exited 1 without touching the database; the first completed and
produced the correct baseline.

### 4. AC3 was marked met on inference

It is now **open**. The data-layer evidence still exists and is still reported,
but it is not acceptance. Nobody has watched the athlete land on `/athlete` and
the coach on `/coach` in a running app, so nothing in this report says they did.

### 5. Exact health values and raw database-error text in committed artifacts

Two separate leaks of the same kind:

- `demo-verify-consent.mjs` hard-coded a check-in. A fixed reading committed to
  the repository is an exact health value in a committed artifact however
  synthetic it is, so the values are now generated at run time from the domain the
  schema already declares (RPE 0–10, feeling 1–5, pain none or present). What is
  committed is the domain, not a reading. A source scan asserts no module assigns
  a literal health value, and `api.test.mjs` follows the same rule for its own
  fixtures.
- This handoff quoted a raw database error string from the round 1 session, and
  restated the synthetic check-in's values. Both are gone. The diagnosis story is
  still told below, without the CLI's text.

The local verification is unchanged in what it proves: every assertion is still a
row count, and `countRows` still requests `select=id`, so no health column enters
the process at all.

### 6. Restart printed raw Supabase credentials

The tooling's own failure message, `demo-stop.mjs`, `LOCAL-DEMO.md`, and
`platform/README.md` all told the Product Owner to restart with `db:start` — which
is `supabase start`, which ends by printing the local database URL, the JWT
secret, the secret key, the service-role key, and S3 credentials into terminal
scrollback. Decision 5 forbids exactly that, and the tooling was routing around
its own rule by handing the job to the user.

New `demo:start`: the same non-destructive `supabase start`, run with all three
streams discarded at the OS level, followed by a status read through the
credential filter to confirm the stack is up and is the canonical local endpoint.
It resets nothing and reseeds nothing, so AC12 is unaffected; it takes the lock
briefly so it cannot race a reset. A source-safety test asserts no module mentions
`db:start` any more.

Verified live: the stack was stopped and cold-started through `demo:start`, and
the complete output contains **zero** matches for `service_role`, `jwt`, `secret`,
`postgresql://`, `anon key`, `sb_publishable_`, `sb_secret_`, or `S3`. The demo
data survived the stop/start intact.

### 7. Credential-file replacement could leave a stale or partial file

Two failures. **Stale:** a reset interrupted after the database was wiped left the
previous run's file in place, holding a password that no longer opened anything —
and the Product Owner would read it, fail to sign in, and have no way to tell
whether the demo or their typing was wrong. **Partial:** a direct `writeFile`
could publish a truncated file under the real name.

The file is now discarded *before* the destructive step and written only after the
baseline verifies, so it either describes the accounts that exist or does not
exist at all. The write goes to a pid-qualified temporary file, is flushed, and is
renamed over the target — atomic on POSIX and on Windows, where libuv uses
`MoveFileEx` with replace-existing. A leftover temporary file from an earlier
crash is cleared rather than trusted, and a failed rename removes it instead of
leaving it to be found later.

### 8. Credential-related test failures could leak

`credentials.test.mjs` rendered a **real generated password** into a file and then
asserted with `assert.match(contents, /…/)`. `assert.match` reports its input on
failure — so a single failing assertion would have printed the whole credential
file, password included, into CI output or a terminal. The test that existed to
protect the password was the thing most likely to print it.

Every assertion over a rendered credential file is now `assert.ok` with a fixed
message, which reports the message and nothing else, and the rendering tests use a
fixed synthetic stand-in assembled from fragments rather than a generated
password. One test still proves a generated password reaches the file; it reports
only whether it did.

### 9. Stale documentation

`LOCAL-DEMO.md` and `platform/README.md` described a four-command tooling that no
longer matches, pointed at `db:start`, and said nothing about the lock, the
credential file's new lifecycle, or what a signal-termination message means. Both
are updated. `SUPABASE-ENVIRONMENT.md`, `apps/mobile/README.md`, and
`.env.example` were re-read and are still accurate — the endpoint contract did not
change this round.

## Commits

| # | SHA | Subject |
| --- | --- | --- |
| 1 | `d8e585bc8129278dd77c8f09e08aab53bf245c66` | `docs(task-017): add the safe local app demo packet` |
| 2 | `6df94175afbb3995b8dd3020218cabdf4cbbe1b9` | `feat(supabase): add a fail-closed local endpoint mode to the client` |
| 3 | `60d01180624126d7465abddeafe4550f9b0e1ac1` | `feat(demo): add local-only demo commands and a synthetic fixture` |
| 4 | `97697d49a088359e5a1d7f7dc3da5ba9a71c3b85` | `docs(task-017): document the local demo workflow and endpoint contract` |
| 5 | `5267856` | `docs(task-017): record the implementation handoff` |
| 6 | `2a7b2d5` | `fix(demo): close the Codex round 1 findings in the demo tooling` |
| 7 | `b2547ec` | `docs(task-017): document demo:start, the lock, and the stale-file rule` |
| 8 | *this commit* | `docs(task-017): record the round 2 review response` |

All on `feat/TASK-017-safe-local-app-demo`, cut from `ccd7d44`. **No existing
commit was amended, rebased, or rewritten in this round** — round 2 is additive on
top of round 1, so the review history stays legible. Commit 8 touches only
`docs/`; its SHA cannot be printed inside itself, and is resolvable with
`git log --oneline ccd7d44..HEAD`.

## Changed files

Round 2 alone:

> **20 files changed, 1639 insertions(+), 85 deletions(-)**
> (`git diff --shortstat 5267856..HEAD`, before this handoff commit)

Whole branch against the approved base:

> **41 files changed, 5551 insertions(+), 22 deletions(-)**
> (`git diff --shortstat ccd7d44..HEAD`)

New in round 2: `tooling/local-demo/lock.mjs`, `lock.test.mjs`, `api.test.mjs`,
`demo-start.mjs`. Changed: `api.mjs`, `subprocess.mjs`, `subprocess.test.mjs`,
`credential-filter.mjs`, `credentials-file.mjs`, `credentials.test.mjs`,
`launch.mjs`, `paths.mjs`, `reset.mjs`, `demo-stop.mjs`,
`demo-verify-consent.mjs`, `supabase-cli.mjs`, `source-safety.test.mjs`,
`package.json` (one script line), `docs/app/LOCAL-DEMO.md`, `platform/README.md`.

**Nothing else changed, in either round.** No migration, policy, grant, function,
view, or pgTAP file; no `config.toml`; no `database.types.ts`; no
`pnpm-lock.yaml`, `pnpm-workspace.yaml`, dependency, or Expo version; no existing
auth, athlete check-in, sharing, profile, coach, component, theme, or navigation
file; no protected legacy path; **no `.env.local`**. The round 2 work is confined
to `platform/tooling/local-demo/`, one `package.json` script, and two documents.

## Acceptance status

| # | Criterion | Status |
| --- | --- | --- |
| 1 | Repeated reset gives 2 profiles, 1 team, 2 active memberships, 0 grants, 0 check-ins | **met** — `demo:reset` run repeatedly across both rounds, byte-identical counts each time; the reset verifies the baseline itself and refuses to write credentials if it does not match |
| 2 | Both accounts authenticate through real local Auth | **met** — created via `POST /auth/v1/signup`, signed in via `POST /auth/v1/token?grant_type=password`, both asserted in `demo:verify:consent` |
| 3 | Athlete routes to athlete area, coach to coach area | **OPEN — not claimed.** Each account returns exactly one active membership of the expected role from `team_memberships` under RLS, and the route guards derive from exactly that data via `resolveAuthGate`. But **no one has observed the rendered routing**: no browser, no emulator, no sign-in. This criterion stays open until a real Web or Android run shows the athlete landing on `/athlete` and the coach on `/coach` |
| 4 | Coach cannot read the check-in before consent | **met** — asserted, count 0 |
| 5 | Coach sees the check-in after an explicit grant | **met** — asserted, count 1 |
| 6 | Coach loses access after revoke; athlete keeps self-access | **met** — asserted, 0 and 1 respectively, on the very next query with no re-authentication |
| 7 | No hosted endpoint contacted | **met** — every CLI call carries `--local`; a source scan asserts no `--linked`, `--db-url`, `supabase.co`, `db push`, `db pull`, `link`, or `login` appears anywhere in the tooling |
| 8 | No raw credential, password, token, user id, health value, Auth response, database error, or credential-bearing CLI output in logs, tests, terminal, or artifacts | **met, and materially stronger than in round 1** — findings 1, 5, 6, and 8 were all violations of this criterion and are all closed. See the privacy section |
| 9 | Existing cross-team and other-athlete authorization tests remain authoritative | **met** — unchanged; pgTAP re-run at the exact 5 files / 583 assertions baseline |
| 10 | No automatic consent, no seeded health data | **met** — the fixture inserts neither and deletes from both tables; asserted by a scan of the SQL. The lock now also protects the zero-consent baseline against a concurrent reset landing mid-verification |
| 11 | No new dependency, migration, RLS policy, or client provisioning capability | **met** — frozen lockfile unchanged; the lock and the atomic file replacement use Node built-ins only |
| 12 | Launching never resets or reseeds implicitly | **met** — `demo:web`/`demo:android` still refuse to start a stopped stack rather than bringing it up, and run no reset, fixture, or user creation. `demo:start` starts the stack and nothing else: no reset, no fixture, no user, no write |

## Verification results

Run from `platform/` unless noted. **All green.**

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 — "Already up to date"; lockfile unchanged |
| `corepack pnpm format:check` | exit 0 — all files match |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test:tooling` | exit 0 — **38 suites, 293 tests, 0 failures** (round 1: 210) |
| `corepack pnpm test` | exit 0 — **40 test files, 790 tests, 0 failures**, unchanged |
| `corepack pnpm demo:reset` | exit 0 — identical baseline every time |
| `corepack pnpm demo:verify` | exit 0 — baseline verified |
| `corepack pnpm demo:verify:consent` | exit 0 — **9/9 checks passed** |
| Two concurrent `demo:reset` processes | **second refused, exit 1**, first completed correctly |
| `corepack pnpm demo:stop` → cold `corepack pnpm demo:start` | exit 0 — **0** credential-shaped fragments in the output; demo data intact afterwards |
| `supabase db reset --local --no-seed` | exit 0 — 4 migrations, no seed |
| `supabase test db --local` | exit 0 — **5 files, 583 assertions, `Result: PASS`** |
| `supabase db lint --local --schema public,private --level warning --fail-on warning` | exit 0 — **0 findings** |
| `expo export -p web` (from `apps/mobile/`) | exit 0 — **13 static routes**, unchanged |
| `expo export -p android` (from `apps/mobile/`) | exit 0 — 1 bundle, 1 metadata file |
| `expo-doctor@latest` (from `apps/mobile/`) | exit 1 — **20/21**, exactly the recorded baseline; the single failure is the known pre-existing patch drift |
| `git diff --check` | exit 0 (CRLF advisories only, normal on Windows) |
| NUL-byte scan across all changed files | **0 bytes** |
| Supabase containers after `demo:stop`, running / including stopped | **0 / 0** |
| Final worktree status | **clean** |

The tooling suite grew from 210 to 293 tests: 17 in the new `api.test.mjs`, 21 in
the new `lock.test.mjs`, and the rest in the credential-file, subprocess, and
source-safety suites. **No existing test was deleted**; several were rewritten to
stop leaking on failure or to reflect the new result shape, and each such rewrite
is described under the finding that caused it.

pgTAP counts match the TASK-014/016 baseline exactly — 5 files, 583 assertions, 0
lint findings — which is the expected outcome, because neither round changed a
`platform/supabase/migrations/` or `tests/` file.

The same two benign pre-existing notices appeared in the pgTAP output:
`extension "pgtap" already exists, skipping`, and one
`WARNING: no privileges were granted for "pg_temp_11"` from
`005_daily_check_ins_rls_test.sql`.

The CLI advised that `v2.111.0` is available (installed `v2.109.1`). **No upgrade
was performed** — the pin lives in `platform/package.json`, and changing a
dependency is out of scope even though this task owns that file's scripts.

### The consent verification, in full

`demo:verify:consent` is a **destructive** verification that brackets itself with
a full reset at both ends, so it always leaves the decision-9 baseline behind —
including on failure, via a best-effort restore. In round 2 the whole workflow,
including that restore, holds the destructive-workflow lock.

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

Every assertion is a **row count**. The reads request `select=id`, so no health
column enters the verification process at all — not into a variable, not into an
assertion, not into a failure message. The check-in's values are generated at run
time, are never printed, and are not recorded anywhere, including here.

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
database URL were **never** used, in either round.

Round 1 disclosed that one Supabase CLI command had been run directly and its
output read while diagnosing the fixture defect below. That is still true and is
still worth knowing; the error text itself has been removed from this document,
because a database error string is exactly the class of value AC8 covers and
there is no reason for it to live in a committed artifact. It carried no
credential.

## Decision 5: the blocker condition did not fire

Decision 5 says to stop and report a blocker if the pinned CLI cannot supply the
publishable credential without exposing secret-bearing output. **It can.** The
pinned CLI `2.109.1` exposes `PUBLISHABLE_KEY` in the `sb_publishable_` format and
an `API_URL` of exactly the canonical local endpoint, verified by shape without
printing either value.

The raw status document *is* secret-bearing. The rule as written forbids
**printing or persisting** that output and requires that only the validated
publishable field cross the boundary, which is what `credential-filter.mjs` does:
it is the only module that ever holds the document, it reads two fields by name,
and it returns a newly constructed frozen object. It never spreads, merges, or
rest-destructures the parsed document, so a future CLI release adding a new secret
cannot widen what escapes. No weakening of the rule was needed.

Round 2 strengthened one edge of this boundary: a `supabase status` call that is
killed part-way now fails as a subprocess failure rather than being parsed as a
truncated document.

If a future pin stops providing `PUBLISHABLE_KEY`, the filter **fails closed**
with an explicit refusal rather than falling back to `ANON_KEY`, which is a legacy
JWT.

## Defects I introduced and fixed, disclosed in full

**Round 1, defect 1 — the fixture could not be applied as written.**
`local-demo.sql` was first written with an explicit `begin; … commit;` around a
`DO` block and two `DELETE` statements. `supabase db query --file` sends the file
as a *single prepared statement*, which cannot carry multiple commands, so the
first real `demo:reset` failed. Restructured into one atomic `DO` statement —
which gives the same all-or-nothing guarantee, since any exception rolls back
every write in it — and the source-safety test that asserted `begin;`/`commit;`
was rewritten to assert single-statement atomicity instead.

Worth noting for the reviewer: **the output suppression worked exactly as designed
there, and it cost a diagnosis step.** The failure printed only
`local fixture application failed (exit code 1)`, and the real cause was recovered
by re-running the underlying CLI command by hand, which is precisely the workflow
the error message and `LOCAL-DEMO.md` prescribe. That is the intended trade, but
it is a real ergonomic cost and you should decide whether you accept it.

**Round 1, defect 2 — my own source scan caught a genuine duplication.**
`credentials-file.mjs` restated the local endpoint as a literal instead of
importing it. The "only `endpoint.mjs` contains a literal Supabase endpoint" test
failed, and the module now imports `LOCAL_SUPABASE_URL`.

**Round 1, defects 3–5 — three initial test failures were defects in my tests,
not in the code**, and are recorded so the counts are not mistaken for a clean
first run: a paren-matching regex that stopped inside `count(*)`; a scan that
flagged the English word "password" in reassuring prose (fixed by stripping string
literals while *keeping* `${…}` interpolations, which are the real risk); and a
fake child process that emitted `close` before its stream drained, modelling a
race that does not exist on a real `ChildProcess`.

**Round 2 introduced no defect that needed a second fix.** Every change landed
against a test written for it, and the full suite was re-run after each. What
round 2 *did* establish is that five of the nine findings — 1, 5, 6, 8, and the
credential-file half of 7 — were violations of acceptance criterion 8 that my own
round 1 report claimed as met. The scans I wrote did not catch them because they
scan for *forbidden identifiers in source*, and every one of these leaks was a
value arriving at run time through a standard-library error message. That is the
gap a reviewer found and a scan could not.

## Privacy and security impact

**Net exposure change: small, and smaller after round 2 than before it.** This
task adds no new data path, no new query, and no new capability to the product. It
adds a way to run the existing product locally, plus one new secret-adjacent
artifact.

- **Authorization is untouched.** No migration, policy, grant, or helper changed.
  `private.can_current_user_read_shared_data` remains the sole gate, and the
  consent verification exercises it rather than bypassing it.
- **No client provisioning capability was created.** The fixture writes `teams`
  and `team_memberships` as the **database owner**, which is only possible because
  no client role holds INSERT on either. That asymmetry is preserved deliberately.
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
- **The credential file cannot be stale or partial** (round 2). Discarded before
  the destructive step, written atomically by rename only after the baseline
  verifies. It either describes the accounts that exist or does not exist.
- **The credential file holds no key, token, or session** — asserted by test
  against `sb_publishable_`, `sb_secret_`, `eyJ`, `postgres://`, `access_token`,
  and `service_role`.
- **The lock file holds no secret either** — pid, hostname, command label, and a
  timestamp, asserted by test, in the same git-ignored directory.
- **No health value is written down anywhere** (round 2). None is seeded; the only
  ones that ever exist are generated at run time inside the consent verification,
  live for a few seconds, belong to an account that cannot receive email, are
  deleted by the restoring reset, and are recorded in no file, no log, and no
  report.
- **Baseline verification cannot read health data.** The query selects only
  `count(*)` aggregates; a test asserts it names no health column and no
  identifier column, and that every subquery is a count.
- **Subprocess output cannot leak, and a killed subprocess cannot be mistaken for
  a completed one** (round 2). `stdio: ignore` at the OS level for start/stop; a
  failure carries a label, a numeric exit code, and at most a shape-checked signal
  name. Tested against a fake child that prints a database URL, a JWT secret, and
  a service-role key and *then* fails or is killed — including `error.stack`.
- **Response bodies cannot leak through a parse error** (round 2). See finding 1.
- **The restart path prints no credential block** (round 2). See finding 6;
  verified live against a cold start.
- **Test failures cannot leak** (round 2). No assertion that prints its input is
  applied to a rendered credential file, and the rendering tests use a fixed
  synthetic stand-in rather than a generated password.
- **`.env.local` is never touched.** No dotenv path appears anywhere in the
  tooling (asserted), and `EXPO_NO_DOTENV=1` means Expo reads none during a demo.
- **No real data.** No `athletes/`, `team_data/`, `garmin/`, environment file,
  dump, or credential was read at any point, in either round.

**Test-output safety:** the tooling tests assert on booleans, counts, key names,
and fixed strings. Where a test must prove a value did *not* leak, it uses
synthetic stand-ins assembled from fragments (`["sb","secret",…].join("_")`) so no
line in the test files resembles a real credential to a secret scanner.

## Known limitations

1. **Acceptance criterion 3 is open, not met.** I did not launch a browser or an
   emulator, did not sign in, and did not observe the rendered routing. The route
   guards derive from the membership data the consent verification does check, but
   that is an inference and it is not what AC3 asks for. **This is the Product
   Owner's step**, and it is the one criterion this branch cannot close on its own.
2. **`demo:web` and `demo:android` were not executed end to end.** They start a
   long-lived foreground dev server, which is not something I can meaningfully run
   to completion in this session. Their configuration is unit-tested
   (`buildDemoEnv`), the Expo CLI resolution is verified, both exports build, and
   the credential read they depend on is now exercised live by `demo:start` — but
   the launch path itself is still untested at runtime. This remains the most
   likely place for a residual defect, and the first thing to try.
3. **The Android emulator path is untested against a real emulator.** The
   `10.0.2.2` mapping is standard and the app-side platform gate is unit-tested,
   but no emulator was started.
4. **Output suppression costs diagnosis.** A failing command reports only a label,
   an exit code, and possibly a signal, by design; recovering the cause means
   re-running the underlying CLI by hand. Documented in `LOCAL-DEMO.md`, but you
   should confirm you accept the trade.
5. **`demo:verify:consent` is still destructive, and a hard kill still leaves
   rows.** The lock closes the concurrency hole — no other demo command can now
   interleave with it — but if the process itself is killed between the grant and
   the restore, a grant and a synthetic check-in survive until the next
   `demo:reset`. A lock cannot fix that; only the process finishing can.
6. **The credential file is protected by `.gitignore`, not by file permissions.**
   `mode: 0600` is set but Windows ignores it, so any local process running as the
   user can read the demo password. Acceptable for a local synthetic account;
   worth knowing it is not a secure store. The same is true of the lock file,
   which holds nothing sensitive.
7. **The two demo accounts share one password.** Simpler for the Product Owner,
   and both are synthetic and local. It does mean the demo cannot model a
   per-account credential compromise.
8. **The lock is only honoured by this tooling.** Running `supabase db reset` or
   `supabase stop` directly bypasses it entirely, and so does the pgTAP suite —
   which is exactly what desynchronizes the credential file from the database (see
   limitation 10). A cooperative lock cannot bind a command that never asks for it.
9. **Known pre-existing Expo patch drift persists** and is out of scope: `expo`
   `56.0.17` vs expected `~56.0.18`, `expo-router` `56.2.16` vs `~56.2.17`. No
   dependency was changed. 20/21 checks pass.
10. **Supabase CLI `v2.111.0` is available; `v2.109.1` is pinned.** Not upgraded.
11. **`demo:stop` preserves the local volume**, so a later `demo:start` restores
    whatever state the last reset left. If the pgTAP suite was the last thing to
    touch the database, the demo accounts will be gone and the credential file
    will be stale in a way the tooling cannot detect, because the wipe did not go
    through it. I ran a final `demo:reset` before stopping, so the environment you
    inherit is a valid baseline — but the commands can desynchronize, and the fix
    is always `demo:reset`.
12. **Docker Desktop was not running when this session began, and I started it**
    to run the local suites. It is **still running**; quitting it is a machine-wide
    action I left to you. No Supabase container is running.

## Rollback

Fully additive on a dedicated branch:

```text
git switch feat/mobile-foundation
git branch -D feat/TASK-017-safe-local-app-demo
```

`feat/mobile-foundation` is untouched at `ccd7d44`. No migration was added, no
remote state changed, no dependency moved, and no Supabase container remains.

Local artifacts outside Git, if you want them gone: `platform/.local-demo/` (the
credential file and the lock) and the local Docker volume, removable with
`corepack pnpm exec supabase stop --no-backup` — **note that this discards the
local database**, which is exactly why `demo:stop` never passes that flag.

To revert only round 2 and keep round 1: `git revert b2547ec 2a7b2d5`. To revert
the implementation and keep the documentation: `git revert 60d0118 6df9417`.

## For the reviewer (GPT/Codex, read-only)

Round 1's focus list still stands. What is new and worth your attention first:

1. **`lock.mjs`.** Fail-fast versus queueing is a genuine product call, and I chose
   refusal. Also check the staleness rule: a lock is taken over only when its
   record is unusable, or its owner is not running *and* it was written by this
   host, or it is older than 30 minutes. Is 30 minutes right for a cold
   `supabase start` on a slow machine? Too short and a live reset gets its lock
   stolen; too long and an abandoned lock blocks work.
2. **The reentrancy counter.** It is process-local module state. Confirm there is
   no path where `depth` can be left above zero after a throw, which would leak the
   lock file for the life of the process.
3. **`parseJsonBody` in `api.mjs`.** The claim is that neither the body nor any
   substring reaches a caller. Look for a path where the text could still be
   referenced — a cause chain, a rethrow, a future `error.detail`.
4. **The signal rule.** `succeeded()` is now the only definition of success.
   Confirm every call site uses it, and judge whether `launch.mjs` treating
   `SIGINT`/`SIGTERM`/`SIGHUP` as a clean stop is the right exception or a hole.
5. **Whether `demo:start` is the right answer to finding 6**, or whether
   `demo:web`/`demo:android` should simply start a stopped stack themselves. I kept
   fail-fast so launching can never become a hidden rebuild, and added an explicit
   safe command instead — but auto-starting would be friendlier and would still
   reset nothing.
6. **Whether generating health values at run time is the right reading of AC8**,
   or whether a fixed synthetic constant was always acceptable and this is
   over-correction. I lean toward generation: it makes the property structural
   rather than a matter of which constant someone picked.
7. **`source-safety.test.mjs`.** Still only as good as its comment- and
   string-stripping, and round 2 added more scans that depend on it. Look for a way
   to write a forbidden call that the stripper hides.

**Not done, deliberately:** no merge, push, deploy, publish, hosted-Supabase link,
remote migration, `db push`, branch deletion, worktree removal, or `.env.local`
access. No acceptance criterion was reworded, and AC3 is left open rather than
argued into met.
