# TASK-017 handoff — Safe Local App Demo Environment and Synthetic Fixtures

Status: **Round 3 complete.** Every Codex finding from rounds 1 and 2 is fixed,
with a test for each. All verification re-run, including the local database
authorization suite, a real end-to-end consent verification, and live
multi-process tests of the redesigned lock. Stopped for GPT/Codex read-only
review. Not merged. Worktree not removed.

**One acceptance criterion is deliberately still open — AC3.** See the acceptance
table. It is not "met at the data layer" any more; it stays open until the
Product Owner observes the routing in a real Web or Android walkthrough.

Writer: **Claude Code** (sole writer)
Reviewer: **GPT/Codex** (read-only)
Product Owner: **Wayu**
AGY: **not used**

Task: `docs/app/tasks/TASK-017-safe-local-app-demo-environment.md`
Branch/worktree: `feat/TASK-017-safe-local-app-demo` in
`.claude/worktrees/task-017-safe-local-app-demo`

**No acceptance criterion was reworded, narrowed, or removed in any round.** The
packet is byte-identical to the approved version; the only thing that changed
about AC3 is that this report stopped claiming it.

## Approved scope deviation: `demo:start` is a fifth demo command

The packet's in-scope list names **four** commands — `demo:reset`, `demo:web`,
`demo:android`, `demo:stop`. Round 2 added a fifth, `demo:start`, to close a
finding: every restart route the tooling offered went through `db:start`, which
ends by printing the local database URL, the JWT secret, the secret key, the
service-role key, and S3 credentials into terminal scrollback. Decision 5 forbids
printing that output, and the tooling was satisfying the letter of the rule by
handing the job to the person running it.

**The Product Owner has approved this deviation.** `demo:start` stays, on the
stated grounds that it safely replaces credential-printing `db:start`. It is the
only addition to the command surface, it is non-destructive — no reset, no
fixture, no user, no write — and AC12 is unaffected: starting a stopped stack is
not reseeding it. The packet's in-scope list is left as approved rather than
edited to match; this section is the record.

## Round 3: the findings and what was done

Four findings, all from the round 2 lock and the guidance around it. Round 2
fixed a real concurrency hole and introduced a smaller one of its own; this round
closes it properly.

### 1. The lock did not actually provide mutual exclusion

Two defects in one mechanism, and the second is the serious one.

**Age was treated as proof.** Any lock older than thirty minutes was broken even
when its owner was demonstrably running. A cold `supabase start` followed by a
reset on a slow machine can pass that mark, and the reward for being slow was
having the lock taken away mid-migration. Age is now not consulted at all, and a
scan asserts `lock.mjs` contains no timestamp arithmetic. Being slow is not
evidence of being dead.

**Read-then-delete was a race that could delete a *live* lock.** Between reading
a lock, deciding it was stale, and unlinking it, another process could break the
same stale lock and acquire a live one — which this process then removed. Both
then ran, and the holder never found out. That is worse than having no lock: the
holder keeps working believing it is protected.

The redesign:

- Mutual exclusion comes from exactly one thing, `open(lockFile, "wx")`, which the
  OS resolves atomically.
- A lock is breakable **only** when its owning process is gone — proven by
  `kill(pid, 0)` — and only for a lock this host wrote. A lock from another host
  is never assumed dead. An unusable record is breakable because it names no
  owner at all.
- Breaking is serialized by its own exclusively created claim file,
  `demo.lock.break`. The claim holder re-reads the lock and requires the
  **identical nonce** it proved abandoned before unlinking anything.
- That is sound rather than merely careful: the owner is already proven dead, a
  dead process cannot release its own lock, and only the single claim holder may
  unlink — so nothing can change the lock file inside that window.
- The claim file is **never broken automatically**. It is held for milliseconds
  and removed in a `finally`, so a survivor means a hard kill inside that window;
  every command then refuses and names the one file to delete. Refusing is
  recoverable in one command, and automatic claim recovery would reintroduce the
  race the claim exists to remove.

