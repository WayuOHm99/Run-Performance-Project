# TASK-010: Secure Session Storage Hardening

Status: Implemented, awaiting Codex read-only review

Writer: Claude Code (sole writer)

Reviewer: ChatGPT/Codex (read-only)

No AGY reviewer is assigned to this task.

## Goal and user value

Replace plaintext native Supabase session persistence with a size-safe encrypted
storage adapter **before any health data is introduced**.

TASK-009 shipped the Supabase session as plaintext JSON in AsyncStorage, which
is not encrypted at rest on device. Its own handoff named this "the single most
important follow-up" and made SecureStore hardening mandatory before pilot
release or before health data is added. This task closes it.

The user value is indirect but real: an athlete's access and refresh tokens, and
therefore their whole account, stop being readable from device storage by
anything that can read the app's files.

## In scope

- An AES-256-GCM `SupportedStorage` adapter for Supabase Auth on native.
- Expo SecureStore holding the AES key only.
- AsyncStorage holding a versioned authenticated ciphertext envelope only.
- Deletion, never migration, of TASK-009 plaintext sessions.
- A fail-closed result path for every storage, envelope, and crypto failure.
- `persistSession: false` on web, with no persistent browser Auth storage.
- Expo SDK 56 `expo-secure-store` and `expo-crypto`, pinned.
- The SecureStore config plugin, configured for Android backup exclusion and
  **without** Face ID permission text.
- Unit tests using injected storage and crypto ports.
- The approved Garmin restriction in `docs/app/PRODUCT-CHARTER.md`.
- A sanitized handoff at `docs/app/handoffs/TASK-010.md`.

## Out of scope

- Biometric or `requireAuthentication` prompts.
- Any database, migration, or pgTAP change. This task owns no database change.
- Changing TASK-009 authentication behaviour, JWT verification, or auth-event
  ordering.
- Health, workout, sleep, check-in, or training-plan code.
- A real-device or store build, an App Store export-compliance declaration.
- Hosted Supabase linking, remote migration, deployment, merge, or push.

## Owned paths

- `docs/app/tasks/TASK-010-secure-session-storage.md`
- `docs/app/PRODUCT-CHARTER.md` (only the approved Garmin clarification)
- `docs/app/handoffs/TASK-010.md`
- `platform/apps/mobile/package.json`
- `platform/pnpm-lock.yaml`
- `platform/apps/mobile/app.json`
- `platform/apps/mobile/README.md`
- `platform/apps/mobile/src/lib/supabase/`
- narrowly required TASK-009 auth integration and tests, only where necessary to
  enforce fail-closed storage behaviour

Expanded by Product Owner authorization during round 2, to resolve Codex
Finding 1:

- `docs/app/claude-app-settings.json`
- `docs/app/CLAUDE-CODE-SETUP.md`
- verification helpers under `docs/app/` only
  (`docs/app/permission-canary/CANARY.md`)

## Forbidden paths

- `platform/supabase/` — migrations and database tests
- `platform/apps/mobile/src/lib/supabase/database.types.ts` (generated)
- unrelated mobile features
- `platform/package.json` and root dependency files
- health, workout, sleep, check-in, and training-plan code
- `athletes/`, `team_data/`, `garmin/`, `scripts/`, root `supabase/`,
  `CLAUDE.md`, `.agents/AGENTS.md`, `.claude/settings*.json`

## Approved security decisions

1. Encrypt the **complete** Supabase session value with AES-256-GCM.
2. Use the Expo SDK 56 `expo-crypto` AES APIs. No third-party AES library.
3. Store only the AES key in Expo SecureStore.
4. Store only a versioned authenticated ciphertext envelope in AsyncStorage.
5. Never store the plaintext session, tokens, email, user id, or claims in
   readable form in either backend.
6. Fresh nonce per seal; secure key material.
7. Bind envelope version, algorithm, and storage key as additional authenticated
   data.
8. One stable SecureStore service across read, write, and delete, with
   `WHEN_UNLOCKED_THIS_DEVICE_ONLY` and no `requireAuthentication`.
9. Web uses `persistSession: false` with no persistent Auth storage.
10. Legacy plaintext is deleted, never migrated, never parsed or reported.

## Architecture

Three files, split so the security logic is testable without a device.

| File | Role |
| --- | --- |
| `secure-session-storage.ts` | the adapter: ports, envelope, failure matrix. No platform import. |
| `native-session-storage.ts` | thin binding onto SecureStore, Expo Crypto, AsyncStorage. |
| `auth-options.ts` | the pure web/native persistence decision. |

