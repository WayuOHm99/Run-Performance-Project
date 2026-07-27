# TASK-010 Handoff — Secure Session Storage Hardening

This is the sanitized handoff for the read-only reviewer (ChatGPT/Codex). It
contains no credential, key, token, database URL, hosted identifier, or real
user data. Everything below can be pasted into a review tool as-is.

```text
Task:            TASK-010 — Secure Session Storage Hardening
Writer:          Claude Code (sole writer)
Reviewer:        ChatGPT/Codex (read-only). No AGY reviewer.
Branch:          feat/TASK-010-secure-session-storage
Worktree:        isolated, based on feat/mobile-foundation
Base commit:     8a6c3ab57326df4b68932d045e7d4d3ae04fdca6
Round 1 implementation:  b6fe9b2eff5cd4e08b105f0209f1919c245e60da
Round 1 handoff:         ac415e4c306d6c90b5ac9fca635b458bd52e633b
Round 2 fix (F1, F2):    8dd6ae717814b57e392658c09be29ac4d584f3d0
Round 2 handoff:         documentation-only follow-up; this is the head
```

Nothing has been merged, pushed, deployed, linked, or migrated. The branch and
worktree are left in place.

## Round 2 — Codex findings 1 and 2

Both findings were accepted as correct. Neither was disputed.

| Finding                                                                | Severity | Status                                                            |
| ---------------------------------------------------------------------- | -------- | ----------------------------------------------------------------- |
| 1 — protected-path deny rules do not cover worktrees                   | High     | **Fixed**, but the rules are **unverified in-session**; see below |
| 2 — partial storage removal may leave protected routing open in memory | Medium   | **Fixed** and proved by mutation testing                          |

Finding 1's remediation carries an important caveat: Claude Code reads its
settings at launch, so a session cannot validate its own settings edits. The
rules are written and statically validated but **must be confirmed in a fresh
session** before being trusted. Details in "Protected-path incident and
remediation".

### Finding 2 — how it was fixed

Codex was exactly right about the mechanism. `AuthProvider.signOut` awaited
`signOutGlobally()` and only then cleared the identity and cache. Supabase's
`_removeSession` stops before emitting `SIGNED_OUT` when `storage.removeItem()`
throws, and TASK-010's adapter throws by design when either backend fails to
remove its half. So on precisely the failure that matters, no `SIGNED_OUT`
arrived, the awaited call rejected, and the previous identity plus its protected
routes stayed live until the app restarted.

The fix inverts the order: **close locally first, then talk to the server.**

- A new `sign-out-initiated` event in `auth-state.ts` settles the reducer
  straight to signed-out — identity `null`, candidate `null` — and advances
  `appliedToken` to the newly claimed token. That second part is load-bearing:
  every in-flight validation carries an older token, so `canApplyValidation`
  rejects it on the equality check and a late result cannot resurrect the
  identity that was just closed.
- It settles to `settled`, not `verifying`, deliberately. `verifying` would have
  stranded the user on the loading screen for as long as Supabase withheld its
  event — which, when storage removal throws, is forever. `settled` makes the
  gate report `signed-out` and route to sign-in at once.
- `performSignOut` in the new `sign-out.ts` dispatches that event and clears the
  auth-scoped cache **before any `await`**, so there is no suspension point at
  which the old identity is still readable. The remote call still runs, and its
  failure is still reported, but only after local access is already closed.
- The adapter's behaviour is unchanged: it still attempts both backends and
  still reports a sanitized failure.

The orchestration was extracted out of the component specifically so this
ordering is testable against the real reducer and the real gate without adding a
renderer dependency.

**Mutation-tested.** Reverting `performSignOut` to the old await-first order
fails 4 of the new tests, including "closes athlete and coach routing when
sign-out throws and no SIGNED_OUT arrives". The tests encode the reported defect
rather than merely passing alongside it.

## What changed and why

TASK-009 persisted the Supabase session as plaintext JSON in AsyncStorage, and
its own handoff named that "the single most important follow-up", mandatory to
close before pilot release or before any health data is added. This task closes
it.