Tests drive the concurrent paths through injected `isAlive` and an `onBreakWindow`
seam rather than by starting processes and hoping the timing lands, so each
interleaving is exactly the one the test asks for:

- a lock re-taken inside the recovery window survives, with its own nonce intact;
- a second recovery refuses while another holds the claim, touching neither the
  claim nor the lock;
- an owner that looks dead and then alive during recovery causes a refusal;
- **a live lock four times older than thirty minutes is honoured**, and is still
  byte-identical afterwards.

Two further tests use a **real child process**, because an in-process second
caller would take the reentrant path and prove nothing: a separate process is
refused while this one holds the lock, and a separate process does recover a lock
whose owner is genuinely gone.

### 2. An untrusted label from the lock file reached an error message

The lock file is ordinary writable state on disk, so everything read back out of
it is untrusted input — and `record.label` was interpolated into the conflict
message verbatim. Anything a file could contain, a message could print.

The label now reaches a message only by matching one of the four labels this
tooling itself writes; anything else becomes a fixed fallback. The hostname is
never echoed, and the pid only after validating it is a positive integer. A test
writes a credential-shaped sentinel as the label and asserts it appears in no
message, stack, cause, or serialized property — and a live run against a lock
carrying that sentinel printed `(a demo command, pid 19128)` with **zero**
occurrences of the sentinel.

### 3. Credential temporary files outlived the process that wrote them

Round 2 cleaned only the current process's own pid-qualified temporary file. A
run killed between the write and the rename therefore left a file that nothing
would ever remove: it is not the credential file, so no reset replaced it, and it
carried the password that run had generated. Cleaning only the current pid made
that permanent.

Cleanup now removes every file matching the exact
`credentials.txt.<digits>.tmp` shape in the ignored `.local-demo/` directory,
whatever process wrote it. The scan is confined to that directory — `readdir`
returns bare entry names, so nothing can reach outside it — no file is opened, no
content is read, and nothing is printed. Tests cover a different simulated pid, a
directory of bystander files that must survive, and a same-shaped file one
directory away that must not be touched.

Deleting another run's temporary file is safe because writing one happens only
inside the destructive-workflow lock, so no other run can have one in flight.

### 4. Guidance still pointed at raw, credential-printing CLI commands

`describeSubprocessFailure`, the malformed-body message, and the demo guide's
troubleshooting all ended with some form of "re-run the underlying command
yourself". That is the tooling routing around its own rule: a failure is exactly
when someone pastes a terminal into a chat or a screenshot, and the suppressed
output at that moment is the most credential-bearing thing on their screen.

Every such invitation is gone. Failures now say what was suppressed and why, and
point at `docs/app/LOCAL-DEMO.md`, whose troubleshooting gives an ordered recovery
route made only of demo commands and Docker state queries — and says plainly that
going looking for the suppressed output is the one thing the design exists to
prevent. `db:start` and `db:status` no longer appear in any demo-facing section;
they survive in the platform README's general database section, labelled with what
they print and pointed away from demo work. A scan asserts no module names either
script or invites a re-run.

## Round 2: the findings and what was done

## Checkpoint, re-verified each round

Permission settings are read at launch, and a previous session cannot vouch for a
later one, so the safety checks were re-run rather than carried forward — at the
start of round 2, and again at the start of round 3. The canary read was refused
both times with no file content, and the main checkout's changed files were listed
by name only and are unchanged.

| Check | Result |
| --- | --- |
| Approved base SHA | **pass** — branch still cut from `ccd7d4440b69be390fd6ed35a417006bd66c70ff` |
| Worktree canary denied **before any content** | **pass** — re-run in both rounds; `Read` of `docs/app/permission-canary/WORKTREE-CANARY.md` by exact path returned "File is in a directory that is denied by your permission settings" with no file content |
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

Confirmed present and **untouched** throughout both rounds:

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

