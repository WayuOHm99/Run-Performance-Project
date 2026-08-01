# TASK-017 handoff — Safe Local App Demo Environment and Synthetic Fixtures

Status: **Round 8 complete.** Round 8 fixes a real failure the Product Owner
reproduced on their own machine — one that **round 6 had concluded was
impossible**. Both structural baseline conditions are retryable again, on a wider
bound, with distinct messages preserved. Round 6's measurements are kept as
historical evidence with its conclusion explicitly marked superseded. Full
verification re-run, including the database authorization suite, an end-to-end
consent verification, and a stop → cold `demo:reset` → `demo:verify` cycle.
**The intermittent condition did not recur during my verification**, so nothing
here claims to have watched the retry fire. Stopped for GPT/Codex read-only
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

**The Product Owner has approved this deviation**, in round 2 and again in round
4. `demo:start` stays, on the stated grounds that it safely replaces
credential-printing `db:start`. It is the only addition to the command surface, it
is non-destructive — no reset, no fixture, no user, no write — and AC12 is
unaffected: starting a stopped stack is not reseeding it. The packet's in-scope
list is left as approved rather than edited to match; this section is the record.

## Round 6: the findings and what was done

Three findings — one Medium, two Low. The Medium one asked for evidence rather
than a code change, and the evidence changed what the other fix should be.

### The measurement, first

Round 5 defended a retry budget with an argument. Round 6 measured it. A
throwaway probe — written **outside the repository**, in the session scratchpad,
and not committed — polled the baseline query continuously across two full
`stop → cold start → db reset` cycles.

**What the probe was allowed to record:** an enumerated structural
classification, an attempt number, and an elapsed millisecond count. Nothing
else. The classifier looks only at whether a key exists and what *type* it is;
it never reads a value, and it never prints stdout, a row, a credential, a URL,
or a health value. The classifications are a closed set: `one-row`,
`rows-array-length-N`, `rows-missing`, `rows-not-array(type)`,
`document-not-object`, `malformed-json`, `non-integer-count`,
`subprocess-failure`.

**Measurement A — is the database ready when `readBaseline` actually runs?**
Poll starts after the command returns.

| Cycle | After cold `supabase start` | After `db reset --local --no-seed` |
| --- | --- | --- |
| 1 | `one-row` on attempt 1 | `one-row` on attempt 1 |
| 2 | `one-row` on attempt 1 | `one-row` on attempt 1 |

**4 of 4, first attempt, no gap at all.** The only classification observed in the
entire measurement was `one-row`.

**Measurement B — the readiness ramp, polled from t=0 *while* the command runs.**
This is the window the incident would have to fall in.

| Cycle | Phase | Unreachable from | First `one-row` | Command returned |
| --- | --- | --- | --- | --- |
| 1 | cold start | 1545ms | 5026ms | 26998ms |
| 1 | `db reset` | 1563ms | 23348ms | 35117ms |
| 2 | cold start | 1693ms | 5709ms | 27452ms |
| 2 | `db reset` | 1702ms | 24603ms | 37293ms |

Two facts come out of this, and both matter more than the timings:

1. **An unready local database produces a non-zero exit — never a well-formed
   document with the wrong number of rows.** Across roughly a hundred probe
   attempts spanning every unready moment of four container transitions, the
   only two classifications ever observed were `subprocess-failure` and
   `one-row`. `rows-missing`, `rows-not-array`, `rows-array-length-N`,
   `malformed-json`, and `non-integer-count` **never occurred once**.
2. **The database is ready long before the command that resets it returns** —
   by 11.8s in cycle 1 and 12.7s in cycle 2. And `readBaseline` does not even
   run there: `db reset`, two real Auth signups, and the fixture application all
   have to succeed against that same database first.

> **Superseded by round 8, in part.** The measurements above are kept because
> they are real and still useful — the timings and the "unready means non-zero
> exit" observation both stand as *observations*. What does **not** stand is the
> conclusion drawn from fact 1: that a missing or non-array row set is therefore
> a permanent CLI-contract failure. The Product Owner hit exactly that shape
> three times in a row and it cleared on its own. This probe simply never
> provoked it, and I mistook that for proof it could not happen. See round 8.

### 1. Medium — the retry budget is not proven sufficient

**Kept at four attempts and 500ms, and the reason is now measured rather than
argued.**

For the phenomenon that is real and reproducible — local readiness — the budget
is not marginal, it is enormous: the required allowance measured **0ms in 4 of 4
cycles**, against a 1.5s budget, with three successful database round-trips
already standing between the reset and the baseline read. A budget in the tens of
seconds would be sizing for a window this code structurally cannot be in.

**What I could not do is reproduce the incident.** The retried condition — a row
array of the wrong length — did not occur once in any measurement. So I cannot
give you a duration for it, and I will not invent one: increasing the budget
against an unmeasured window is exactly the arbitrary increase this finding asked
me to avoid. The retry stays as bounded, cheap insurance, and it is now honest
about what it is.

The budget is pinned by a test rather than left as whatever the constants happen
to say, so changing it requires re-reading this evidence.

**A more useful outcome than a bigger number:** because finding 2 splits the
classification, a recurrence will now say *which* shape it was. "…returned no
row set" and "…did not return exactly one row" are different messages, and
whichever appears next tells us which branch fired — something round 5's single
message could not.

### 2. Low — retry classification was broader than its explanation

Codex is right, and the measurement decides it. Round 5 retried

```text
!Array.isArray(rows) || rows.length !== 1
```

so `{}`, `{ rows: null }`, and `{ rows: {} }` each cost four attempts and 1.5
seconds, while every comment and paragraph described only a wrong row *count*.

**Resolved by narrowing, which is option one of the two offered.** I took it
because the second option requires proving those shapes are a transient
readiness condition, and measurement B proves the opposite: readiness failures
are non-zero exits. There was no evidence behind retrying a missing row set, and
round 5 should not have claimed one.

- `Array.isArray(rows) && rows.length !== 1` → **retryable**, message unchanged.
- Missing or non-array `rows`, and a document that is not an object → **fails
  immediately**, with a new fixed sanitized message, *"The baseline query
  returned no row set."*
