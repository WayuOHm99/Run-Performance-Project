# TASK-016 handoff — Coach Daily Check-in Review (Mobile)

Status: **Implementation complete. All verification complete, including the local
database authorization suite.** Stopped for GPT/Codex read-only review. Not
merged. Worktree not removed.

Round history:

- **Round 1** — implementation. The database suite was recorded as **blocked**;
  the Docker daemon was unreachable in that session.
- **Round 2** — verification and documentation only. The database suite was run in
  full and passed. No implementation code, test, or migration changed.
- **Round 3** — the Medium revoked-grant race is **fixed**, by approved scope
  deviation, with one final active-consent revalidation (**stage d**) after the
  health-bearing read. All verification re-run, including pgTAP and database lint.
- **Round 4** — the Medium consent-pair **key collision** is fixed: the pair key is
  now `JSON.stringify([teamId, athleteProfileId])` instead of a space-joined
  string. All verification re-run again.
- **Round 5** — test hygiene and documentation only. A literal `0x00` byte is
  removed from `domain.test.ts`, the injectivity test stops over-claiming, and the
  stale zero-NUL assertion in this document is corrected against a fresh scan. No
  runtime implementation changed; the database suite was not re-run, and Round 4's
  passing evidence stands (see below).

Corrections in this document are written as explicit "Round *n* said X, here is
why it was wrong" notes rather than silent overwrites, so the change is auditable.

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
| 4 | `d67d71d` | 2 | `docs(task-016): close out verification and correct the handoff` |
| 5 | `458b3ed` | 3 | `fix(coach): revalidate consent after the health-bearing read` |
| 6 | `8bbd647` | 3 | `docs(task-016): document stage d and correct the final statistics` |
| 7 | `f7720d1` | 4 | `fix(coach): make the consent-pair key collision-free` |
| 8 | `4ae445d` | 4 | `test(coach): assert pair-key injectivity as a property, not one example` |
| 9 | `9b6b1a7` | 4 | `docs(task-016): record the collision fix and both statistic baselines` |
| 10 | `434d39b` | 5 | `test(coach): write the NUL delimiter as an escape, not a raw byte` |
| 11 | *this commit* | 5 | `docs(task-016): correct the NUL claim and close out round 5` |

All eleven are on `feat/TASK-016-coach-daily-check-in-review-mobile`, cut from
`4ac2bfe`. **No existing commit was amended or rewritten.** Commit 11 touches only
`docs/`; its SHA cannot be printed inside itself, so it is identified by position
and resolvable with `git log --oneline 4ac2bfe..HEAD`.

**Five** commits touch `platform/` — `c31dbdb` (the feature), `458b3ed` (stage d),
`f7720d1` (the injective key), `4ae445d` (the injectivity property test), and
`434d39b` (the Round 5 test-source hygiene fix). Of those, **four change runtime
code**; `434d39b` changes a test source only. The other six commits are
documentation. Every round kept the two kinds separate as instructed: no code
commit carries a documentation-only edit, and no documentation commit carries
code.

One correction to disclose: the packet commit was first created with a shell
here-string that the Bash tool mangled into the literal subject `@`. It was
immediately re-created with `git reset --soft HEAD~1` plus a fresh commit,
before any other work. That touched only the commit this session had just
created seconds earlier; no pre-existing commit and no approved-base history was
altered. `a6229ff` is the corrected commit.

## Changed files

Two baselines are recorded, because they answer two different questions and one
of them cannot be measured from inside this file without care.

**Final state at `HEAD`** — what the branch actually delivers:

> **22 files changed, 6329 insertions(+), 6 deletions(-)**
> (`git diff --shortstat 4ac2bfe..HEAD`)

These figures were computed from the **staged** final documentation state — this
file and the packet included, exactly as committed — then written back in place
without changing any line count, so they describe the commit they appear in. The
substitution was re-staged and re-measured to confirm the number is a fixed point
rather than a snapshot that its own insertion invalidated.

**Last commit touching `platform/`, `434d39b`** — everything except the closing
documentation:

> **22 files changed, 6244 insertions(+), 6 deletions(-)**
> (`git diff --shortstat 4ac2bfe..434d39b`)

The difference between the two is documentation only.

The file count has been **22 since Round 1**; every round since has changed
existing files in place, adding none. Insertions grew 5079 -> 5378 -> 5875 -> 6170
-> 6244 across the rounds. *(Round 1's 5079/21-file figure was measured before the
handoff was committed and omitted this file; Round 2 corrected the count to 22.)*