> **Superseded by round 3, findings 1 and 2.** The 30-minute age bound and the
> read-then-delete recovery described here were themselves wrong: the first broke
> live locks, the second could delete one. The reentrancy, the fail-fast choice,
> the host rule, and the set of commands that take the lock are unchanged. See
> round 3 above for what the mechanism is now.

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

> **Partly superseded by round 3, finding 3.** "A leftover temporary file is
> cleared" was true only of *this process's* leftover. Another run's survived
> forever, carrying the password that run had generated. Cleanup is now
> pid-independent. The discard-before-wipe rule and the atomic rename are
> unchanged.

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
| 8 | `ef4a9c5` | `docs(task-017): record the round 2 review response` |
| 9 | `ed199e3` | `fix(demo): make the lock race-safe and stop echoing untrusted input` |
| 10 | `772353e` | `docs(task-017): route every recovery path through the demo commands` |
| 11 | *this commit* | `docs(task-017): record the round 3 review response` |

All on `feat/TASK-017-safe-local-app-demo`, cut from `ccd7d44`. **No existing
commit was amended, rebased, or rewritten in any round** — each round is additive
on top of the last, so the review history stays legible. Commit 11 touches only
`docs/`; its SHA cannot be printed inside itself, and is resolvable with
`git log --oneline ccd7d44..HEAD`.

## Changed files

Round 3 alone:

> **10 files changed, 917 insertions(+), 218 deletions(-)**
> (`git diff --shortstat ef4a9c5..HEAD`, before this handoff commit)

Round 3 touched: `lock.mjs` and `lock.test.mjs` (rewritten),
`credentials-file.mjs`, `credentials.test.mjs`, `source-safety.test.mjs`,
`paths.mjs`, `subprocess.mjs`, `api.mjs` (one message each),
`docs/app/LOCAL-DEMO.md`, and `platform/README.md`. **No new file was added and
no command was added or removed** — the five-command surface approved above is
unchanged.

Whole branch against the approved base:

> **41 files changed, 6454 insertions(+), 25 deletions(-)**
> (`git diff --shortstat ccd7d44..HEAD`)

New in round 2: `tooling/local-demo/lock.mjs`, `lock.test.mjs`, `api.test.mjs`,
`demo-start.mjs`. Changed: `api.mjs`, `subprocess.mjs`, `subprocess.test.mjs`,
`credential-filter.mjs`, `credentials-file.mjs`, `credentials.test.mjs`,
`launch.mjs`, `paths.mjs`, `reset.mjs`, `demo-stop.mjs`,
`demo-verify-consent.mjs`, `supabase-cli.mjs`, `source-safety.test.mjs`,
`package.json` (one script line), `docs/app/LOCAL-DEMO.md`, `platform/README.md`.

**Nothing else changed, in any round.** No migration, policy, grant, function,
view, or pgTAP file; no `config.toml`; no `database.types.ts`; no
`pnpm-lock.yaml`, `pnpm-workspace.yaml`, dependency, or Expo version; no existing
auth, athlete check-in, sharing, profile, coach, component, theme, or navigation
file; no protected legacy path; **no `.env.local`**. Rounds 2 and 3 are confined
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
| 8 | No raw credential, password, token, user id, health value, Auth response, database error, or credential-bearing CLI output in logs, tests, terminal, or artifacts | **met, and materially stronger each round** — round 2 findings 1, 5, 6, 8 and round 3 findings 2, 3, 4 were all violations of this criterion and are all closed. See the privacy section |
| 9 | Existing cross-team and other-athlete authorization tests remain authoritative | **met** — unchanged; pgTAP re-run at the exact 5 files / 583 assertions baseline |
| 10 | No automatic consent, no seeded health data | **met** — the fixture inserts neither and deletes from both tables; asserted by a scan of the SQL. The lock protects the zero-consent baseline against a concurrent reset landing mid-verification, and round 3 makes that protection actually hold under a stale lock |
| 11 | No new dependency, migration, RLS policy, or client provisioning capability | **met** — frozen lockfile unchanged; the lock and the atomic file replacement use Node built-ins only. `demo:start` is a new *command*, approved above, not a new capability: it starts a stack and writes nothing |
| 12 | Launching never resets or reseeds implicitly | **met** — `demo:web`/`demo:android` still refuse to start a stopped stack rather than bringing it up, and run no reset, fixture, or user creation. `demo:start` starts the stack and nothing else: no reset, no fixture, no user, no write |