- Malformed JSON, non-integer counts, subprocess failures, and real count
  mismatches are unchanged and still never retried or hidden.

Fourteen new tests cover the classification directly: two retryable shapes
(empty array, two rows) asserting `retryable === true` and the unchanged
message; eight fail-fast shapes (`{}`, `{ rows: null }`, `{ rows: {} }`,
`{ rows: "1" }`, `{ rows: 1 }`, an envelope with `boundary`/`warning` and no
`rows`, a non-object document, and `null`) asserting the new message and
`retryable === false`; and a `readBaseline`-level test asserting each of those
costs **exactly one attempt and zero waits**. The sentinel-leak scan gained three
cases aimed at the new branch, including one where the offending `rows` value
*is* the sentinel.

> **Superseded by round 8.** Narrowing was the wrong call, and the reason is
> instructive: I said option two "requires proving those shapes are a transient
> readiness condition" and treated my failure to provoke them as proof of the
> negative. The Product Owner then reproduced exactly that shape. Both shapes are
> retryable again as of round 8. The one part of this finding that survives is
> the **separate message**, which is what later identified which branch fired —
> that distinction was worth making and is kept.
>
> Codex's underlying complaint was still correct: the classification and its
> explanation disagreed. Round 8 resolves it the other way, by widening the
> explanation to match a retryable classification instead of narrowing the
> classification to match a too-confident explanation.

### 3. Low — rollback documentation was inconsistent

Also correct. The table called `git revert 6fef4cb 26d78dd` "Round 5 only" while
round 5 was three commits including the handoff, so running it would have left
this document describing code that was no longer on the branch.

The round 6 rewrite added a column naming the documentation left in place, and
explained why no documentation commit appears in a rollback command.

> **Superseded by round 7.** The round 6 rewrite fixed the label and then made a
> worse error underneath it: it declared every command "implementation-only"
> while three of them contained `89fb9c6` (a mixed code-and-documentation
> commit), `772353e`, and `b2547ec` (both documentation-only), and it kept an
> "all implementation" command that reverts only round 1's implementation while
> six later code commits stay on the branch. I corrected the wording Codex
> pointed at without checking the commits the wording described. See the Rollback
> section for what the table says now — two verified commands, and an explicit
> statement that anything older is a manual rollback.

## Round 8: the finding and what was done

**The Product Owner reproduced the failure round 6 declared impossible.** That is
the whole round, and the correction matters more than the code.

### What happened

1. `demo:reset` failed with **"The baseline query returned no row set."**
2. An immediate `demo:verify` failed with the same message.
3. A second `demo:reset` failed with the same message again.
4. A later safe structural probe returned the normal envelope, with `rows` an
   array of length 1.
5. `demo:verify` then passed.
6. A subsequent controlled `demo:reset` passed and wrote the credentials file.

A condition that fails three times and then clears on its own, with no
intervening fix, is transient. **Round 6's conclusion is disproven.**

### Why round 6 got it wrong

Round 6 measured a local stack across two `stop → cold start → db reset` cycles,
found that an unready database fails with a **non-zero exit** rather than a
malformed envelope, and concluded that a missing row set had to be a permanent
CLI-contract violation. It made that shape fail immediately, and I wrote that up
as the disciplined, evidence-led choice.

The measurement was not wrong about what it saw. The **inference** was wrong: I
treated "I could not provoke this in four container transitions on one machine"
as "this cannot happen". Those are not the same claim, and only the first one was
supported. The round 6 write-up even said the incident was never reproduced and
listed that as a limitation — and then reasoned as though it had been ruled out.

The general lesson, recorded because this is the second round in a row where my
reasoning outran my evidence: **an absence of reproduction is not evidence of
impossibility**, and a real failure on the Product Owner's machine outranks my
inability to reproduce it.

### The change

Both structural shapes are retryable again, on one shared budget:

| Parsed result | Round 6 | Round 8 |
| --- | --- | --- |
| `rows` missing or not an array | fail immediately | **retryable** |
| `rows` an array, length ≠ 1 | retryable | **retryable** |
| Malformed JSON | fail immediately | fail immediately |
| Non-integer count | fail immediately | fail immediately |
| Subprocess failure | fail immediately | fail immediately |
| Real count mismatch | returned, never retried | returned, never retried |

**The two messages stay distinct.** *"The baseline query returned no row set."*
and *"The baseline query did not return exactly one row."* Round 6's one durable
contribution was creating that distinction, and it is what told us which branch
the Product Owner actually hit. Collapsing them now would throw away the only
diagnostic this whole sequence produced; a test asserts they stay different.

**The bound moves from 4 attempts / 500ms to 10 attempts / 1000ms.**

**9000ms is the maximum *wait* budget, not the maximum duration.** The nine waits
are the only part of the elapsed time this module controls. Each of the ten
attempts also spawns a Supabase CLI process and waits for it to answer, and round
6 measured a single baseline query at roughly 1.5s against a healthy stack. A
full exhaustion is therefore ~9s of waiting **plus** ten query round-trips, and
the wall-clock total can exceed twenty seconds. Nothing promises otherwise and no
caller sets a deadline against it.

**Ten attempts do not promise to outlast the Product Owner's incident.** That one
survived a whole `demo:reset` and an immediate `demo:verify` — a far longer
window than any budget here would cover. The wider bound makes a short blip
recoverable and leaves a long one failing closed, which is the honest shape for a
condition whose duration is still unknown. The recovery when it is not enough is
unchanged: run `demo:reset` again.

Unchanged and re-asserted: credentials stay unwritten until the baseline passes
comparison (the throw propagates out of `resetUnderLock` before
`writeCredentialsFile`); exhaustion rethrows the last error unchanged so it fails
closed; and nothing derived from the response reaches any error surface.

### Honest limits of this round's verification

**I did not reproduce the intermittent condition either.** Every live command I
ran this round succeeded on its first read. The verification below shows the
pipeline still works end to end with the wider bound; it does **not** show the
retry firing, because nothing transient occurred while I was watching. The retry
path's behaviour rests entirely on the deterministic unit tests, where both the
query and the wait are injected.