| Where        | Before (TASK-009)                       | After (TASK-010)                            |
| ------------ | --------------------------------------- | ------------------------------------------- |
| AsyncStorage | the full session JSON, in plaintext     | a versioned AES-256-GCM ciphertext envelope |
| SecureStore  | not used                                | the AES-256 key, and nothing else           |
| Web          | browser storage, `persistSession: true` | no storage, `persistSession: false`         |

The session JSON, access token, refresh token, email, user id, and claims are
never written to either backend in readable form.

## Changed files

### New — mobile session storage (5)

| File                                              | Role                                                              |
| ------------------------------------------------- | ----------------------------------------------------------------- |
| `src/lib/supabase/secure-session-storage.ts`      | the adapter: ports, envelope, failure matrix. No platform import. |
| `src/lib/supabase/native-session-storage.ts`      | thin binding onto Expo SecureStore, Expo Crypto, AsyncStorage     |
| `src/lib/supabase/auth-options.ts`                | the pure web/native persistence decision                          |
| `src/lib/supabase/secure-session-storage.test.ts` | 40 tests, the full negative matrix                                |
| `src/lib/supabase/auth-options.test.ts`           | 3 tests, web cannot persist                                       |

### Modified (6)

| File                                | Change                                                              |
| ----------------------------------- | ------------------------------------------------------------------- |
| `src/lib/supabase/client.ts`        | uses the encrypted adapter on native; web persists nothing          |
| `platform/apps/mobile/package.json` | `+ expo-secure-store ~56.0.4`, `+ expo-crypto ~56.0.4`              |
| `platform/pnpm-lock.yaml`           | regenerated for the above                                           |
| `platform/apps/mobile/app.json`     | `expo-secure-store` config plugin                                   |
| `platform/apps/mobile/README.md`    | new "Session storage" section; replaces the old SecureStore warning |
| `docs/app/PRODUCT-CHARTER.md`       | the approved Garmin restriction                                     |

### New — documentation (2)

`docs/app/tasks/TASK-010-secure-session-storage.md`, `docs/app/handoffs/TASK-010.md`

### Round 2 — Finding 1 (deny rules)

| File                                   | Change                                                                                                  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `docs/app/claude-app-settings.json`    | worktree deny rules for all nine protected paths; canary rules. 34 → 63 rules, none removed or weakened |
| `docs/app/permission-canary/CANARY.md` | **new** synthetic verification fixture                                                                  |
| `docs/app/CLAUDE-CODE-SETUP.md`        | worktree rule explanation; canary-based verification; settings-load-at-launch warning                   |

### Round 2 — Finding 2 (sign-out)

| File                                   | Change                                                        |
| -------------------------------------- | ------------------------------------------------------------- |
| `src/features/auth/sign-out.ts`        | **new** — `performSignOut`, closes locally before any I/O     |
| `src/features/auth/sign-out.test.ts`   | **new** — 12 integration-oriented tests                       |
| `src/features/auth/auth-state.ts`      | new `sign-out-initiated` event                                |
| `src/features/auth/auth-state.test.ts` | 4 tests for the new event                                     |
| `src/features/auth/auth-provider.tsx`  | hoisted `claimToken`; `signOut` delegates to `performSignOut` |

`auth-provider.tsx` and `auth-state.ts` are TASK-009 files. The task packet
allows "narrowly required TASK-009 auth integration/tests only if necessary to
enforce fail-closed storage behaviour", which is exactly what Finding 2 is. No
TASK-009 behaviour was otherwise altered, and all 265 original tests still pass.

**No database file changed.** TASK-010 owns no database change, and no
migration, pgTAP test, or generated type was touched. No TASK-009 auth file
needed editing: the fail-closed guarantee is enforced entirely inside the
storage boundary, and the existing gate already denies every non-ready state.

## Design

### Envelope

```json
{ "v": 1, "alg": "AES-256-GCM", "d": "<base64 nonce ‖ ciphertext ‖ tag>" }
```

Recognition is **positive**: a stored value counts as an envelope only if it
carries our version, our algorithm, and a non-empty payload. This matters
because a TASK-009 plaintext session parses as JSON perfectly well — anything
short of a positive match is purged unread.