## Verification results

Run from `platform/` unless noted. **All green.**

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 — "Already up to date"; lockfile unchanged |
| `corepack pnpm format:check` | exit 0 — all files match |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test:tooling` | exit 0 — **40 suites, 312 tests, 0 failures** (round 1: 210, round 2: 293) |
| `corepack pnpm test` | exit 0 — **40 test files, 790 tests, 0 failures**, unchanged |
| `corepack pnpm demo:reset` | exit 0 — identical baseline every time |
| `corepack pnpm demo:verify` | exit 0 — baseline verified |
| `corepack pnpm demo:verify:consent` | exit 0 — **9/9 checks passed** |
| Two concurrent `demo:reset` processes | **second refused, exit 1**, first completed correctly |
| Lock naming a **dead** pid, then `demo:reset` | recovered automatically, exit 0; `.local-demo/` left holding only `credentials.txt` |
| Lock naming a **live** pid with a credential-shaped label, then `demo:reset` | refused, exit 1, message read `(a demo command, pid 19128)` — **0** occurrences of the sentinel |
| Orphan `credentials.txt.999999.tmp`, then `demo:reset` | removed; only `credentials.txt` remained |
| `corepack pnpm demo:start` (warm and cold) | exit 0 — **0** credential-shaped fragments in the output; demo data intact afterwards |
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

The tooling suite grew from 210 to 293 to **312** tests. Round 3 rewrote
`lock.test.mjs` around the new mechanism — the concurrency tests it replaces
described a design that no longer exists — and added the untrusted-label sentinel
tests, the cross-pid temporary-file tests, and three new source scans. **No test
was deleted to make a failure go away**; every rewrite is described under the
finding that caused it, and the two commands' behavioural tests are unchanged.

pgTAP counts match the TASK-014/016 baseline exactly — 5 files, 583 assertions, 0
lint findings — which is the expected outcome, because no round changed a
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
including on failure, via a best-effort restore. Since round 2 the whole workflow,
including that restore, holds the destructive-workflow lock — and since round 3
that lock cannot be taken from it by another process, however long the run takes.

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
by running the underlying CLI command by hand. At the time that was what the error
message and `LOCAL-DEMO.md` prescribed; **round 3 removed that advice**, because
telling the person at the keyboard to go and fetch the suppressed output is the
tooling routing around its own rule. The ergonomic cost is real and now falls
where it belongs: on whoever maintains the tooling, working from an exit code and
a command name, rather than on the Product Owner being sent to a credential-
printing command.

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

**Round 2 introduced two defects of its own, both found in round 3 and both in the
lock I had just written.** They are the honest headline of this round, so they are
stated plainly rather than folded into the findings above:

- the lock broke any holder older than thirty minutes, so the fix for concurrency
  could itself steal a lock from a healthy, slow run;
- its stale-lock recovery read the file and then unlinked it, which can delete a
  lock another process legitimately acquired in between — the one failure mode
  that is *worse* than having no lock, because the victim never finds out.

Round 2's unit tests passed against both, because they tested the behaviour I had
designed rather than the property I needed: exclusion under concurrency. Round 3's
tests assert the property, and two of them use a real second process.

Round 2 also echoed an untrusted label from that file into an error message, which
is the same class of mistake as round 1's `response.json()` leak — a value from
outside reaching a message — committed while fixing round 1's version of it.

**Round 3 introduced no defect that needed a second fix.** Every change landed
against a test written for it, and the full suite was re-run after each.

Taken together across three rounds: eight of the seventeen findings were
violations of acceptance criterion 8 that my own reports had claimed as met. The
scans I wrote did not catch them because they scan for *forbidden identifiers in
source*, and every one of these leaks was a value arriving at run time — through a
standard-library error message, or out of a file on disk. That is the gap a
reviewer found and a scan could not.

## Privacy and security impact

**Net exposure change: small, and smaller after each round.** This task adds no
new data path, no new query, and no new capability to the product. It adds a way
to run the existing product locally, plus one new secret-adjacent artifact.

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
- **No temporary credential file outlives the run that wrote it** (round 3).
  Cleanup is pid-independent and confined to the ignored directory by an exact
  name pattern, so a killed run cannot leave its generated password sitting in a
  file nothing would ever replace.
- **The credential file holds no key, token, or session** — asserted by test
  against `sb_publishable_`, `sb_secret_`, `eyJ`, `postgres://`, `access_token`,
  and `service_role`.