So: the *fix* is driven by the Product Owner's evidence, and the *tests* prove
the fix behaves as specified. Neither is a claim that I saw it recover live.

## Round 7: the finding and what was done

One Low finding, documentation-only. No code, test, migration, config, package
file, or README changed; `git diff --name-only 59437f0..HEAD` lists this file
alone.

Codex found that round 6's rollback table was still wrong, in a way round 6
introduced. The details and the correction are in the Rollback section rather
than duplicated here, because that is where someone rolling back will look.

What I take from it, since this is three rounds in a row where the rollback
guidance was wrong: **I had never verified the composition of the commits I was
writing commands out of.** Round 7 started by running `git show --name-only` on
all seventeen commits on the branch and building the round-composition table from
the output. Every claim in the Rollback section now traces to that, and the one
"these revert cleanly" claim is backed by a `git log` invocation the reviewer can
run. Prose about history should be derived from the history, not from memory of
what I intended each commit to be.

## Round 5: the finding and what was done

One Medium reliability finding, reproduced and diagnosed by Codex from the
Product Owner's own run. Nothing else was touched.

### 1. Medium — a cold `demo:reset` intermittently failed a correct baseline

**What happened.** The Product Owner's first cold `demo:reset` started the stack,
reset the database, created both accounts through real Auth, and applied the
fixture — and then failed with *"The baseline query did not return exactly one
row."* An immediate `demo:verify` failed the same way. Later structural
inspection of the same query returned the expected envelope — top-level
`boundary`, `rows`, `warning`, with `rows.length` of 1 — and a warm reset, then a
later stop → cold reset → `demo:verify`, all passed. It is intermittent, not a
schema or fixture defect.

**Why that condition is transient and not a state report.** `BASELINE_SQL` is a
single outer `select` of ten scalar subqueries. It has no `from` clause and no
predicate on the outer select, so the database has no way to answer it with
anything but exactly one row — not zero, not two, whatever the demo's actual
state is. A result that is not one row therefore says the read did not reach a
ready database; it says nothing about how many profiles or grants exist.

**The fix.** `readBaseline` now retries **that one condition** and nothing else:
four attempts, a bounded 500ms wait between them, so the worst case adds 1.5
seconds and then fails. The retryable/non-retryable decision is a fixed boolean
set at the throw site in `parseBaselineRow`, never derived from the response.

**What is deliberately not retried**, because the requirement was to retry only
what can be shown safe:

- **A count mismatch is not retried and not hidden.** It is not a failure of the
  read at all — it is a correct read of a database in the wrong state, and it
  must surface on the first attempt. Structurally it cannot be swallowed either:
  a mismatching baseline parses successfully, so `readBaseline` returns it and
  the caller's separate `compareBaseline` step sees the real numbers. The retry
  loop never reaches into that comparison and never re-runs it. There is a test
  asserting the query is issued exactly once for a baseline carrying a seeded
  grant and four seeded check-ins, and that both counts come back unaltered.
- **Malformed JSON and a non-integer count are not retried.** I cannot prove
  these are transient. Malformed output means the CLI wrote something that is not
  a result document; a non-integer count means a `count(*)::int` came back as
  something that is not an integer. Both are equally consistent with a broken
  invocation or a changed CLI contract, and retrying a broken contract only
  reports a permanent fault as a slow one. Requiring proof rather than
  plausibility is the point: an unprovable retry is exactly how a hard failure
  becomes a hidden one.
- **A subprocess failure is not retried.** A non-zero exit or a signal from the
  CLI is a different condition with its own sanitized error, and it leaves the
  loop immediately.

**Failing closed is unchanged.** When the budget is exhausted the last error is
rethrown **unchanged** — same fixed sanitized message, same type — so a
persistent structural failure looks exactly like a single-attempt failure and
still stops the run. Because the throw propagates out of `resetUnderLock` before
`writeCredentialsFile`, **credentials still stay unwritten until the baseline
verifies**, and the discard that precedes the database reset means a failed run
leaves no credential file at all.

**Nothing from the response reaches the error.** No stdout, no row, no envelope
field, no attempt-specific detail. The only property added is `retryable`, a
boolean decided from the failure's shape. A test drives four different responses
carrying a sentinel string through the loop and asserts the sentinel appears in
none of `error.message`, `String(error)`, `error.stack`, or any own property
name/value — including properties a future edit might attach — and that the
message is one of the three fixed sanitized strings.

**Honest limit on the fix.** In the Product Owner's report the condition
outlived an immediate `demo:verify`, which a 1.5-second budget would not have
absorbed. This makes a short readiness window recoverable; it does not claim to
cover every window, and it deliberately does not grow the budget until evidence
says a longer one is both necessary and safe. A longer wait would trade a
still-failing run for a slower still-failing run. The recovery when the retry is
not enough is unchanged and unchanged in cost: run `demo:reset` again.

### Round 5 verification of the fix itself

The retry path is covered by deterministic unit tests only — both the query and
the wait are injected, so nothing sleeps and nothing depends on a real clock,
CLI, or database. That is intentional: the live failure is intermittent, so a
live run can confirm the pipeline still works but can never confirm the retry
fired. **All three live cold cycles this round passed on their first read**, so
the retry was not exercised in production; the evidence that it behaves correctly
is the unit suite.

## Round 4: the findings and what was done

Two Medium findings and one Low. The first is another defect in the lock, in the
one place I had not looked: the moment it is created.

### 1. Medium — the lock's own initialization was a race (fail-closed now)

A lock is created with `open(lockFile, "wx")` and its record is written a moment
later. **Every successful acquisition therefore passes through a state where the
file exists and is empty.** Round 3 treated a file with no usable record as proof
that no orderly holder existed and deleted it under the claim protocol — so a
process arriving inside that window would delete a lock that had just been
legitimately taken, and both would run.

This is the same failure round 3 set out to eliminate, surviving in the one case
round 3's reasoning did not cover. The reasoning was "it names no owner, so nobody
holds it", and the flaw is that an empty lock file is not the appearance of an
abandoned lock — it is the ordinary appearance of a lock **being taken right
now**.

