# Product Charter — Run Performance Mobile App

Status: **Approved baseline**

Date: 2026-07-27

Product Owner: Coach / repository owner

## Product outcome

Build one simple mobile app with two role-based experiences. The athlete experience
is primary; the coach experience exists to assign training and notice who may need
attention.

The MVP is useful without a connected watch. Wearable access improves the
experience but must never block check-in or viewing a training plan.

## Users and core jobs

### Athlete — primary role

- Connect Apple Health or Health Connect.
- See today's training plan quickly.
- Submit RPE, overall feeling, and pain/injury status in under 30 seconds.
- See personal workout and sleep summaries.
- Control whether sleep and workout summaries are shared with the coach.

### Coach

- See a compact team overview.
- Open one athlete's details.
- Create and send a training plan.
- See explainable monitoring flags with data freshness.
- Never receive access to an athlete outside an active team membership and sharing
  grant.

## MVP navigation

### Athlete

1. `Today` — today's plan, last night's sleep, and check-in.
2. `History` — personal workout and check-in history.
3. `Me` — health connection, sharing controls, account, export, and deletion.

### Coach

1. `Team` — athlete status, latest check-in, plan completion, and freshness.
2. `Plans` — create, assign, and review training plans.
3. `Settings` — team membership, account security, and privacy operations.

There is no separate Sleep tab in the MVP.

## Sleep scope

Read-only sources:

- iOS: HealthKit `sleepAnalysis`
- Android: Health Connect `SleepSessionRecord`

Athlete display:

- last main sleep duration;
- bedtime and wake time;
- seven-night average;
- source and last-sync time;
- Light, Deep, and REM totals only when the source provides reliable stage data.

Coach display:

- last main sleep duration;
- seven-night trend;
- source freshness;
- no raw stage timeline in the team overview.

Normalization:

- sync on app open or explicit refresh;
- first import is limited to 28 days;
- use the local wake date as `sleep_date`;
- merge overlapping intervals before calculating totals;
- choose one preferred source per night to prevent double counting;
- upload a nightly summary, not raw stage intervals.

Sleep exclusions:

- naps;
- manual sleep entry inside this app;
- vendor sleep scores;
- HRV, resting HR, SpO2, respiration, and temperature;
- diagnosis or a red flag derived from sleep alone.

## MVP data categories

- Profile and role
- Team membership and sharing grants
- Training plans and planned sessions
- Athlete check-ins: RPE, feeling, pain/injury status
- Workout summaries
- Nightly sleep summaries
- Explainable flag events
- Sync state, consent history, privacy requests, and security audit events

## Explicit non-goals

- Chat or social feed
- Payments and subscriptions
- Live GPS tracking
- Direct Bluetooth watch pairing
- Raw GPS routes or raw heart-rate series
- Direct Garmin integration in the MVP
- Strava data in the coach dashboard
- Writing planned workouts back to a watch
- Meal plans, medical diagnosis, or automated coaching decisions
- In-app AI assistant
- Web dashboard as a separate product

## Technical baseline

- Mobile: Expo + React Native + Expo Router + TypeScript strict
- Runtime: Node.js 24 LTS and pnpm
- Server state: TanStack Query
- Forms and validation: React Hook Form + Zod
- Backend: Supabase Auth + PostgreSQL + RLS
- Native health bridge: local Expo module with Swift HealthKit and Kotlin Health
  Connect implementations
- Device security: SecureStore; encrypted SQLite only if an offline outbox is needed
- Notifications: Expo Push for non-sensitive reminders
- Monitoring: Sentry free tier with PII scrubbing and session replay disabled
- Verification: unit, component, PostgreSQL/RLS, and critical mobile E2E tests

Exact package versions will be selected and pinned during the platform bootstrap
after checking the current Expo/React Native compatibility matrix.

## Repository boundary

New product code will live under:

```text
platform/
  apps/mobile/
  packages/
  supabase/
```

The package manager workspace and lockfile also live under `platform/`. Root
`supabase/`, `garmin/`, and `scripts/` remain part of the current operational
system.

## Free-first constraint

Start with free and open-source tooling:

- Expo/EAS Free
- Supabase Free for development and pilot
- GitHub Actions Free
- Expo Push
- Sentry Developer
- Resend Free with an owned domain

Do not introduce a paid aggregator, analytics platform, UI kit, icon service, or AI
runtime. Store memberships and a sender domain are external costs that cannot
always be avoided. Supabase Pro is deferred until real usage requires automatic
backups and non-pausing infrastructure.

## Product quality gates

- An athlete can see today's plan within two taps after sign-in.
- An athlete can complete the daily check-in within 30 seconds.
- Denying health permission does not block core use.
- Revoking coach sharing removes coach access immediately.
- A coach from Team A cannot query an athlete from Team B.
- Missing, partial, and stale wearable data is clearly labeled.
- Sleep, workout, RPE, feeling, and pain/injury values never appear in push
  payloads, analytics, logs, session replay, or crash context.
- Every flag shows its reason, rule version, and input freshness.

## Decision rule

When a proposed feature does not directly improve one of the core jobs above, it is
out of scope until after the pilot.