Line counts per file at `434d39b`, from `git diff --numstat`:

| File | + | - |
| --- | --- | --- |
| `.../coach-check-in/source-safety.test.ts` | 742 | 0 |
| `.../coach-check-in/coach-review-repository.test.ts` | 681 | 0 |
| `.../coach-check-in/domain.test.ts` | 667 | 0 |
| `.../coach-check-in/domain.ts` | 563 | 0 |
| `docs/app/tasks/TASK-016-coach-daily-check-in-review-mobile.md` | 511 | 0 |
| `docs/app/handoffs/TASK-016.md` | 496 | 0 |
| `.../coach-check-in/query-options.test.ts` | 358 | 0 |
| `.../coach-check-in/coach-review-repository.ts` | 337 | 0 |
| `.../coach-check-in/test-fixtures.ts` | 324 | 0 |
| `.../coach-check-in/logging.test.ts` | 233 | 0 |
| `.../coach-check-in/view-state.test.ts` | 215 | 0 |
| `.../coach-check-in/coach-check-in-section.tsx` | 207 | 0 |
| `.../coach-check-in/view-state.ts` | 184 | 0 |
| `.../coach-check-in/failure-probe.ts` | 133 | 0 |
| `.../coach-check-in/athlete-check-in-card.tsx` | 122 | 0 |
| `.../coach-check-in/copy.ts` | 114 | 0 |
| `.../coach-check-in/query-options.ts` | 98 | 0 |
| `platform/apps/mobile/src/lib/query/keys.test.ts` | 94 | 0 |
| `.../coach-check-in/errors.ts` | 94 | 0 |
| `.../coach-check-in/use-coach-check-in-review.ts` | 36 | 0 |
| `platform/apps/mobile/src/lib/query/keys.ts` | 18 | 0 |
| `platform/apps/mobile/src/app/coach/index.tsx` | 10 | 6 |

Files changed by Round 5: `coach-check-in/domain.test.ts` (code commit), plus this
handoff and the packet (documentation commit).

`coach/index.tsx` is the **only** pre-existing file with deletions, and its 6
removed lines are exactly the Team placeholder `InfoCard`.

Files changed by Round 4 (`git diff --name-only 8bbd647..4ae445d`):
`coach-check-in/domain.ts` and `coach-check-in/domain.test.ts`. Two files, both
owned, both inside the feature directory.

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
| 5 | Stage c skipped with no active grants (and stage d too) | **met** — asserted on the recorded table list |
| 6 | Overflow above 100 fails, never truncates | **met** — `capacity` failure with its own escalation wording; retry control still offered per the packet |
| 7 | Every fail-closed condition rejects the whole load | **met** |
| 8 | Key auth-scoped and health-free | **met** |
| 9 | Eight cache overrides hold against real `QueryClient`/`QueryObserver` | **met** — verified against deliberately hostile defaults |
| 10 | Health hidden during refresh and after a failed refresh | **met** |
| 11 | No logging, persistence, or write | **met** — AST + runtime |
| 12 | Every failure message from a fixed sanitized set | **met** |
| 13 | All verification commands pass | **met** — including the local database suite, run in Round 2 |
| 14 | Mutation evidence recorded | **met** — 12 mutations across rounds, all detected, all reverted |
| 15 | Revocation between stage b and stage c fails the whole load; a new grant is not attached | **met** (Round 3) — 12 stage-d tests |
| 16 | The consent-pair key is injective; a revoked pair is never masked by a colliding one | **met** (Round 4) — 8 collision tests + 2 property tests over 17 candidate delimiters |

## Safe verification counts

Run from `platform/` unless noted.

| Command | Result |
| --- | --- |
| `corepack pnpm install --frozen-lockfile` | exit 0 |
| `corepack pnpm format:check` | exit 0, all files match |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| `corepack pnpm test` | exit 0 — **40 test files, 748 tests, 0 failures** (720 before stage d, 738 after it, 748 after the Round 4 collision work) |
| focused `vitest run src/features/coach-check-in src/lib/query` | exit 0 — **8 test files, 163 tests, 0 failures** (135 → 153 → 163) |
| `corepack pnpm dlx expo-doctor@latest` (from `apps/mobile/`) | exit 1 — **20/21 checks pass**; the single failure is the known pre-existing patch drift (see limitations) |
| Android Expo export | exit 0 — 1 bundle, 1 metadata file |
| Web Expo export | exit 0 — **13 static routes, unchanged from before this task** |
| `git diff --check` | exit 0, clean |
| working tree after all verification | clean |