The rule is now: **an unreadable, empty, or partially written lock record is never
deleted automatically.** Automatic recovery is preserved for exactly one case, a
**well-formed** record naming an owner **proven gone on this host**. Everything
else refuses and names the file, which costs a manual delete in a case that should
never occur and keeps the guarantee in the case that does.

`isLockBreakable` now returns false for a null or non-object record rather than
true, so the fail-closed property belongs to the function itself and not to its
call sites. The nonce and claim protocol is unchanged and still race-safe; the
re-read inside the claim now also refuses if the record has become unreadable.

Four tests added, and the existing ones kept:

- **the initialization window itself** — a lock is created with `open(…, "wx")`
  and held open with nothing written, exactly as a mid-acquisition lock looks;
  the workflow never runs, the lock survives, and no recovery claim is created;
- **the same, from a genuinely separate process**, which refuses and leaves the
  file present and still zero bytes;
- an unreadable record is refused rather than deleted, even when the pid check
  says its owner is dead;
- the contents of an unreadable lock file are never echoed, proven with a
  credential-shaped sentinel.

Dead-owner recovery, live-old-lock preservation, the claim races, and the
separate-process tests are all unchanged and still pass.

**Verified live against the real command.** An empty `demo.lock` was placed in
`platform/.local-demo/` and `demo:reset` was run:

```text
demo:reset failed — The local demo lock exists but does not yet hold a readable
record. That is what a lock being taken right now looks like, so this command
stopped rather than assume it was abandoned.
```

The lock file was still present afterwards, still **0 bytes**, with no recovery
claim beside it. Before this round the same input deleted it and ran.

### 2. Medium — raw CLI examples in the platform README

`platform/README.md`'s "Safe local commands" section still opened with
`db:start` and `db:status`, which pass the Supabase CLI's output straight through
— the local database URL, the JWT secret, and the service-role key. Round 3
labelled them instead of replacing them, which left the first commands a reader
meets being the two that print credentials.

The block is now `demo:start`, `demo:verify`, and `demo:stop`, with a sentence
saying these are the supported way to run the local stack and that each suppresses
the CLI's output at the OS level. The `db:*` scripts still exist in
`package.json`; nothing in any document now points a reader at them.

### 3. Low — "the only destructive command" was wrong

`platform/README.md` said `demo:reset` is the only destructive command.
`demo:verify:consent` is destructive too: it creates a synthetic check-in and a
sharing grant, which is why it brackets itself with a full reset at both ends.

The README now names both, explains that the consent verification restores the
zero-consent baseline afterwards — including on failure, via a best-effort
restore — and points out that `demo:verify` is the read-only one.
`docs/app/LOCAL-DEMO.md` already marked it destructive and self-restoring in its
command table and needed no change.

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
  is never assumed dead. ~~An unusable record is breakable because it names no
  owner at all.~~ **Superseded by round 4, finding 1: that last clause was itself
  a race, because an empty file is what a lock being taken right now looks like.
  An unusable record is now never broken.**
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
| 11 | `ef2f9ef` | `docs(task-017): record the round 3 review response` |
| 12 | `89fb9c6` | `fix(demo): fail closed on a lock record that is not readable yet` |
| 13 | `26d78dd6d13a7b22a846971e75086fbe558d1992` | `fix(demo): retry only the transient baseline row-count condition` |
| 14 | `6fef4cb4fcdb612e32abb9630c80fecb081f0017` | `fix(demo): clamp the baseline retry's test seams to the bound` |
| 15 | `b4067b06ca937df47e5b4719aa7287417141b14f` | `docs(task-017): record the round 5 review response` |
| 16 | `939435e6deaa6ae06243e0fbaacfdabd7cd88bfb` | `fix(demo): narrow the baseline retry to a measured condition` |
| 17 | `59437f052af8d796618df8b992e919d80245df31` | `docs(task-017): record the round 6 review response` |
| 18 | `dc21f484b865b20acfc4adcca234844233ea415d` | `docs(task-017): correct the rollback table` |
| 19 | `0748048034f3cdcc8a6a8221a8d563274ccc3ee6` | `fix(demo): retry both structural baseline conditions on a wider bound` |
| 20 | *this commit* | `docs(task-017): record the round 8 review response` |

All on `feat/TASK-017-safe-local-app-demo`, cut from `ccd7d44`. **No existing
commit was amended, rebased, or rewritten in any round** — each round is additive
on top of the last, so the review history stays legible.

Composition by round — **code commits plus documentation commits** — is set out
in the round-composition table in the Rollback section, derived from
`git show --name-only` on all seventeen predecessors rather than from memory.
The short version: **round 4 is one mixed commit** carrying code and
documentation together; **round 5 is two code commits plus one documentation
commit**; **round 6 is one of each**; **round 7 is documentation only**.

Round 5's clamp was kept as its own commit rather than amended into `26d78dd`
deliberately: the defect it fixes is disclosed below, and hiding it inside the
first commit would have made the disclosure unverifiable.

Each round's closing documentation commit cannot print its own SHA inside itself;
all of them are resolvable with `git log --oneline ccd7d44..HEAD`.

## Changed files

Round 8 alone — **two files** in one code commit, no new file, no command added
or removed:

> `platform/tooling/local-demo/baseline.mjs`,
> `platform/tooling/local-demo/baseline.test.mjs`, plus this handoff.

`reset.mjs` and `demo-verify.mjs` still call `readBaseline()` with no arguments;
the wider bound lives entirely behind that call.

Round 7 alone — **one file**, this handoff, in one documentation-only commit:

> `docs/app/handoffs/TASK-017.md`

Confirmed with `git diff --name-only 59437f0..HEAD`. No code, test, migration,
config, package file, lockfile, README, or fixture changed.

Round 6 alone — **two files** in one code commit, no new file, no command added
or removed:

> `platform/tooling/local-demo/baseline.mjs`,
> `platform/tooling/local-demo/baseline.test.mjs`, plus this handoff.

The readiness probe that produced the round 6 evidence was written in the session
scratchpad **outside the repository** and is deliberately **not committed**. It is
a diagnostic, not a test: it needs Docker, takes several minutes, and stops and
restarts the local stack. Committing it would put a slow, environment-dependent
script in a suite that is currently fast and hermetic. Its logic is described
above in enough detail to rebuild, and what it proved is now pinned by
deterministic unit tests that need no database.

