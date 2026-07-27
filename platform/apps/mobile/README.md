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