The keystore, ciphertext store, and AES-GCM primitive are injected as ports.
Tests supply a **WebCrypto**-backed AES-256-GCM port — a real authenticated
implementation present in the Node runtime, not a stand-in cipher — so tamper
detection, nonce freshness, and AAD binding are genuinely exercised. The
cryptographic logic is therefore not duplicated between implementation and
tests: both sides are thin adapters over a real primitive, and the envelope and
failure logic exists exactly once.

### Envelope

```json
{ "v": 1, "alg": "AES-256-GCM", "d": "<base64 nonce ‖ ciphertext ‖ tag>" }
```

Recognition is **positive**: a value is an envelope only if it carries our
version, our algorithm, and a non-empty payload. A TASK-009 plaintext session
parses as JSON perfectly well, so anything less than a positive match is
purged unread.

AAD is `runperf.session|v1|AES-256-GCM|<storage key>`, so an envelope cannot be
replayed under a different storage key or relabelled as another version without
failing the tag.

### Failure behaviour

| Situation | Result |
| --- | --- |
| legacy plaintext, malformed envelope, unknown version | purge both sides, return `null` |
| missing ciphertext (orphaned key) | purge both sides, return `null` |
| missing key, wrong key | purge both sides, return `null` |
| failed tag, corrupted ciphertext, decrypt error | purge both sides, return `null` |
| backend read threw | return `null`, **do not** purge |
| any write failure | purge both sides, throw `SessionStorageError` |
| removal, one side failing | attempt both, then throw |

A backend that merely throws is treated as transient, so an unavailable
keystore does not cost the user data it was simply unable to read. Everything
that is provably unusable is destroyed.

## Acceptance criteria

- [x] Native Supabase Auth never writes a plaintext session to AsyncStorage.
- [x] SecureStore contains only encryption key material, never session JSON or
      tokens.
- [x] AsyncStorage contains only a recognizable versioned AES-GCM ciphertext
      envelope.
- [x] Stored ciphertext contains no readable access token, refresh token, email,
      user id, or claims.
- [x] A synthetic session larger than 4 KB round-trips successfully.
- [x] Writing identical plaintext twice produces different ciphertext.
- [x] Tampering with the ciphertext or authentication tag fails closed.
- [x] Missing key/ciphertext, malformed envelope, unknown version, or decrypt
      failure returns no session.
- [x] Legacy plaintext is deleted and results in signed-out.
- [x] Storage read/write/remove failures do not open protected routing or reuse
      an old identity. **Extended in round 2:** an initiated sign-out closes the
      local identity, protected routing, and the auth-scoped cache before any
      I/O, so a removal failure that stops Supabase emitting `SIGNED_OUT` cannot
      leave the previous user's routes open.
- [x] Partial writes are cleaned up; plaintext fallback is impossible.
- [x] Removal attempts both storage backends even if one operation fails.
- [x] No token, key, ciphertext, storage value, raw native error, email, or user
      id is logged or displayed.
- [x] Native client uses the encrypted adapter.
- [x] Web uses `persistSession: false` and no persistent Auth storage.
- [x] TASK-009 JWT verification, stale-event ordering, sign-in, sign-up, and
      sign-out tests remain passing.
- [x] Expo config and dependency versions are compatible with SDK 56.
- [x] Product Charter records the permanent Garmin restriction.
- [x] No health data, secret, real user, or athlete data is introduced.
- [x] No hosted Supabase project is linked or contacted.

## Required negative tests

All present in `secure-session-storage.test.ts` unless noted.

- legacy plaintext value
- modified ciphertext
- modified authentication tag
- modified nonce
- envelope replayed under another storage key
- missing SecureStore key
- orphaned key (key with no ciphertext)
- missing ciphertext
- wrong key
- malformed envelope (7 shapes)
- unsupported envelope version
- SecureStore read rejection
- AsyncStorage read rejection
- transient read failure does not destroy data
- encryption failure
- SecureStore key-write failure
- ciphertext-write failure after key write
- one-side removal failure, both sides confirmed attempted
- surviving envelope unreadable after a partial removal
- duplicate plaintext writes produce different envelopes
- payload above 4 KB
- synthetic email/user-id/token/claim markers unreadable in stored ciphertext
- no logging during any operation, including failures
- sanitized errors carrying no `cause` and no marker
- web configuration cannot persist a session (`auth-options.test.ts`)
- storage failure cannot authorize athlete or coach routing

Added in round 2 for Codex Finding 2, in `sign-out.test.ts` and
`auth-state.test.ts`. These drive the real reducer and the real gate rather than
asserting on ports:

- a successful sign-out closes the identity and clears the cache
- a sign-out that throws, with no `SIGNED_OUT` emitted, still closes athlete and
  coach routing