Round 5 alone — **two files** across its two code commits, no new file, no
command added or removed:

> `platform/tooling/local-demo/baseline.mjs`,
> `platform/tooling/local-demo/baseline.test.mjs`, plus this handoff.

No other module was touched. `reset.mjs` and `demo-verify.mjs` call
`readBaseline()` with no arguments exactly as before; the retry lives entirely
behind that call, and its seams (`query`, `attempts`, `delayMs`, `wait`) are
defaulted parameters that no command passes.

Round 4 alone — four files, no new file, no command added or removed:

> `platform/tooling/local-demo/lock.mjs`, `lock.test.mjs`, `paths.mjs`,
> `platform/README.md`, plus this handoff.

Round 3:

> **10 files changed, 917 insertions(+), 218 deletions(-)**
> (`git diff --shortstat ef4a9c5..ef2f9ef`)

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
| `corepack pnpm test:tooling` | exit 0 — **42 suites, 348 tests, 0 failures** (round 1: 210, round 2: 293, round 3: 312, round 4: 315, round 5: 324, round 6: 336) |
| Readiness probe, measurement A (post-command), 2 cycles × 2 phases | `one-row` on attempt 1, **4 of 4**, no gap |
| Readiness probe, measurement B (during the ramp), ~100 attempts | only `subprocess-failure` and `one-row` ever observed; the retried condition **never occurred** |
| `corepack pnpm test` | exit 0 — **40 test files, 790 tests, 0 failures**, unchanged |
| **stop → cold `demo:reset` → `demo:verify`**, run five times | exit 0 each time — **0** Supabase containers before each cold start; identical baseline every time; the `demo:verify` immediately after each cold reset passed. The fifth cycle ran against the final round 8 code |
| Round 8: did the intermittent condition recur? | **No.** Every live command succeeded on its first read, so the retry was never exercised against a real stack this round |
| `corepack pnpm demo:reset` | exit 0 — identical baseline every time |
| `corepack pnpm demo:verify` | exit 0 — baseline verified |
| `corepack pnpm demo:verify:consent` | exit 0 — **9/9 checks passed** |
| Two concurrent `demo:reset` processes | **second refused, exit 1**, first completed correctly |
| **Empty** lock file (the initialization window), then `demo:reset` | **refused, exit 1**; lock still present and still **0 bytes**, no recovery claim created |
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

The tooling suite grew from 210 to 293 to 312 to 315 to 324 to 336 to **348**
tests. Round 8 reworked the `readBaseline` suite around the wider bound and added
twelve net: recovery for each retryable shape after repeated failure and again on
the **tenth and last** attempt; exhaustion at **exactly ten attempts and nine
waits** for missing rows, non-array rows, and wrong cardinality, each asserting
its own distinct message; the production bound pinned at 10 × 1000ms with the
9000ms wait budget stated; seams rejected when they try to **exceed** the bound
(`attempts: 11`, `delayMs: 1001`) as well as when they try to remove it; a seam
honoured when it asks for less; exactly-one-query assertions for malformed JSON,
non-integer counts, and subprocess failure; a count mismatch queried once and
returned unaltered; and a leak scan extended to `error.cause` and to both
retryable branches driven to exhaustion.
Round 6 added twelve: ten pinning the exact retryable/fail-fast classification
across the shapes in finding 2, one pinning the chosen budget so it cannot drift
away from the evidence, and one asserting the fail-fast shapes cost exactly one
attempt and no wait. The sentinel-leak scan also gained three cases for the new
branch. Round 5
added nine, all in a new `readBaseline` suite: recovery after one structural
failure, the SQL sent unchanged on every attempt, budget exhaustion failing
closed with bounded attempts and bounded waits, an out-of-bounds `attempts` seam
falling back to the default budget, an out-of-bounds `delayMs` seam falling back
to the default wait, a count mismatch neither retried nor altered, malformed JSON
and a non-integer count not retried, a throwing query not retried, and the
sentinel-leak scan across message, `String(error)`, stack, and every own
property. Round 4 added four
lock tests and inverted one — the round 3 test asserting that an unusable lock
record is *recovered* asserted the defect, so it now asserts the refusal. Round 3
rewrote
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

**Round 3 did not introduce a defect, but it did not finish removing round 2's.**
Its rewrite carried one clause forward unexamined — that a lock file with no
usable record names no owner and can be deleted — and that clause was the round 2
race surviving in the one case the new reasoning did not cover. Round 4 closes it.

The pattern is worth naming, because it is now three rounds long: **each time, the
mechanism I wrote was correct for the states I had thought of, and wrong for a
state that only exists for a few milliseconds.** A lock older than thirty minutes.
A lock unlinked between the read and the create. A lock that exists but has not
been written yet. Each was invisible to tests that asserted the design rather than
the property, and each was found by a reviewer reading for what could happen
rather than for what was intended.

**Round 4 introduced no defect that needed a second fix.** Every change landed
against a test written for it, and the full suite was re-run after each.

**Round 5 introduced one, and I caught it while writing the reviewer list rather
than while writing the code.** The retry's test seams were plain defaulted
parameters, so `attempts: 0` — or `NaN`, or a negative number — would have
skipped the loop body entirely, left `lastError` undefined, and thrown
`undefined`: no message, no type, no fail-closed guarantee. No command can reach
it, because no command passes the seam, but a mechanism whose whole purpose is a
bound should not have a way to be handed no bound at all. Both numeric seams are
now clamped to a ceiling and fall back to the default when out of range, with a
test for each. The pattern is the same one round 3 and round 4 found in the lock:
**a test seam is part of the mechanism, not outside it.**