Baseline before this task was 596 workspace tests (TASK-014); it is **748** now,
including TASK-015's additions. Round 3 added **18** tests (12 stage-d repository
regressions, 6 `pairsStillActive` domain cases). Round 4 added **10** more: 8
collision regressions and 2 injectivity property tests.

**A Round 1 figure is corrected here.** Round 1 and 2 reported the web export as
"10 routes". The real count is **13 static routes** — the earlier number came
from reading a truncated tail of the export output, not from a shortened list.
The route list itself is unchanged by this task and always was: no file was added
under `src/app/`, and `/coach` remains the only coach surface. The claim that
followed from it — that no route was added — is unaffected and still holds.

### Round 5 verification

Re-run after the test-source change (`434d39b`):

| Command | Result |
| --- | --- |
| `corepack pnpm format:check` | exit 0 |
| `corepack pnpm lint` | exit 0 |
| `corepack pnpm typecheck` | exit 0 |
| focused `vitest run src/features/coach-check-in src/lib/query` | exit 0 — **8 files, 163 tests, 0 failures** |
| `corepack pnpm test` | exit 0 — **40 files, 748 tests, 0 failures** |
| `git diff --check` | exit 0 |
| byte-level NUL scan over 22 owned files | **0** |
| `rg` text-file probe on `domain.test.ts` | 3 matches printed with line numbers and content |

Counts are **identical** to Round 4 in both suites, which is the expected outcome:
the change swapped a raw byte for the escape sequence denoting the same character,
so the NUL delimiter case still runs and nothing else moved.

**The local database suite was not re-run, by instruction.** Round 5 changed one
test source and two documents; it touched no migration, policy, function, or
runtime module, and nothing it changed can affect a pgTAP result. Round 4's
evidence therefore stands unmodified and is preserved below rather than restated
as if it had been re-executed: **5 files, 583 assertions, `Result: PASS`, 0 lint
findings, 0 containers remaining**.

### Local database authorization suite — **RUN AND PASSED** (Round 2; re-run in Rounds 3 and 4; not re-run in Round 5)

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

**Round 3 re-ran the entire suite** after the stage-d change, with identical
results: `db:start` 0, `reset --no-seed` 0, pgTAP **5 files / 583 assertions /
`Result: PASS`**, `db lint` 0 findings, `db:stop` 0, **0 containers remaining**.
Stage d touches no migration and no policy — it re-uses the existing
`sharing_grants_select_active_for_coach` read — so an unchanged pgTAP result is
the expected and correct outcome, not a sign the suite missed the change. What
covers the change is the 12 new repository regressions and the mutation evidence
below.

**Round 4 re-ran it again** after the collision fix, with identical results:
`db:start` 0, `reset --no-seed` 0, pgTAP **5 files / 583 assertions /
`Result: PASS`**, `db lint` **0 findings**, `db:stop` 0, **0 containers
remaining**. The pair key is a client-side data structure and touches no SQL, so
an unchanged database result is again the expected outcome.

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
and the file was restored with `git checkout`. Rounds 1–2 baseline is **135
passed / 0 failed**; the Round 3 baseline is **153 passed / 0 failed**. Only
counts are recorded.

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
| M5 | stage-d revalidation check neutralized — the exact Round 3 regression | `coach-review-repository.ts` | **1 file, 4 tests failed** |
| M6 | `pairsStillActive` made bidirectional (a new grant also fails the load) | `domain.ts` | **2 files, 6 tests failed** |
| M7 | stage d reuses the stage-b result instead of re-reading | `coach-review-repository.ts` | **1 file, 8 tests failed** |
| M8 | ambiguous space-delimited pair key restored — the exact Round 4 regression | `domain.ts` | **1 file, 3 tests failed** |
| M9a | pair key joined on `\|` instead | `domain.ts` | **1 test failed** |
| M9b | pair key joined on `:` instead | `domain.ts` | **1 test failed** |
| M9c | pair key joined on `-` instead | `domain.ts` | **1 test failed** |

M2 and M3 were each run twice because the first variant left a second defence in
place; M2b and M3b remove that too, which is what shows both layers are covered
rather than only one.

**M8 is the mutation the Round 4 requirement asks for**: restoring the
space-delimited encoding fails the collision regressions.