- a partial storage removal does not reuse the old identity
- the cache is cleared before the remote call is awaited, not after
- a delayed stale validation for the previous user cannot reopen a route
- a delayed stale auth event observed before the sign-out cannot reopen a route
- an exposure trace proving user A never reappears after sign-out
- a genuine later sign-in still works, so sign-out fails closed without latching
- repeated sign-outs are idempotent
- the reported error carries no token, key, email, user id, or native error text
- nothing is logged on either the success or the failure path
- reducer-level: settles immediately, advances `appliedToken`, is ignored when a
  newer signal was already observed, and leaves both role areas closed

## Privacy classification

**PII only. No health data.** No RPE, feeling, pain/injury, sleep, heart rate,
or workout value is read, written, logged, or displayed.

This task strictly reduces exposure: the data that previously sat in plaintext
on device is now encrypted at rest with a key held in the platform keystore. All
fixtures are synthetic; the marker strings are deliberately recognisable so
tests can prove they never reach storage, an error, or a log.

## Verification

Run from `platform/`:

```powershell
corepack pnpm install --frozen-lockfile
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

```powershell
Push-Location apps/mobile
corepack pnpm dlx expo-doctor@latest

$env:EXPO_NO_DOTENV = "1"
$env:EXPO_PUBLIC_SUPABASE_URL = "https://altlphxckxsudnuwhqfw.supabase.co"
$env:EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_synthetic_local_verification_key"
corepack pnpm exec expo export --platform web
Pop-Location
```

```powershell
git diff --check
git status --short
```

No database stack or pgTAP rerun is required: TASK-010 owns no database change.
If any database file changes unexpectedly, stop.

## Known limitations

- **No real-device proof.** Unit tests use injected ports and a WebCrypto
  AES-GCM implementation. Nothing here demonstrates real iOS Keychain or Android
  Keystore behaviour, or `expo-crypto`'s native AES-GCM on a device. **On-device
  SecureStore verification is a mandatory pre-pilot quality gate.**
- **App Store export compliance is not declared.** Adding encryption may require
  an export-compliance answer at submission. This is recorded as a required
  release check, deliberately not asserted here.
- **Sign-out depends on a best-effort removal.** Both backends are always
  attempted. Removing the key alone already renders a surviving envelope
  undecryptable, so the realistic single-side failure still ends in signed-out.
  Only a simultaneous failure of both removals leaves a restorable session, and
  that session must still pass TASK-009 JWT verification. Since round 2, local
  access is closed regardless: the identity, protected routing, and auth-scoped
  cache are dropped before any removal is attempted, so a failure here can leave
  bytes on disk but cannot keep a route open.
- **A failed global sign-out is reported but not retried.** The user is signed
  out locally and sees a sanitized error; other devices may still hold a valid
  session until their own tokens expire. There is no retry queue in this task.
- **The deny-rule fix is unverified in-session.** Claude Code reads its settings
  at launch, so the worktree rules added in round 2 could not be exercised from
  the session that wrote them. They are statically validated only. Confirm with
  the canary check in `CLAUDE-CODE-SETUP.md` from a fresh session before relying
  on them.
- **A write failure signs the user out.** When the ciphertext write fails, the
  key is purged too, which makes any previous envelope unreadable. This is
  deliberate — an inconsistent key/ciphertext pair is worse — but it means a
  transient AsyncStorage write failure costs the session.
- **Web has no session persistence at all.** A browser refresh requires signing
  in again. Accepted because web is an export and smoke-test target here.
- **Envelope version 1 is the only accepted version.** There is no migration
  path between envelope versions; bumping the version signs every user out by
  design.
- Every TASK-009 limitation still stands, including incomplete sign-up
  enumeration resistance while email confirmation is disabled, and the possible
  network round trip in `getClaims()`.

## Rollback

- Revert the branch; nothing depends on it, and no database object changed.
- Reverting restores `platform/apps/mobile/package.json` and
  `platform/pnpm-lock.yaml`; run `corepack pnpm install --frozen-lockfile`
  afterwards to drop `expo-secure-store` and `expo-crypto`.
- Reverting returns the app to plaintext AsyncStorage sessions, which
  reintroduces the TASK-009 privacy gap. **Do not ship a reverted build that
  also carries health data.**
- Users signed in on a build with the encrypted adapter will be signed out by a
  revert, because the reverted code cannot read an envelope. No data is lost.
- Nothing exists outside this repository to undo: no remote migration, no
  deployment, no hosted account, no push.

## Required handoff

A sanitized copy at `docs/app/handoffs/TASK-010.md`, recording branch and base
SHA, the clean implementation commit, changed files, acceptance-criteria
evidence, commands and results, privacy/security impact, the Garmin decision,
known limitations, rollback, and confirmation that nothing was pushed, deployed,
linked, migrated, or accessed remotely.