Taken together across four rounds: eight of the twenty findings were violations of
acceptance criterion 8 that my own reports had claimed as met, and three were
concurrency defects in the lock built to fix the first one. The scans I wrote did
not catch the leaks because they scan for *forbidden identifiers in source*, and
every one of those was a value arriving at run time — through a standard-library
error message, or out of a file on disk. The tests I wrote did not catch the races
because they asserted the behaviour I had designed rather than the property I
needed. That is the gap a reviewer found and neither a scan nor my own tests
could.

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
9. **Two rare states need one manual delete each, on purpose.** Neither is an
   oversight; both are the fail-closed side of a trade.
   - A hard kill *during lock recovery* can leave the recovery claim file behind.
     It is deliberately never broken automatically, because automatic recovery of
     the recovery lock would reintroduce the race it exists to remove. Commands
     then refuse and name `platform/.local-demo/demo.lock.break`.
   - A hard kill *during lock creation*, or a corrupted lock file, can leave a
     lock whose record is empty or unreadable. Round 4 made that permanently
     un-deletable by the tooling, because an empty lock file is exactly what a
     lock being taken right now looks like, and guessing costs the whole
     guarantee. Commands refuse and name `platform/.local-demo/demo.lock`.

   Both windows are milliseconds wide and both files are removed in a `finally`,
   so neither should ever be seen. If one is, the fix is deleting the named file —
   and the message says which, without echoing what it contained.
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
14. **The incident that motivated the retry was never reproduced, and its cause
    is still unknown.** This is the honest headline of round 6. Roughly a hundred
    probe attempts across four container transitions produced only
    `subprocess-failure` and `one-row`; the condition the retry covers did not
    occur once. So the retry is insurance against something I have measured the
    *absence* of, not something I have characterised. If it recurs, the two
    distinct messages will at least say which branch fired — that is the
    diagnostic this round bought, and it is worth more than the retry itself.
    ~~Round 5: the bound may be too small for the window the Product Owner hit.~~
    **Superseded by round 6's measurement**, which shows the readiness window at
    that point is 0ms and that readiness failures take a different shape
    entirely. The old claim assumed the incident was a readiness gap; nothing
    supports that.
15. **The retry has still never been observed firing against a real stack**, now
    across four cold cycles rather than three. Its behaviour rests entirely on
    deterministic unit tests with the query and the wait injected.
16. **The measurement is one machine, one Docker backend, two cycles.** Windows
    11 with the WSL 2 backend, Supabase CLI `v2.109.1`. The consistency between
    cycles was high — the four transitions agree to within a few hundred
    milliseconds — but a slower machine, a cold image pull, or a different CLI
    version could move the ramp timings. What I would not expect to move is the
    *shape* finding: an unready database failing with a non-zero exit rather
    than a malformed envelope is CLI behaviour, not a timing artefact.
17. **The readiness probe is not committed**, so this evidence is not
    reproducible by running the test suite. It is reproducible by rebuilding the
    probe from the description above. I judged a slow, Docker-dependent,
    stack-restarting diagnostic to be the wrong thing to add to a fast hermetic
    suite; if you disagree, that is a reasonable place to push back.
18. **The retry's duration is still unknown, and ten attempts may not be
    enough.** The Product Owner's incident survived a full `demo:reset` and an
    immediate `demo:verify` — much longer than 9000ms of waiting plus ten query
    round-trips. This makes a short blip recoverable; it does not promise to
    outlast that incident, and I did not widen it further because there is still
    no measurement of how long the condition actually lasts. The recovery when
    it is not enough is unchanged: run `demo:reset` again.
19. **A wider bound makes a genuinely broken baseline slower to report.** Ten
    attempts against a persistently wrong structural result costs ~9s of waiting
    plus ten CLI round-trips before it fails. That is the price of the retry, it
    is paid only on the failure path, and it is bounded — but it is real, and it
    is longer than the 1.5s round 6 charged.
20. **Round 8 did not reproduce the condition either.** Every live command this
    round succeeded on its first read. The fix follows the Product Owner's
    evidence; the tests prove the fix behaves as specified; neither is a claim
    that I watched it recover.
