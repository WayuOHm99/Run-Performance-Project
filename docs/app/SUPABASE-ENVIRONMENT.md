# Supabase Environment Contract

Status: **Configured for future integration; not connected**

The app talks to exactly one of **two** endpoints, and which one is an explicitly
declared decision rather than whatever happens to be in the environment:

| Mode | `EXPO_PUBLIC_SUPABASE_ENVIRONMENT` | URL |
| --- | --- | --- |
| Hosted (default) | absent, empty, or `hosted` | `https://altlphxckxsudnuwhqfw.supabase.co` |
| Local demo | `local` | `http://127.0.0.1:54321` |

Any other value of the mode variable is an **error**, not a fallback to hosted. A
typo must stop the app rather than quietly aim it at production. See
`docs/app/LOCAL-DEMO.md` for the local demo workflow.

## Hosted project

| Field | Value |
| --- | --- |
| Project name | `Run-performance-Project` |
| Project reference | `altlphxckxsudnuwhqfw` |
| API URL | `https://altlphxckxsudnuwhqfw.supabase.co` |

The project name, reference, and URL are public identifiers. No API key is stored
in this document.

## Mobile variables

The Expo app may read only:

```dotenv
EXPO_PUBLIC_SUPABASE_URL=https://altlphxckxsudnuwhqfw.supabase.co
EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY=replace-with-current-publishable-key
```

Expo inlines every `EXPO_PUBLIC_` value into the client bundle. These variables
must therefore be treated as public. The publishable key is appropriate here
because database access will be enforced by authentication and Row Level
Security.

Never place any of the following in the mobile app, its environment files, EAS
client variables, logs, tests, or source:

- a Supabase secret key;
- a legacy service-role key;
- a database password;
- a personal access token;
- a private signing key.

## Local setup

Immediately before the Supabase client task:

1. Copy `platform/apps/mobile/.env.example` to
   `platform/apps/mobile/.env.local`.
2. Replace only the publishable-key placeholder using the current value from
   Supabase Dashboard → Project Settings → API Keys.
3. Do not paste the value into an AI chat, task packet, terminal command, or Git
   commit.
4. Confirm the file is ignored with:

   ```powershell
   git check-ignore platform/apps/mobile/.env.local
   ```

## Local demo mode (TASK-017)

The local demo endpoint is gated behind its own mode variable rather than added
to the accepted URL set, so a machine that forgets to declare local mode cannot
silently point a demo build at the hosted project, and a hosted build cannot be
talked into a local one.

Validation is **exact equality against an allowlist**, in the app and in the demo
tooling independently. Neither trusts the other. Rejected before any client is
created:

- the hosted project URL, and any other `*.supabase.co` host;
- arbitrary LAN hosts such as `192.168.x.x`;
- `localhost` and the IPv6 loopback — only `127.0.0.1` is canonical, so the value
  cannot resolve through a hosts-file entry;
- any port other than `54321`;
- userinfo (`http://user:password@...`), a path, a query, a fragment, a trailing
  slash, and surrounding whitespace.

`http://10.0.2.2:54321` is the Android emulator's alias for the host loopback. It
is accepted **only when the app is actually running on Android**, so a web or iOS
build handed that URL refuses to start.

The credential rules are identical in both modes and are not relaxed locally: the
local stack has a service-role key too, and it is exactly as dangerous inside a
client bundle as a hosted one. Only `sb_publishable_` is accepted; `sb_secret_`,
legacy JWTs, database URLs, passwords, and malformed keys are refused. No error
message ever echoes the rejected value.

The demo commands pass all of this as **process-scoped** environment variables
and set `EXPO_NO_DOTENV=1`. They never read, modify, overwrite, back up, or
delete `platform/apps/mobile/.env.local`.

## Backend boundary

Future trusted server components may use a separately rotated secret key only
through their hosting provider's secret store. Mobile code must never receive it.
The first backend task will add migrations and authorization-negative tests
before any protected data is introduced.

No CLI link, schema change, database query, or remote migration was performed by
this configuration task.
