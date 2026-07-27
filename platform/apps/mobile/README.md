# Run Performance Mobile

Expo SDK 56 development shell for the athlete-and-coach mobile app.

## Current routes

Every route below is gated by `Stack.Protected` in `src/app/_layout.tsx`, and
every guard is derived from `resolveAuthGate` in `src/features/auth/gate.ts`.

- `/` — decides where the user belongs and redirects; renders nothing itself
- `/loading` — neutral restore/load state, and the recoverable retry state
- `/sign-in`, `/sign-up` — email and password only
- `/check-email` — generic state after a sign-up that returned no session
- `/onboarding` — required display name, before any role area
- `/pending` — signed in and onboarded, but holding no active membership
- `/choose-role` — only for a user with two active roles
- `/profile` — display-name editing and global sign-out
- `/athlete`, `/coach` — role shells, still empty-state placeholders

These screens intentionally use no real athlete, health, team, or wearable data.

## Authorization boundary

The route guards are **UX protection only**. PostgreSQL grants and Row Level
Security are the authorization boundary. A guard exists so a user is not shown a
screen that would fail, not so a query can be trusted.

Roles come from `public.team_memberships` rows returned under RLS, and from
nowhere else. A role is never read from auth metadata, a JWT claim, the email
address, on-device storage, or the role chooser. That is what makes a revocation
take effect on the next successful query rather than at the next sign-in.

## Run

From `platform/`:

```powershell
corepack pnpm install
corepack pnpm --filter @run-performance/mobile start
```

Then press `w` for web or `a` for an Android emulator. Native iOS simulation
requires macOS and Xcode.

## Quality checks

```powershell
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

The unit tests are pure-logic only. They import no React Native module, render
no component, and make no network request, so they run under plain `vitest` with
no extra configuration. Data-access modules take the Supabase client as an
argument specifically so they can be tested with a small hand-written double.

## Generated database types

`src/lib/supabase/database.types.ts` is generated. Do not hand-edit it.

Regenerate it from the **local** stack only, after a migration changes the
schema. Run from `platform/` with the local stack up:

```powershell
corepack pnpm exec supabase gen types typescript --local --schema public `
  | Out-File -FilePath "apps\mobile\src\lib\supabase\database.types.ts" -Encoding utf8
```

`Out-File -Encoding utf8` writes a BOM on Windows PowerShell 5.1; strip it before
committing, or Prettier will disagree with the checked-in file.

Never generate types with `--linked`, a project ref, or a remote database URL.
Doing so contacts the hosted project and can leak schema details of an
environment this workspace is not authorized to read.

## State architecture

Server state uses TanStack Query. Two rules are not negotiable:

- **Every auth-bound query key includes the authenticated user id**
  (`src/lib/query/keys.ts`). Without it, a cache entry written for one account
  could be read by the next account signed in on the same device.
- **The query cache is never persisted to disk.** No persister is installed. On
  sign-out or a change of user, `clearAuthScopedQueries` _removes_ the entries
  rather than invalidating them, so no stale value from the previous account is
  readable while a refetch is in flight.

Data-backed screens must distinguish:

- initial loading;
- refresh in progress;
- empty or missing data;
- stale data;
- permission not granted;
- recoverable error;
- access denied.

The most important of these is the last pair. A failed load and "this user has
no active team" both produce zero usable rows and mean opposite things, so the
repository raises on failure instead of returning an empty list, and the gate
checks for an error before it checks the membership count.

## Supabase environment

For local work, copy `.env.example` to `.env.local` and enter only the current
publishable key.

Never put a secret or legacy service-role key in this mobile project. Every
`EXPO_PUBLIC_` value is bundled into the application and is readable by end
users. See `docs/app/SUPABASE-ENVIRONMENT.md` for the complete boundary.

## Session storage

Native session persistence is **encrypted**. TASK-010 replaced the plaintext
AsyncStorage adapter that TASK-009 shipped.

| Where            | What is stored                                                |
| ---------------- | ------------------------------------------------------------- |
| Expo SecureStore | the AES-256 key, and nothing else                             |
| AsyncStorage     | a versioned AES-256-GCM ciphertext envelope, and nothing else |

The session JSON, the access and refresh tokens, the email, the user id, and the
claims are never written to either backend in readable form.

- `secure-session-storage.ts` — the `SupportedStorage` adapter. Platform-free:
  the keystore, the ciphertext store, and the AES-GCM primitive are injected as
  ports, which is what lets the whole failure matrix be tested in plain Node.
- `native-session-storage.ts` — the thin binding onto Expo SecureStore, Expo
  Crypto, and AsyncStorage.
- `auth-options.ts` — the web/native persistence decision.

Expo SDK 56's `expo-crypto` provides authenticated AES-GCM natively, so no
third-party AES library is used. **Never substitute an unauthenticated mode such
as AES-CTR**: tamper detection is the point, not merely confidentiality.

### Fail closed, never fall back

A missing key, a missing ciphertext, a legacy plaintext value, a malformed
envelope, an unknown version, a failed authentication tag, and a backend that
throws all resolve to "no session", which the gate reads as signed-out. There is
no code path that returns a session GCM did not authenticate.

A leftover TASK-009 plaintext session is **deleted, never migrated**, and the
user signs in again. Its value is never parsed for content, displayed, logged,
or included in an error.

Errors leaving the adapter are `SessionStorageError` with a message from a
closed set and no `cause`, so a raw native error, a storage value, a key, a
token, an email, or a user id cannot escape through something a caller renders.

### Web

Web sets `persistSession: false` and supplies no storage at all, so a refresh
requires signing in again. Web is an export and smoke-test target here, not a
production dashboard.

### Device configuration

The SecureStore key uses `WHEN_UNLOCKED_THIS_DEVICE_ONLY` and one stable
`keychainService` across read, write, and delete. `requireAuthentication` is
deliberately **off** — biometric prompts are out of scope — and the config
plugin is set with `faceIDPermission: false` so no Face ID usage string is
added.

`configureAndroidBackup` keeps the SecureStore entry out of Android cloud backup
and device transfer. AsyncStorage is still backed up, so a restored device
carries an envelope with no key; that decrypts to nothing and fails closed to
sign-in, which is the intended outcome.

> **Not yet proven on a real device.** The unit tests use injected ports. No
> claim is made about real iOS Keychain or Android Keystore behaviour.
> On-device SecureStore verification is a mandatory pre-pilot quality gate.

> App Store export-compliance for encryption has **not** been declared. Treat it
> as a required release check before any store submission.