21. **Docker Desktop was already running at the start of this round** (I started
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

### Partial reverts

**Round 7 rewrote this subsection because the round 6 version was wrong.** It
claimed every command in it was "implementation-only" and built commands out of
commits that are not implementation commits at all. Verified against
`git show --name-only` for all seventeen commits on the branch, the errors were:

- `89fb9c6` (round 4) is a **mixed** commit — `lock.mjs`, `lock.test.mjs`,
  `paths.mjs`, **and** `platform/README.md` **and** this handoff. It was listed
  inside "code only" commands.
- `772353e` and `b2547ec` are **documentation-only** — each touches only
  `docs/app/LOCAL-DEMO.md` and `platform/README.md`. Both were listed inside
  "code only" commands, which is the exact opposite of what they are.
- `git revert 60d0118 6df9417` was labelled "all implementation". It is not: it
  reverts the two round 1 implementation commits while every later fix
  (`2a7b2d5`, `ed199e3`, the code in `89fb9c6`, `26d78dd`, `6fef4cb`,
  `939435e`, and now `0748048`) stays on the branch, and several of those edit
  files `60d0118` created. It would conflict, and if forced through it would
  leave a half-existing tooling directory. It has been removed rather than
  reworded.

**What the branch actually contains**, by round:

| Round | Code commits | Documentation commits |
| --- | --- | --- |
| 1 | `6df9417`, `60d0118` | `d8e585b`, `97697d4`, `5267856` |
| 2 | `2a7b2d5` | `b2547ec`, `ef4a9c5` |
| 3 | `ed199e3` | `772353e`, `ef2f9ef` |
| 4 | — **mixed**: `89fb9c6` is code *and* documentation in one commit — | |
| 5 | `26d78dd`, `6fef4cb` | `b4067b0` |
| 6 | `939435e` | `59437f0` |
| 7 | none | `dc21f48` |
| 8 | `0748048` | this commit |

**The three commands below are the only partial reverts I am willing to state.**
All are code-only in the strict sense — every commit named touches nothing but
`platform/tooling/local-demo/baseline.mjs` and its test, confirmed with
`git show --name-only` — and all leave **every** documentation commit, including
this file, on the branch.

| To undo | Command | State afterwards |
| --- | --- | --- |
| Round 8's code, keeping rounds 1–7 | `git revert 0748048` | `readBaseline` returns to round 6's behaviour: a missing row set fails immediately, 4 × 500ms. **Not recommended** — that is the behaviour the Product Owner's reproduced failure disproved. Every handoff round remains and round 8's account is now stale |
| Rounds 6–8 code, keeping rounds 1–5 | `git revert 0748048 939435e` | `readBaseline` returns to the round 5 retry: both shapes retryable, 4 × 500ms. Closer to correct than reverting round 8 alone. Every handoff round remains; rounds 6 and 8 are now stale |
| Rounds 5–8 code — the whole retry, keeping rounds 1–4 | `git revert 0748048 939435e 6fef4cb 26d78dd` | `readBaseline` returns to a single attempt. It still fails closed with the same fixed sanitized messages; it just fails sooner, and the Product Owner's intermittent failure becomes a failed `demo:reset` every time it occurs. Every handoff round remains; rounds 5–8 are now stale |

Run them newest-first exactly as written. The basis for calling these clean is
checkable rather than asserted: `git log 26d78dd^..HEAD -- baseline.mjs
baseline.test.mjs` lists exactly those four commits and nothing else, so
reverting all four restores both files bit-for-bit to their `26d78dd^` content.
Each command is a prefix of the next, so any partial chain also applies cleanly —
but only newest-first. Reverting an older one while a newer one is still applied
will conflict, because each edits the loop its predecessor introduced.

### Anything reaching round 4 or earlier is a manual rollback

**I am not giving a command for it, because no single command is accurate.**
Two independent reasons, either of which is enough:

1. **`89fb9c6` cannot be reverted as code.** Reverting it also reverts this
   handoff to its round 3 text and `platform/README.md` to its round 3 text,
   silently discarding the round 4 record — while rounds 5, 6, and 7 of this
   document, committed later, stay. The result is a handoff that contradicts
   itself about which rounds happened.
2. **The lock rounds are not independently revertible**, which was already true
   and is unchanged: rounds 2, 3, and 4 each fix a defect in the previous one, so
   a partial revert leaves a lock that is worse than no lock. Round 3 without
   round 4 deletes a lock that is being created; round 2 without round 3 breaks
   live holders on a timer and can delete another process's lock. With no lock at
   all — the round 1 state — nothing pretends to be protected, which is a more
   honest failure than a lock that silently lets two resets run. So if the lock
   has to go, rounds 2, 3, and 4 go together — and that set includes the mixed
   commit.

So the honest instruction is: **roll back to round 4 or earlier by review, not by
command.** Start from `git log --oneline ccd7d44..HEAD` and the table above,
decide which files you want at which state, and construct the change deliberately
— most likely by checking out known-good file contents (`git checkout <sha> --
<path>`) rather than by reverting commits. Then update this file in the same
commit to say what you did. That is more work than a one-liner, and inventing a
one-liner that does not work is worse.

If you want none of it, the whole-branch discard at the top of this section is
exact and always correct.

**Why no documentation commit appears in either command above.** The handoff is
the review record for seven rounds, including the disclosure of every defect I
introduced and every correction a reviewer forced. Reverting it would delete that
record while leaving the branch history that makes it checkable. That is not a
recommendation to preserve a flattering account — the record is mostly unflattering
— it is that a rollback should change code, and a review trail that disappears
when someone rolls back is not a review trail. **If you revert code, edit this
file in the revert commit** to say so.

## For the reviewer (GPT/Codex, read-only)

The earlier focus lists still stand. What is new in round 8, highest value first:

1. **Whether ten attempts and 1000ms is the right bound**, given the incident it
   answers outlasted a whole `demo:reset` plus a `demo:verify`. I did not go
   wider because the condition's duration is still unmeasured and a longer wait
   mostly buys a slower failure. If you think the evidence supports 30s or a
   different shape entirely — an outer deadline rather than an attempt count —
   say so.
2. **Whether the two structural shapes should really share one budget.** They now
   do, and they may have different durations. Splitting them would let each be
   tuned separately at the cost of a second set of constants; I judged one shared
   bound simpler and no less correct while both durations are unknown.
3. **The message distinction.** It is the only diagnostic that survived rounds
   6–8, and a test pins it. Confirm nothing can make the two branches produce the
   same string, and that an exhaustion still reports the branch that actually
   fired rather than the first one encountered.
4. **The seam clamps now sit at the production values themselves.** A test may
   ask for fewer attempts or a shorter delay, never more. Check there is no gap —
   particularly that `attempts: 11` and `delayMs: 1001` both fall back to the
   production numbers rather than being partially honoured.
5. **`error.cause`.** The leak scan now covers it and asserts it stays
   `undefined`. If a future edit chains the underlying failure, that is the most
   likely route for response content to escape.
6. **Whether I have now over-corrected.** Round 6 narrowed on thin evidence;
   round 8 widened on one reproduced incident. Both were single data points
   pointing opposite ways. The difference I claim is that a reproduced failure is
   evidence of possibility while a failed reproduction is not evidence of
   impossibility — but if you think round 8 is the same mistake with the sign
   flipped, that is worth saying plainly.

What was new in round 6, and still worth your attention:

1. **Whether the probe measured the right thing.** Its central claim is that an
   unready local database fails with a non-zero exit rather than a malformed
   envelope, and everything in round 6 follows from that. It was measured across
   four container transitions on one machine. If there is a readiness state my
   two phases skipped — a partially healthy Kong, a pooler that accepts a
   connection and then answers oddly, a `db reset` that fails midway — that state
   is where the classification could still be wrong.
2. **Whether narrowing was the right option for finding 2.** I chose fail-fast
   for missing/non-array rows because I could not prove those shapes transient
   and the measurement pointed away from them. The cost, if the Product Owner's
   incident *was* one of those shapes, is that it now fails on attempt 1 instead
   of attempt 4 — the same failure, sooner, with a message that identifies it. I
   think that is strictly better than a silent four-attempt delay. Check that
   reasoning.
3. **Whether keeping the budget at 1.5s is defensible given I could not
   reproduce the incident.** My argument is that 0ms was needed in 4 of 4
   measurements, that three successful database round-trips precede the baseline
   read, and that enlarging against an unmeasured window is guessing. The
   opposite reading — that an unreproduced intermittent fault deserves a wider
   margin precisely because it is not understood — is not unreasonable, and it
   is the Product Owner's call more than mine.
4. **The new fixed message.** *"The baseline query returned no row set."* Check
   it says nothing about what was actually received, and that the branch cannot
   be reached with a valid one-row document.
5. **That the probe is not committed.** Argued under changed files and
   limitations. If you think this evidence should be reproducible from the repo
   rather than from a description, say so — it is a real trade and I picked one
   side of it.
6. ~~**The rollback table's honesty.** It is now labelled implementation-only
   with a column for what documentation survives.~~ **You found this was still
   wrong; round 7 rewrote it. Re-check it.** Specifically: that `939435e` and
   `939435e 6fef4cb 26d78dd` are the only partial reverts now offered, that both
   really are code-only, that the round-composition table matches
   `git show --name-only` for all seventeen commits, and that refusing to give a
   command for round 4 and earlier is the right call rather than an evasion.

What was new in round 5, and still worth your attention:

1. **The claim that "not exactly one row" cannot be a state report.** The whole
   fix rests on it: `BASELINE_SQL` has no outer `from` and no outer predicate, so
   one row is the only cardinality the database can produce, and any other
   cardinality is about readiness rather than about the demo's contents. If there
   is a way for that query — or for the CLI's envelope around it — to legitimately
   carry zero or two rows for a reason that reflects real state, then this retry
   masks it and the finding is worse than the bug.
2. **Whether the non-retry list is drawn in the right place.** Malformed JSON and
   a non-integer count are the two I refused to retry for lack of proof. If you
   believe one of them is provably transient on a cold stack, that proof is worth
   more than my caution — but it has to be a proof, not a plausible story.
3. **That a count mismatch cannot be reached by the retry loop.** My argument is
   structural: a mismatching baseline *parses*, so it returns normally and never
   enters the catch. Check that there is no response shape that both fails
   `parseBaselineRow` on row count and would have been a genuine mismatch.
4. **The `retryable` flag as a channel.** It is a boolean set at two literal
   throw sites and read in one place. Confirm it cannot be influenced by response
   content, and that no third code path can set it.
5. **The four injected seams** (`query`, `attempts`, `delayMs`, `wait`).
   Defaulted parameters, used only by the tests. Writing this list is what made
   me notice that `attempts: 0` or `NaN` would have skipped the loop entirely and
   thrown `undefined`, so both numeric seams are now clamped to a ceiling and fall
   back to the default when out of bounds, with a test for each. Confirm no
   command passes anything, and that the clamps have no gap.
6. **Whether 4 attempts × 500ms is the right budget** given the incident it is
   answering, where the condition outlived an immediate `demo:verify`. I argue a
   larger budget buys a slower failure rather than a better one, and that the
   number should move on measurement. You may read the evidence differently.
7. **The leak test's own coverage.** It scans `message`, `String(error)`,
   `stack`, and every own property name and value for a sentinel. If there is a
   surface it misses — a getter, a cause chain, something a formatter would
   print — that is where the next leak lives.

What was new in round 4, and still worth your attention:

1. **Every state the lock file can be in, enumerated.** Three rounds of defects
   here have all been the same shape: a state that exists for milliseconds and was
   not in my head when I wrote the rule. The states I now believe exist are
   absent, empty, partially written, well-formed and live, well-formed and dead,
   well-formed and foreign, and unreadable-garbage. The tooling deletes exactly
   one of them automatically. **If there is an eighth state, that is where the
   next defect is.** I would rather you find it than the Product Owner.
2. **Whether refusing forever on an unreadable record is acceptable.** It cannot
   be recovered without a human deleting the file. I argue that is right — an
   empty lock file is indistinguishable from a lock being taken, so any automatic
   rule here is a guess — but it does mean a corrupted lock file blocks all
   destructive demo commands until someone acts.
3. **The claim-file argument in `lock.mjs`.** The correctness claim is a chain,
   and it is only as strong as its weakest link: the lock's owner is proven dead;
   a dead process cannot release its own lock; only the single claim holder may
   unlink; therefore nothing can change the lock file between the nonce check and
   the unlink. Attack that chain. The place I would look first is whether "proven
   dead" can go stale — the pid check happens before the claim is taken, and the
   nonce re-check after, which is why both exist.
4. **The claim file is never broken automatically.** That is deliberate, and it
   trades a vanishingly rare manual step for the removal of a whole class of race.
   Judge whether that is the right call, or whether a bounded automatic recovery
   would be acceptable given the window is milliseconds.
5. **Whether refusing is right when recovery is contended.** A second process
   arriving during a recovery refuses rather than waiting for the claim to clear.
   Retrying would be friendlier; refusing is one fewer state to reason about.
6. **The temporary-file pattern in `credentials-file.mjs`.** It deletes files
   another process wrote, which is only safe because writing one happens under the
   lock. Check that the name pattern cannot match anything but this tooling's own
   temporary files, and that the scan cannot reach outside `.local-demo/`.
7. **Whether removing the raw-CLI advice went too far.** A maintainer debugging a
   fixture failure now has an exit code and a command name, and has to decide for
   themselves to run the CLI. I think the exposure trade is right; you may think
   the tooling should offer a maintainer-only escape hatch instead.
8. **The `isAlive` and `onBreakWindow` seams.** They exist for the tests. Confirm
   they cannot be reached from a command, and that no production path passes
   anything but the defaults.
9. **`source-safety.test.mjs`.** Still only as good as its comment- and
   string-stripping, and each round adds scans that depend on it. Look for a way
   to write a forbidden call, or a raw-CLI invitation, that the stripper hides.
10. **Still open from round 2:** whether `demo:web`/`demo:android` should start a
   stopped stack themselves rather than refusing; and whether generating health
   values at run time is the right reading of AC8 or an over-correction.

**Not done, deliberately:** no merge, push, deploy, publish, hosted-Supabase link,
remote migration, `db push`, branch deletion, worktree removal, or `.env.local`
access. No acceptance criterion was reworded, and AC3 is left open rather than
argued into met.
