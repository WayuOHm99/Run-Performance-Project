# Local App Demo

Status: **Active** (TASK-017)

Run the whole athlete-and-coach product on your own machine, against a **local**
Supabase stack only, with two synthetic accounts.

Nothing here contacts the hosted Supabase project. There is no link, no remote
migration, no `db push`, and no deployment.

## Prerequisites

- Docker Desktop with the WSL 2 backend, running.
- Node.js 22–24 with Corepack enabled.
- Dependencies installed: `corepack pnpm install --frozen-lockfile` from
  `platform/`.

Confirm Docker is up and using a Linux engine:

```powershell
docker version --format '{{.Server.Os}}'
```

The value must be `linux`.

## The commands

Run all of them from `platform/`.

| Command | What it does | Destructive? |
| --- | --- | --- |
| `corepack pnpm demo:reset` | Rebuilds the demo baseline from scratch | **Yes — to the local Supabase project only** |
| `corepack pnpm demo:start` | Brings the stopped stack back up, with its credential block suppressed | No — existing data is kept |
| `corepack pnpm demo:web` | Launches the Web surface | No |
| `corepack pnpm demo:android` | Launches the Android Emulator surface | No |
| `corepack pnpm demo:stop` | Stops this project's containers | No — local data is kept |

Two helpers exist for verification:

| Command | What it does |
| --- | --- |
| `corepack pnpm demo:verify` | Re-reads the baseline counts. Read-only; changes nothing. |
| `corepack pnpm demo:verify:consent` | Proves the consent boundary end to end. **Destructive**, and restores the baseline itself. |

**Launching never resets.** `demo:web` and `demo:android` run no reset, apply no
fixture, and create no user. Rebuilding the data is always an explicit
`demo:reset`.

**`demo:start` is the supported way to bring a stopped stack back.** The five
commands above are the whole interface: everything the demo needs is one of them,
and none of them prints the stack's credential block. You never need to run the
Supabase CLI by hand for a demo, and this guide never asks you to.

### Only one destructive command at a time

`demo:reset`, `demo:start`, `demo:stop`, and `demo:verify:consent` take an
exclusive lock file, `platform/.local-demo/demo.lock`, before they touch the
stack. A second one **refuses to run** rather than queueing:

```text
Another destructive demo command is already running (demo:reset, pid 12345).
```

That is not fussiness. Two resets interleaved produce a database built by one run
and a credential file written by the other, so the password you are given no
longer opens the accounts that exist. A reset landing in the middle of
`demo:verify:consent` leaves a sharing grant behind, which is exactly the
zero-consent baseline the demo promises.

**A running command's lock is never taken away from it**, however long it has
been running. A cold start on a slow machine can take many minutes, and being
slow is not evidence of being dead. A lock is recovered only when the process
that wrote it is genuinely gone, which the next run detects and handles by
itself — you do not need to delete anything.

Very rarely you may see *"Another process is recovering an abandoned local demo
lock"*. That means a run was killed during the fraction of a second it spends
recovering. Try again; if it never clears, delete
`platform/.local-demo/demo.lock.break` and try again.

## First run

```powershell
cd platform
corepack pnpm demo:reset
corepack pnpm demo:web
```

`demo:reset` prints the baseline counts and the **path** to your local
credentials. It does not print the password.

```text
Local demo credentials written to: platform/.local-demo/credentials.txt
```

Open that file to get the shared password for both accounts. It is git-ignored,
regenerated on every reset, and must never be committed, screenshotted, or pasted
into an AI chat.

**If the file is missing, the reset did not finish.** It is deleted before the
database is wiped and written again only after the baseline has been verified, so
it either describes the accounts that exist or it does not exist at all. It is
never left holding a password that no longer works. Run `demo:reset` again.

## The baseline

Every `demo:reset` produces exactly this, and verifies it before writing the
credential file:

| Thing | Count |
| --- | --- |
| Auth users (`example.test`) | 2 |
| Profiles, both with a display name | 2 |
| Teams | 1 |
| Active memberships | 2 (1 athlete, 1 coach) |
| **Sharing grants** | **0** |
| **Daily check-ins** | **0** |

The two accounts are `athlete-a@example.test` and `coach-a@example.test`.
`example.test` is reserved by RFC 6761 and can never receive mail, so a stray
local email cannot reach a real inbox.

**Consent is never seeded and health data is never seeded.** That is the point:
the demo starts with the coach unable to see anything, and you create the consent
yourself through the real UI.

Roles come from `public.team_memberships` and from nowhere else — never from Auth
metadata, and never from a JWT claim. That is why revoking takes effect on the
next query rather than at the next sign-in.

## The story to walk