- **The lock file holds no secret either** — pid, hostname, command label,
  timestamp, and a random nonce, asserted by test, in the same git-ignored
  directory.
- **Nothing read back out of the lock file is echoed** (round 3). The label must
  match one of four allowlisted values or it becomes a fixed fallback; the
  hostname is never printed and the pid only as a validated integer. Proven with a
  credential-shaped sentinel, in the tests and against the real command.
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
- **No message sends anyone to a credential-printing command** (round 3). Every
  recovery route in the tooling and in `LOCAL-DEMO.md` is a demo command or a
  Docker state query; a scan asserts no module invites a raw CLI re-run or names
  `db:start` or `db:status`.
- **`.env.local` is never touched.** No dotenv path appears anywhere in the
  tooling (asserted), and `EXPO_NO_DOTENV=1` means Expo reads none during a demo.
- **No real data.** No `athletes/`, `team_data/`, `garmin/`, environment file,
  dump, or credential was read at any point, in any round.

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
4. **Output suppression costs diagnosis, and round 3 made that cost sharper on
   purpose.** A failing command reports a label, an exit code, and possibly a
   signal — and no longer tells anyone to go and re-run the raw CLI, because that
   advice is a credential-exposure route dressed as helpfulness. The documented
   recovery is `demo:reset`, then Docker state, then handing the exit code and
   command name to whoever maintains the tooling. If a failure ever needs the raw
   output, that is a deliberate, informed act by a maintainer, not a step in a
   troubleshooting list. You should confirm you accept that trade.
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
   limitation 11). A cooperative lock cannot bind a command that never asks for it.
9. **A hard kill during lock recovery needs one manual step.** The recovery claim
   file is deliberately never broken automatically, because automatic recovery of
   the recovery lock would reintroduce the race it exists to remove. The window is
   milliseconds and the claim is removed in a `finally`, so this should never be
   seen; if it is, every command refuses and names
   `platform/.local-demo/demo.lock.break` to delete. That is a considered trade —
   fail closed, recover in one step — and not an oversight.
10. **Pid liveness can be fooled by pid reuse.** If the operating system has reused
    a dead holder's pid, the lock is judged live and the command refuses. That is
    the safe direction — a spurious refusal, never a spurious break — but it means
    a lock can occasionally need waiting out. The opposite error, judging a live
    process dead, is not reachable through `kill(pid, 0)` except on a permission
    error, which is mapped to alive.
11. **Known pre-existing Expo patch drift persists** and is out of scope: `expo`
    `56.0.17` vs expected `~56.0.18`, `expo-router` `56.2.16` vs `~56.2.17`. No
    dependency was changed. 20/21 checks pass.
12. **Supabase CLI `v2.111.0` is available; `v2.109.1` is pinned.** Not upgraded.
13. **`demo:stop` preserves the local volume**, so a later `demo:start` restores
    whatever state the last reset left. If the pgTAP suite was the last thing to
    touch the database, the demo accounts will be gone and the credential file
    will be stale in a way the tooling cannot detect, because the wipe did not go
    through it. I ran a final `demo:reset` before stopping, so the environment you
    inherit is a valid baseline — but the commands can desynchronize, and the fix
    is always `demo:reset`.
