# Supabase Environment Contract

Status: **Configured for future integration; not connected**

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

## Backend boundary

Future trusted server components may use a separately rotated secret key only
through their hosting provider's secret store. Mobile code must never receive it.
The first backend task will add migrations and authorization-negative tests
before any protected data is introduced.

No CLI link, schema change, database query, or remote migration was performed by
this configuration task.