**M9 is the more interesting result, and it exposed a real gap in my own test.**
When first run — against the Round 4 fixtures alone — swapping `JSON.stringify`
for a pipe- or colon-joined template left **all 161 tests passing**, because those
fixtures collide only under a space. The regression proved the *reported* bug was
fixed while leaving the whole class of bug undetected. Commit `4ae445d` therefore
adds an injectivity **property** test over 17 candidate joining characters, and
M9a–M9c are the re-run showing every delimiter is now caught. Reported here
because the first M9 run is exactly the kind of near-miss that a summary claiming
"all mutations detected" would have hidden.

**M5 is the mutation the Round 3 requirement asks for**: with the revalidation
removed, the revoked-grant regressions fail. **M7 matters just as much** — it
proves the stage-d read is a genuine second query rather than a re-inspection of
data already in hand, which is the way a revalidation most plausibly rots into
theatre. **M6** proves the one-directionality is deliberate and covered: making
the check symmetric breaks the "a newly granted pair is not attached" test.

**Every mutation was reverted.** After the last revert, `git status --porcelain`
was empty and the full suite returned **40 files / 748 tests / 0 failures**.

*(Rounds 1–2 recorded this line as 720, which was the count at the time they were
written. It was left stale through Round 3, where the true post-revert count was
738. It is now stated at the current value and will move again if the suite grows,
so it is pinned to a round: **748 as of Round 4**.)*

**No mutated code is committed**; in every round the mutations were applied only
after the corresponding code commit existed, precisely so `git checkout` could
prove the restoration.

**A defect I introduced and fixed, disclosed in full.** `c31dbdb` contained a
literal NUL byte (`0x00`) in `domain.ts`, where the grant-pair key separator
should have been a space — the result of a bad character in my original write, not
of any mutation run. It made `file(1)` report the source as `data` rather than
text. Runtime behaviour was correct throughout: a NUL is a valid JavaScript string
character and worked as a separator, every test passed, and no output was
affected. It is fixed in `458b3ed`, which routed both call sites through one named
`pairKey` function; `f7720d1` then replaced the delimiter approach entirely with
`JSON.stringify`, so there is no separator character left to get wrong. Prettier, ESLint, and
TypeScript all passed with the NUL present, so **no existing gate would have
caught it** — worth noting for the reviewer.

**That claim was wrong, and Round 5 fixes it.** Round 3 wrote "a scan of every
TASK-016-owned file now reports zero NUL bytes". That was true when it was run,
but Round 4 then appended a delimiter list to `domain.test.ts` containing a
**second** literal `0x00`, and the stale sentence was carried forward unchecked
into the Round 4 handoff. The claim was therefore false at the moment it was last
published.

Both NULs came from **one root cause**, not two independent slips: the tooling
path used to write those files collapsed a doubled backslash, turning an escape
sequence into the character it denotes. In `domain.ts` an intended space became
`0x00`; in `domain.test.ts` an intended non-breaking space did.

The consequence is tooling-level rather than behavioural. `file(1)` reported the
source as `data`, and **ripgrep classified it as binary and suppressed line
content** — which silently degrades every grep-based review and search over the
file, including the kind a reviewer would run to audit this task.

`434d39b` replaces the byte with the source escape sequence, so the runtime value
is unchanged — a one-character string whose code point is zero, verified with
`node -e` — and the NUL delimiter case still runs. Test counts are identical
before and after (163 focused, 748 workspace).

**A fresh byte-level scan was run for this handoff**, not carried over:

| Probe | Result |
| --- | --- |
| `tr -dc '\000' < FILE \| wc -c` over all **22** owned files | **0** literal NUL bytes, total across every file |
| `file(1)` on `domain.ts` and `domain.test.ts` | `JavaScript source, Unicode text, UTF-8 text` |
| `rg -n "CANDIDATE_DELIMITERS" domain.test.ts` | prints **3 matches with line numbers and content** — text, not a binary-suppression notice |
| `node -e` on the escape | length `1`, char code `0` — the NUL case is preserved |

No lint, format, type, or test gate detects a stray control byte in source. If that
matters beyond this task, a repository-level check would need adding — deliberately
**not** done here, since this task owns no tooling configuration.

**The root cause recurred a third time while this very section was being written**,
and is reported rather than quietly repaired. Writing the scan command into the
table above put the text for a NUL escape through the same shell path, which
collapsed it and wrote a real `0x00` into this handoff. It was caught by the
verification step immediately after, repaired, and the file now scans clean — but
it is the clearest possible evidence that the mechanism is the tool path and not
carelessness about any one character. Every subsequent edit avoided backslash
sequences in that path entirely, constructing the byte numerically instead.