AAD is `runperf.session|v1|AES-256-GCM|<storage key>`, so an envelope cannot be
replayed under a different storage key or relabelled as another version without
failing the tag. There is a test for exactly that.

### Ports, and why the tests are not a re-implementation

The keystore, ciphertext store, and AES-GCM primitive are injected. The tests
supply a **WebCrypto**-backed AES-256-GCM port — a real authenticated
implementation already present in the Node runtime, not a hand-rolled stand-in.
So tamper detection, nonce freshness, and AAD binding are genuinely exercised
rather than passing by construction.

The cryptographic logic is therefore not duplicated: both the production port
(`expo-crypto`) and the test port (WebCrypto) are thin adapters over a real
AES-GCM primitive, and the envelope, versioning, and failure logic exists
exactly once, in the file under test.

### Failure matrix

| Situation                                             | Result                                        |
| ----------------------------------------------------- | --------------------------------------------- |
| legacy plaintext, malformed envelope, unknown version | purge both sides, return `null`               |
| missing ciphertext (orphaned key)                     | purge both sides, return `null`               |
| missing key, wrong key                                | purge both sides, return `null`               |
| failed tag, corrupted ciphertext, decrypt error       | purge both sides, return `null`               |
| backend read threw                                    | return `null`, **do not** purge               |
| any write failure                                     | purge both sides, throw `SessionStorageError` |
| removal, one side failing                             | attempt both, then throw                      |

Two deliberate asymmetries worth review attention:

1. **A throwing backend does not purge.** An unavailable keystore is treated as
   transient, so a read failure does not cost the user data it was merely unable
   to read. Everything _provably_ unusable is destroyed instead.
2. **A failed ciphertext write purges the key too.** That makes any previous
   envelope unreadable and signs the user out. Chosen because an inconsistent
   key/ciphertext pair is the worse outcome, and because reporting success on a
   failed persist would let Supabase believe a session is stored when it is not.

## Acceptance criteria

All 20 met.

| #   | Criterion                                                                        | Where it is proved                                                        |
| --- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| 1   | No plaintext session in AsyncStorage                                             | only `encodeEnvelope` output is ever written; marker tests                |
| 2   | SecureStore holds key material only                                              | asserts a single 32-byte entry, no marker present                         |
| 3   | AsyncStorage holds a recognizable versioned envelope                             | asserts `{v:1, alg:"AES-256-GCM"}`                                        |
| 4   | No readable token, email, user id, or claims in ciphertext                       | 5 markers checked in the stored string _and_ after base64 decode          |
| 5   | >4 KB session round-trips                                                        | 6 KB payload, asserted above 4096 first                                   |
| 6   | Identical plaintext → different ciphertext                                       | two writes compared; key reuse confirmed, so it is the nonce that differs |
| 7   | Tampering fails closed                                                           | separate tests for ciphertext byte, tag byte, and nonce byte              |
| 8   | Missing key/ciphertext, malformed, unknown version, decrypt failure → no session | 7 malformed shapes + version + both missing halves + wrong key            |
| 9   | Legacy plaintext deleted → signed-out                                            | asserts both backends cleared and `null` returned                         |
| 10  | Storage failure opens no route, reuses no identity                               | drives the real `resolveAuthGate`/`canEnterRoleArea`                      |
| 11  | Partial writes cleaned up, no plaintext fallback                                 | 3 write-failure tests + a marker sweep after encryption failure           |
| 12  | Removal attempts both backends                                                   | `attempts` log asserted for both one-side failures                        |
| 13  | Nothing sensitive logged or displayed                                            | console spies across all ops incl. failures; error has no `cause`         |
| 14  | Native uses the encrypted adapter                                                | `client.ts`; `auth-options.test.ts`                                       |
| 15  | Web: `persistSession: false`, no storage                                         | asserts `"storage" in options === false`                                  |
| 16  | TASK-009 tests still pass                                                        | 265 prior tests green, unchanged                                          |
| 17  | SDK 56 compatible                                                                | versions resolved by `expo install`; Expo Doctor 21/21                    |
| 18  | Charter records the Garmin restriction                                           | new "Garmin restriction" section                                          |
| 19  | No health/secret/real data                                                       | synthetic markers and `example.test` only                                 |
| 20  | No hosted project linked or contacted                                            | no `--linked`, no remote URL, no hosted Auth call                         |