1. `demo:reset`, then `demo:web`.
2. Sign in as `athlete-a@example.test`. You land in the **athlete** area.
3. Submit a check-in. Use any synthetic values you like.
4. Sign out, sign in as `coach-a@example.test`. You land in the **coach** area.
   **The check-in is not visible.** Membership alone is not consent.
5. Sign back in as the athlete and grant check-in sharing to the team.
6. As the coach, refresh. The latest check-in now appears.
7. As the athlete, revoke sharing.
8. As the coach, refresh again. Access is gone. As the athlete, your own check-in
   is still there.

Steps 4, 6, and 8 are the whole product thesis. `demo:verify:consent` asserts the
same sequence mechanically against the database, in case you want the evidence
without the clicking.

## Android Emulator

```powershell
corepack pnpm demo:reset   # if you have not already
corepack pnpm demo:android
```

The emulator cannot reach `127.0.0.1` on your host — inside the emulator that
address is the emulator itself. The demo command therefore hands the app
`http://10.0.2.2:54321`, which is the emulator's alias for the host loopback. It
is the same local stack, and it never leaves your machine.

The app accepts that alias **only when it is actually running on Android**. A web
build handed the same URL refuses to start.

## What is deliberately out of scope

- **Physical devices and LAN access.** The demo binds to loopback. Pointing a
  real phone at your machine's LAN address would need a different endpoint, and
  that is not in scope.
- **iOS.** Requires macOS and Xcode.
- **Tunnels and any external exposure.**
- **The hosted project.** Not contacted, in any command, at any point.

## Your `.env.local` is not touched

The demo commands set process-scoped environment variables for the child process
only, and set `EXPO_NO_DOTENV=1` so Expo reads no dotenv file at all.

`platform/apps/mobile/.env.local` is never read, modified, overwritten, backed
up, or deleted. Your hosted-project configuration survives a demo session
untouched, and a demo session cannot accidentally pick it up either.

## Credential handling

The local stack prints a database URL, a JWT secret, and a service-role key when
it starts. **The demo tooling never shows you any of that.** `supabase start` and
`supabase stop` are run with all three streams discarded at the OS level, and the
only field the tooling reads out of `supabase status` is the local
`sb_publishable_` key — the same class of credential the mobile app is allowed to
hold.

Every command that could print that block — `demo:start`, `demo:reset`,
`demo:stop`, and the stack start inside them — runs it with all three streams
discarded at the OS level.

**No message in this tooling will ever tell you to run the underlying Supabase
CLI to work out what went wrong.** That was true of an earlier version of this
guide and it was a mistake: a failure is the moment you are most likely to paste
a terminal into a chat or a screenshot, and the raw output at that moment is the
most credential-bearing thing on your screen. Every recovery route below is a
demo command whose output is safe.

## Stopping

```powershell
corepack pnpm demo:stop
```

Stops **only this project's** containers. It never uses `--all`, which would stop
unrelated Supabase projects, and never `--no-backup`, which would discard your
local database volume. Your demo data survives; bring it back with
`corepack pnpm demo:start`.

To confirm nothing is left running:

```powershell
docker ps -a --filter name=supabase --format "{{.Names}}"
```

## Troubleshooting

**"The local Supabase stack is not running."** `demo:web` and `demo:android`
deliberately refuse to start it, so that launching can never become a hidden
rebuild. Run `corepack pnpm demo:start` to bring it back with your data, or
`corepack pnpm demo:reset` to rebuild the baseline.

**A command failed and printed only an exit code.** That is intentional: the
underlying output can carry a database URL, a JWT secret, and a service-role key,
so it is discarded at the OS level rather than shown. Recover, in this order:

1. `corepack pnpm demo:reset` — rebuilds the baseline from scratch and is the
   right answer to almost every failure here;
2. if that fails too, confirm Docker is up and healthy with
   `docker version --format '{{.Server.Os}}'` and
   `docker ps -a --filter name=supabase --format "{{.Names}}"`, which print
   container state and no Supabase credential;
3. if it still fails, hand the **exit code and the command name** to whoever
   maintains the tooling. Do not go looking for the suppressed output to paste —
   that is the one thing this design exists to keep off your screen.

**"… was terminated by SIGTERM and did not complete."** Something killed the
Supabase CLI part-way — a Ctrl-C, a Docker restart, an out-of-memory kill. The
command reports it as a failure rather than carrying on, because a `db reset`
that was killed half-way leaves a half-migrated database. Run `demo:reset` again;
the credential file was already discarded, so there is nothing stale to clean up.

**"Another destructive demo command is already running."** Exactly what it says;
see *Only one destructive command at a time* above.

**The coach sees nothing after granting.** Refresh. Access is decided on each
query by PostgreSQL, and an already-rendered screen is not recalled.

**The baseline check fails after you have been clicking around.** Expected — you
have added a check-in or a grant. Run `demo:reset`.