For the reviewer: the practical mitigation is a byte-level scan **after** writing,
never trusting the write. That is what the table above records, and it is the only
reason two of the three instances were caught at all.

One void run is disclosed for honesty: the first M4a attempt used a pattern that
did not match (the file has CRLF endings), so nothing was mutated and the suite
passed. That run proves nothing and was re-done correctly; the table records only
the valid run. Round 3's first M5 attempt likewise failed to match (CRLF plus a
Prettier rewrap), was a no-op, and was re-done correctly; only the valid run is
recorded.

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
- **Consent is re-checked after the health values arrive.** Stage d (Round 3)
  repeats the stage-b grant read once stage c has returned and fails the whole
  load if any pair it was performed for has gone. This never was an access-control
  hole — RLS refuses the rows the instant consent lapses — but it removes a
  **false statement about a person's health record**: the screen no longer says an
  athlete "has not checked in" when what happened is that they revoked consent.
- **The consent-pair comparison is unambiguous.** The stage-d check keys pairs by
  `JSON.stringify([teamId, athleteProfileId])`. Under the previous space-joined
  key, a revoked pair could be masked by a *different* active pair that happened to
  collide with it, which would have re-opened the very disclosure stage d was added
  to close. Fixed in `f7720d1`.
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
   **Round 3 narrowed this window but did not close it:** stage d confirms consent
   held up to the moment the revalidation returned, so the exposure now begins
   there rather than at the health read. A revocation landing after stage d is
   still only reflected on the next query.
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
4. **FIXED in Round 3 — a revoked grant racing the health-bearing read.** Round 2
   recorded this as an open Medium: a grant revoked between stage b and stage c
   made the embed empty, and the athlete rendered as `ยังไม่ได้เช็กอิน` — stating as
   fact that they had not checked in when they had actually withdrawn consent.
   Stage d now re-reads consent after the health values arrive and fails the whole
   load if any pair used by that read has gone. **The residual behaviour is a
   retryable error rather than a wrong statement**, which is the intended trade.
   A membership revocation in the same window was already failing the load, via a
   missing expected profile, and still does.
5. **Identifiers are not shape-checked as UUIDs anywhere in this feature.**
   `isNonEmptyString` accepts any value with a non-blank trimmed form, so
   `"team a"` is a valid identifier as far as this code is concerned. That is what
   made the old delimiter-joined key unsafe. The key is now injective regardless,
   and no other code path in the feature joins identifiers into a string — but if a
   future change adds one, it must not assume whitespace is absent.
6. **Stage d costs one extra `sharing_grants` read per load.** Accepted: it is a
   small, indexed, non-health read, and it is skipped entirely when nobody shares.
7. **Known pre-existing Expo patch drift persists** and is **out of scope**:
   `expo` found `56.0.17` vs expected `~56.0.18`, `expo-router` found `56.2.16` vs
   expected `~56.2.17`. **No dependency was changed.** 20/21 Expo Doctor checks
   pass.
8. **Supabase CLI `v2.110.0` is available; `v2.109.1` is pinned and installed.**
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

1. `coach-review-repository.ts` stage d and `pairsStillActive` — the Round 3 fix.
   Specifically: is one-directionality right? It means a grant made mid-load is
   silently deferred to the next query rather than surfaced. I believe deferring is
   correct because no health value was fetched for that pair, but it is a
   product-visible choice.
2. `domain.ts` — the grant-pair composition and every fail-closed branch. This is
   where a wrong athlete could be attached to a team.
3. `view-state.ts` — the branch order in `readCoachReviewView`. The error check
   preceding the data check is the whole "hide stale health on a failed refresh"
   guarantee.
4. `coach-review-repository.ts` — stage ordering, the skip conditions, and the
   referenced-table `order`/`limit` pair.
5. Whether limitation 2 (blank display name fails the load) is the right product
   call.
6. Whether the 100-pair cap is right, and whether offering the retry control on a
   capacity failure — which the packet specifies and the UI does — is the
   behaviour you want, given that retrying cannot succeed until the number of
   active pairs drops.
7. Whether trading the old wrong-wording behaviour for a retryable error is the
   right call for a coach whose athletes revoke often (limitation 4).
8. `pairKey` and its property test. The fix is at the encoding layer rather than in
   `isNonEmptyString`; if you would rather the guard rejected whitespace outright,
   that is a different and also-defensible design, and it would need its own
   regression because it changes what counts as a valid grant row.

**Not done, deliberately:** no merge, push, deploy, publish, hosted-Supabase
link, remote migration, branch deletion, or worktree removal.
