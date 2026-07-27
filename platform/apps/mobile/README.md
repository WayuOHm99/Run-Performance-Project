# Run Performance Mobile

Expo SDK 56 development shell for the athlete-and-coach mobile app.

## Current routes

- `/` — development-only role preview
- `/athlete` — Athlete Today empty-state shell
- `/coach` — Coach Team empty-state shell

These screens intentionally use no real athlete, health, team, or wearable data.
Authentication will replace the role preview later.

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

## State architecture

This foundation renders explicit empty states. Future data-backed screens must
also distinguish:

- initial loading;
- refresh in progress;
- empty or missing data;
- stale data;
- permission not granted;
- recoverable error;
- access denied.

No state library is installed yet. Local React state is sufficient until a real
flow requires shared client state; TanStack Query will be evaluated when the
backend integration begins.

## Supabase environment

The hosted project identity is documented, but this app does not initialize a
Supabase client from the preview screens yet. The lazy client foundation lives
under `src/lib/supabase/` and will first be invoked by the authentication flow.
For local work, copy `.env.example` to `.env.local` and enter only the current
publishable key.

Never put a secret or legacy service-role key in this mobile project. Every
`EXPO_PUBLIC_` value is bundled into the application and is readable by end
users. See `docs/app/SUPABASE-ENVIRONMENT.md` for the complete boundary.

The client uses AsyncStorage for native session persistence, browser storage on
web, and foreground-only native token refresh. Creating the client does not query
the database; network activity begins only when a later feature calls an Auth or
data method.