14. **Docker Desktop was already running at the start of this round** (I started
    it in round 2 and left it running, as reported then). It is **still running**;
    quitting it is a machine-wide action I left to you. No Supabase container is
    running.

## Rollback

Fully additive on a dedicated branch:

```text
git switch feat/mobile-foundation
git branch -D feat/TASK-017-safe-local-app-demo
```

`feat/mobile-foundation` is untouched at `ccd7d44`. No migration was added, no
remote state changed, no dependency moved, and no Supabase container remains.

Local artifacts outside Git, if you want them gone: `platform/.local-demo/` (the
credential file, and the lock and recovery-claim files when a command is running)
and the local Docker volume, removable with
`corepack pnpm exec supabase stop --no-backup` — **note that this discards the
local database**, which is exactly why `demo:stop` never passes that flag.

Partial reverts, newest first:

| To undo | Command |
| --- | --- |
| Round 3 only, keeping rounds 1–2 | `git revert 772353e ed199e3` |
| Rounds 2 and 3, keeping round 1 | `git revert 772353e ed199e3 b2547ec 2a7b2d5` |
| The implementation, keeping the documentation | `git revert 60d0118 6df9417` |

**Reverting round 3 alone is not recommended.** It would restore a lock that
breaks live holders on a timer and can delete another process's lock, which is
worse than the round 1 state of having no lock at all: with no lock, nothing
pretends to be protected. If round 3 has to go, take round 2 with it.

## For the reviewer (GPT/Codex, read-only)

The earlier focus lists still stand. What is new in round 3, highest value first:

1. **The claim-file argument in `lock.mjs`.** The correctness claim is a chain,
   and it is only as strong as its weakest link: the lock's owner is proven dead;
   a dead process cannot release its own lock; only the single claim holder may
   unlink; therefore nothing can change the lock file between the nonce check and
   the unlink. Attack that chain. The place I would look first is whether "proven
   dead" can go stale — the pid check happens before the claim is taken, and the
   nonce re-check after, which is why both exist.
2. **The claim file is never broken automatically.** That is deliberate, and it
   trades a vanishingly rare manual step for the removal of a whole class of race.
   Judge whether that is the right call, or whether a bounded automatic recovery
   would be acceptable given the window is milliseconds.
3. **Whether refusing is right when recovery is contended.** A second process
   arriving during a recovery refuses rather than waiting for the claim to clear.
   Retrying would be friendlier; refusing is one fewer state to reason about.
4. **The temporary-file pattern in `credentials-file.mjs`.** It deletes files
   another process wrote, which is only safe because writing one happens under the
   lock. Check that the name pattern cannot match anything but this tooling's own
   temporary files, and that the scan cannot reach outside `.local-demo/`.
5. **Whether removing the raw-CLI advice went too far.** A maintainer debugging a
   fixture failure now has an exit code and a command name, and has to decide for
   themselves to run the CLI. I think the exposure trade is right; you may think
   the tooling should offer a maintainer-only escape hatch instead.
6. **The `isAlive` and `onBreakWindow` seams.** They exist for the tests. Confirm
   they cannot be reached from a command, and that no production path passes
   anything but the defaults.
7. **`source-safety.test.mjs`.** Still only as good as its comment- and
   string-stripping, and each round adds scans that depend on it. Look for a way
   to write a forbidden call, or a raw-CLI invitation, that the stripper hides.
8. **Still open from round 2:** whether `demo:web`/`demo:android` should start a
   stopped stack themselves rather than refusing; and whether generating health
   values at run time is the right reading of AC8 or an over-correction.

**Not done, deliberately:** no merge, push, deploy, publish, hosted-Supabase link,
remote migration, `db push`, branch deletion, worktree removal, or `.env.local`
access. No acceptance criterion was reworded, and AC3 is left open rather than
argued into met.