### Negative tests

All required cases are present, plus four beyond the list (modified nonce,
cross-key replay, wrong key, and "a transient read failure does not destroy
data"):

legacy plaintext · modified ciphertext · modified tag · modified nonce ·
cross-key replay · missing SecureStore key · orphaned key · missing ciphertext ·
wrong key · 7 malformed envelope shapes · unsupported version · SecureStore read
rejection · AsyncStorage read rejection · transient failure preserves data ·
encryption failure · key-write failure · ciphertext-write failure after key
write · one-side removal failure with both attempts confirmed · surviving
envelope unreadable after partial removal · duplicate writes differ · >4 KB
payload · marker unreadability · no logging · sanitized errors · web cannot
persist · storage failure cannot authorize routing

## Commands run and results

Run from `platform/`. No database stack was started: TASK-010 owns no database
change, so no pgTAP rerun was required, and none was performed.

| Command                                   | Result                                   |
| ----------------------------------------- | ---------------------------------------- |
| `corepack pnpm install --frozen-lockfile` | exit 0                                   |
| `corepack pnpm format:check`              | exit 0                                   |
| `corepack pnpm lint`                      | exit 0                                   |
| `corepack pnpm typecheck`                 | exit 0                                   |
| `corepack pnpm test`                      | **311 passed, 17 files** (was 265 in 15) |
| `corepack pnpm dlx expo-doctor@latest`    | **21/21 checks passed**                  |
| `expo export --platform web`              | exit 0, 13 static routes                 |
| `git diff --check`                        | clean                                    |
| `git status --short`                      | owned paths only                         |

### Round 2 re-run

| Command                                   | Result                                                      |
| ----------------------------------------- | ----------------------------------------------------------- |
| `corepack pnpm install --frozen-lockfile` | exit 0, already up to date                                  |
| `corepack pnpm format:check`              | exit 0                                                      |
| `corepack pnpm lint`                      | exit 0                                                      |
| `corepack pnpm typecheck`                 | exit 0                                                      |
| `corepack pnpm test`                      | **327 passed, 18 files** (+16)                              |
| `corepack pnpm dlx expo-doctor@latest`    | **21/21 checks passed**                                     |
| `expo export --platform web`              | exit 0, 13 static routes                                    |
| `git diff --check`                        | clean                                                       |
| `git status --short`                      | owned paths only; **no database or migration file changed** |

The round-2 web export used a **fully synthetic** project URL
(`https://synthetic-local.supabase.co`) rather than the real project identifier,
together with `EXPO_NO_DOTENV=1` and a synthetic publishable key. The export
succeeds without any hosted-project identifier, so no real value was needed.

**Mutation test.** Reverting `performSignOut` to the old await-first ordering
fails 4 tests — both routing cases, the ordering case, and the exposure trace —
confirming the new tests encode the reported defect rather than passing
alongside it. The implementation was restored immediately and the full suite
re-run.

The web export ran with `EXPO_NO_DOTENV=1` plus synthetic public values, so the
local `.env.local` never entered the process and no real key could reach a build
artifact. `.env.local` was never read.

Two genuine failures were found and fixed before the results above: `tsc`
rejected the test file's `Uint8Array`/`BufferSource` variance and its use of
`.catch` on `SupportedStorage`'s possibly-synchronous return type, and Prettier
reformatted two files.

## Dependencies and Expo configuration

`expo install` resolved the SDK 56-compatible versions, which were then added
through the pnpm workspace and pinned in `platform/pnpm-lock.yaml`:
`expo-secure-store@~56.0.4` and `expo-crypto@~56.0.4`. No third-party AES
library was added. AsyncStorage was **not** removed; it remains the ciphertext
store.

The SecureStore config plugin is configured deliberately:

```json
[
  "expo-secure-store",
  { "faceIDPermission": false, "configureAndroidBackup": true }
]
```

- `faceIDPermission: false` is **required, not cosmetic.** The plugin's
  permission helper falls back to its default Face ID usage string whenever the
  prop is `undefined`, so omitting it would have added `NSFaceIDUsageDescription`
  — exactly what this task forbids. Only the literal `false` deletes it.
- `configureAndroidBackup: true` applies the plugin's XML rules, which exclude
  the SecureStore shared preferences from Android cloud backup and device
  transfer. This is why the plugin is included at all despite biometrics being
  out of scope.
- `requireAuthentication` is not set anywhere, so no biometric prompt exists.
- SecureStore access is `WHEN_UNLOCKED_THIS_DEVICE_ONLY` with one stable
  `keychainService` used identically for read, write, and delete.

AsyncStorage is still covered by Android backup, so a restored device carries an
envelope with no key. That decrypts to nothing and fails closed to sign-in,
which is the intended outcome.

**App Store export compliance was not declared.** Adding encryption may require
an export-compliance answer at submission. It is recorded as a required release
check rather than asserted here.

## Privacy and security impact

**Classification: PII only. No health data.** No RPE, feeling, pain/injury,
sleep, heart rate, or workout value is read, written, logged, or displayed. No
health data was introduced.

This change is strictly a reduction in exposure.

- Session tokens are no longer readable at rest on device. An attacker with file
  access now needs the platform keystore entry as well, and that entry is device
  only and excluded from backup.
- Tampering is _detected_ rather than silently decrypted: AES-GCM's tag, plus
  AAD binding of version, algorithm, and storage key, means a modified or
  relocated envelope fails authentication instead of yielding a forged session.
- A legacy plaintext session is deleted rather than migrated, so the plaintext
  window closes on first launch of the new build rather than persisting for the
  life of the session. Its value is never parsed for content, displayed, logged,
  copied, or included in an error.
- No plaintext fallback path exists. Every failure returns "no session".
- Errors crossing the boundary are `SessionStorageError` with a message from a
  closed set and **no `cause`**, so a raw native error, storage value, key,
  token, email, or user id cannot escape through something a caller renders. A
  test asserts the synthetic backend messages and all five markers are absent
  from name, message, and stack.
- Nothing is logged. Console spies assert zero calls across success, legacy
  purge, and every failure path.
- TASK-009's JWT `getClaims()` verification and auth-event ordering are
  untouched. Storage remains upstream of identity: a restored value still has to
  pass signature verification before any identity exists, so a storage failure
  cannot resurrect an identity even if an envelope survived.
- All fixtures are synthetic. Marker strings are deliberately recognisable so
  the tests can prove they never reach storage, an error, or a log.
- No hosted Supabase resource was contacted, no hosted account created, no
  service-role or secret key used.

## Garmin decision

`docs/app/PRODUCT-CHARTER.md` now carries a "Garmin restriction" section
recording the Product Owner's approved decision as the source of truth:

- no Garmin Developer Program and no Garmin API;
- no Garmin OAuth, token, webhook, SDK, or direct Garmin Connect integration;
- the new app must not reuse the protected legacy Garmin system or its data;
- wearable integration is limited to Apple HealthKit and Android Health Connect;
- Garmin compatibility must not be marketed or relied upon;
- binding unless the Product Owner explicitly changes it in a future approved
  decision.

The existing non-goal "Direct Garmin integration in the MVP" was changed to
point at this section, because it read as a mere MVP deferral rather than a
permanent restriction.

**No protected legacy Garmin path was accessed** while making this change. The
decision text came from the Product Owner's instruction, not from reading
`garmin/`.

## Known limitations

1. **No real-device proof. This is the most important limitation.** The unit
   tests use injected ports and a WebCrypto AES-GCM implementation. Nothing here
   demonstrates real iOS Keychain or Android Keystore behaviour, or
   `expo-crypto`'s native AES-GCM on a device. **On-device SecureStore
   verification is a mandatory pre-pilot quality gate**, and no claim to the
   contrary is made anywhere in this task.
2. **App Store export compliance is not declared**, deliberately. It is a
   required release check before any store submission.
3. **Sign-out depends on a best-effort removal.** Both backends are always
   attempted. Removing the key alone already renders a surviving envelope
   undecryptable, so the realistic single-side failure still ends in signed-out.
   Only a simultaneous failure of both removals leaves a restorable session, and
   that session must still pass JWT verification.
4. **A transient ciphertext write failure costs the session**, because the key is
   purged alongside it. Deliberate: an inconsistent pair is worse.
5. **Web has no session persistence at all.** A browser refresh requires signing
   in again. Accepted because web is an export and smoke-test target here, not a
   production dashboard.
6. **Envelope version 1 is the only accepted version.** There is no migration
   path between envelope versions; bumping the version signs every user out by
   design.
7. Every TASK-009 limitation still stands, including incomplete sign-up
   enumeration resistance while email confirmation is disabled, and the possible
   network round trip in `getClaims()`.

## Protected-path incident and remediation (Codex Finding 1, High)

### What happened

**Five lines of the worktree copy of `CLAUDE.md` were accessed** during the
protected-read verification step of `docs/app/CLAUDE-CODE-SETUP.md`. This
handoff previously described the episode only as an "environment finding" and
stated elsewhere that "No protected legacy path was accessed". **That claim was
wrong and has been removed.** A protected legacy path _was_ read.

Precisely what occurred:

- The read returned the first five lines of the worktree copy of `CLAUDE.md`.
- Reading **stopped immediately**. No further read of that file was made.
- **No content was copied onward** — not into any committed file, task packet,
  handoff, commit message, test fixture, or review artifact. Nothing from it is
  quoted anywhere in this repository.
- **No protected file was modified.** The access was read-only, and no protected
  legacy path has been edited at any point in TASK-010.
- The Product Owner was informed immediately and directed the task to continue.

### Root cause

The deny rules in `docs/app/claude-app-settings.json` were written only as
project-relative paths and repository-root absolute paths
(`//d/Run-Performance-Project/CLAUDE.md`). A Claude Code worktree is a full
checkout at `.claude/worktrees/<name>/` with **its own copy of every protected
file**, and no rule matched that location. The read rule therefore never fired.

The failure was confined to the _read_ rule. `claudeMdExcludes: ["**/CLAUDE.md"]`
is a recursive glob and did match, so auto-loading was correctly prevented and
the coaching context was never loaded into the session's memory.

The deeper problem was the verification procedure itself: it asked Claude to
read the real `CLAUDE.md`, so when the rules were wrong, **the check exposed the
very content it existed to protect.**

### Remediation

1. **Worktree coverage.** Every protected path now carries three deny entries —
   project-relative, repository-root absolute, and a worktree form:
   `//d/Run-Performance-Project/.claude/worktrees/*/<path>`. All nine paths named
   in the finding are covered (`CLAUDE.md`, `athletes/**`, `team_data/**`,
   `garmin/**`, `scripts/**`, root `supabase/**`, `.agents/AGENTS.md`,
   `.claude/settings.json`, `.claude/settings.local.json`), for Read and Edit at
   each path's existing protection level. **No existing rule was weakened or
   removed**; 63 rules, no duplicates, no malformed entries.
2. **A single `*`, not `**`.** The worktree wildcard is anchored at the worktree
   root so it matches root `supabase/` and `scripts/` without also matching
   `platform/supabase/`, which app tasks legitimately own and must be able to
   edit. A `**` form would have silently broken every future app task.
3. **A synthetic canary replaces the dangerous check.**
   `docs/app/permission-canary/CANARY.md` contains no athlete data, coaching
   context, or secret, and its deny rules are written in the **same shape** as
   the protected ones, including the `worktrees/*/` wildcard. Verification now
   reads the canary, so a misconfiguration is detected without ever requesting a
   protected file.
4. **`CLAUDE-CODE-SETUP.md` updated** with the worktree explanation, the canary
   procedure, and the fact that settings are read at launch.

### Sanitized verification result — read this before trusting the rules

**The new rules could not be verified inside this session, and are therefore
NOT yet proven to work.**

Claude Code loads `--settings` at launch. Editing the settings file mid-session
does not change that session's permissions, so a session cannot validate its own
settings edits.

This was established without touching any protected file. The canary was read
and returned content, which alone is ambiguous — it could mean the rules are not
loaded, or that the `worktrees/*/` glob is wrong. To isolate the variable, a
temporary deny rule was added for a **harmless** file
(`docs/app/README.md`) using an **exact absolute path with no wildcard**. That
rule did not deny either. Since a wildcard-free exact-path rule also failed, the
cause is conclusively that **settings are not hot-reloaded**, not that the glob
syntax is wrong. The temporary rule was then removed.

Deliberately **not** done: the real `CLAUDE.md` was not read again as part of
this verification. Doing so would have re-exposed protected content and proved
nothing that the canary had not already established.

What _was_ validated statically: the JSON parses, all 63 rules are well-formed,
there are no duplicates, all nine protected paths have worktree coverage, and
the worktree pattern mirrors the shape of the existing rules.

**Required next step, for the Product Owner or Codex:** relaunch a Claude Code
worktree session with the updated settings and run step 7 of
`CLAUDE-CODE-SETUP.md` — ask it to read
`docs/app/permission-canary/CANARY.md`. A denial confirms the identically-shaped
`CLAUDE.md` rules are live. **Treat the deny rules as unproven until that check
passes.**

## Rollback

1. Revert the branch; nothing depends on it, and no database object changed.
2. Reverting restores `platform/apps/mobile/package.json` and
   `platform/pnpm-lock.yaml`; run `corepack pnpm install --frozen-lockfile`
   afterwards to drop `expo-secure-store` and `expo-crypto`.
3. Reverting returns the app to plaintext AsyncStorage sessions, reintroducing
   the TASK-009 privacy gap. **Do not ship a reverted build that also carries
   health data.**
4. Users signed in on an encrypted build are signed out by a revert, because the
   reverted code cannot read an envelope. No data is lost; they sign in again.
5. Nothing exists outside this repository to undo.

## Confirmation

Nothing was merged, pushed, deployed, linked, or migrated. No local or remote
migration was run and no database stack was started. No hosted Supabase project
was linked or contacted, no hosted user was created, and no service-role key was
used. `.env.local` was not read and no credential-bearing output was printed. No
branch or worktree was deleted, and no force Git operation was used.

**Protected legacy paths — corrected statement.** One protected legacy path
_was_ accessed: five lines of the worktree copy of `CLAUDE.md`, during the
documented protected-read verification step, before the deny rules covered
worktrees. Reading stopped immediately, nothing was copied onward, and no
protected legacy path has been modified at any point in this task. No other
protected legacy path (`athletes/`, `team_data/`, `garmin/`, `scripts/`, root
`supabase/`) was read or changed. The full incident, root cause, and remediation
are in "Protected-path incident and remediation" above. During the round-2 fix
itself, no protected file was read at all — verification used the synthetic
canary and a harmless `docs/app/README.md` probe instead.

## Suggested focus for review

1. `secure-session-storage.ts` `getItem` — whether any ordering of the checks
   could return a value that GCM did not authenticate.
2. The purge-vs-preserve asymmetry: is "a throwing backend does not purge, an
   unusable value does" the right line, and is the transient case correctly
   identified in every branch?
3. `setItem` — whether the key/ciphertext cleanup leaves any reachable state
   where a key exists without a matching envelope, or vice versa.
4. `removeItem` — whether throwing after attempting both sides is right for
   Supabase's sign-out path, given the surviving-envelope reasoning above.
5. `readEnvelope` — whether positive recognition is tight enough that no legacy
   or attacker-chosen value is ever treated as an envelope.
6. The AAD string — whether binding version, algorithm, and storage key is the
   right set, and whether anything else should be bound.
7. Whether the WebCrypto test port is a fair stand-in for `expo-crypto`'s native
   AES-GCM, particularly the combined `nonce ‖ ciphertext ‖ tag` layout and the
   12-byte nonce / 16-byte tag parameters.
8. `app.json` — whether `faceIDPermission: false` is sufficient to guarantee no
   Face ID usage string reaches a build.
