# TASK-017: Safe Local App Demo Environment and Synthetic Fixtures

Status: Approved

Writer: Claude Code

Reviewers: GPT/Codex (read-only)

Product Owner: Wayu

AGY: not used

Base branch: `feat/mobile-foundation`

Base SHA: `ccd7d4440b69be390fd6ed35a417006bd66c70ff`

Branch: `feat/TASK-017-safe-local-app-demo`

## Goal and user value

The Product Owner can run the whole athlete-and-coach product on their own
machine, against a **local** Supabase stack only, and walk the consent story end
to end with two synthetic accounts:

1. reset the demo environment to a known baseline with one command;
2. sign in as a synthetic athlete and as a synthetic coach, through the **real**
   local Auth flow;
3. confirm the athlete lands in the athlete area and the coach in the coach area;
4. create a synthetic check-in as the athlete;
5. confirm the coach **cannot** see it before consent;
6. grant sharing explicitly in the real UI, and confirm the coach then sees it;
7. revoke sharing, and confirm the coach loses access while the athlete keeps
   self-access.

Everything the demo touches is synthetic and local. No hosted project is
contacted at any point.

## Approved decisions

These ten decisions are the Product Owner's, and they bound the task.

1. **Local Supabase only.** No hosted contact, project link, remote URL, remote
   migration, `db push`, deploy, or production operation.
2. **Web and Android Emulator only.** Physical-device LAN access, iOS, and
   external network exposure are out of scope.
3. **Process-scoped environment only.** Demo commands set process-scoped
   variables and `EXPO_NO_DOTENV=1`. They never read, modify, overwrite, back up,
   or delete `apps/mobile/.env.local`.
4. **Local mode is fail-closed.** The canonical endpoint is
   `http://127.0.0.1:54321`. Only the Android Emulator may map it internally to
   `http://10.0.2.2:54321`. Hosted URLs, arbitrary LAN hosts, other ports,
   userinfo, paths, queries, and fragments are rejected **before** client
   creation.
5. **Publishable credential only.** Accept only the local `sb_publishable_`
   credential. Reject `sb_secret_`, service-role, legacy JWT, database URLs,
   passwords, and malformed keys. Never print or persist raw Supabase
   `start`/`status` output. Only the validated publishable field may cross the
   credential-filter boundary. If the pinned CLI cannot provide this without
   exposing secret-bearing output, stop and report a blocker instead of weakening
   the rule.
6. **Real Auth signup.** Create the two login-capable users through the real
   local public Auth signup flow. Do not insert password state directly into
   internal auth tables, use an Auth Admin/service-role API, or add a mock/demo
   authentication bypass. Apply application fixtures afterward through a strictly
   local database-owner fixture operation with all raw subprocess output
   suppressed.
7. **Random local password, never printed.** Generate a random local password
   during demo reset. Store it only in an ignored `platform/.local-demo`
   credential file. Do not commit or print the password, session, token, key, or
   raw Auth response. Print only a safe path telling the Product Owner where to
   find the local credentials.
8. **Baseline fixture contents.** Exactly two `example.test` accounts, two valid
   profiles, one synthetic team, one active athlete membership, and one active
   coach membership. Roles come only from `team_memberships`, never Auth metadata
   or JWT claims. No persistent Team B fixture.
9. **Zero consent, zero health data at baseline.** The reset baseline contains
   zero `sharing_grants` and zero `daily_check_ins`. Consent is never automatic.
   The Product Owner enters a synthetic check-in and explicitly grants/revokes
   sharing through the real UI.
10. **Isolated worktree only.** No merge, push, deploy, link, remote migration,
    branch deletion, worktree removal, or modification of any protected legacy
    path.

## In scope

- A local-mode Supabase environment contract in the mobile app, fail-closed, with
  unit tests for every rejection category.
- Node-only demo tooling under `platform/tooling/local-demo/`, with unit tests
  including subprocess and output-leak failure paths.
- A synthetic fixture SQL file applied as the local database owner.
- Four commands: `demo:reset`, `demo:web`, `demo:android`, `demo:stop`.
- An ignored local credential file and the `.gitignore` entry for it.
- Documentation: this packet, `docs/app/LOCAL-DEMO.md`, updates to
  `docs/app/SUPABASE-ENVIRONMENT.md`, `platform/README.md`,
  `platform/apps/mobile/README.md`, `platform/apps/mobile/.env.example`, and the
  handoff.

## Out of scope

- Any hosted Supabase operation of any kind.
- iOS, physical devices, LAN exposure, tunnels, and public URLs.
- New dependencies, migrations, RLS policies, or client provisioning capability.
- Any change to `supabase/config.toml`, `database.types.ts`, `pnpm-lock.yaml`, or
  an existing migration or pgTAP test.
- Any UI, auth, check-in, sharing, or coach feature change. The demo exercises the
  product that already exists; it does not extend it.
- Seeding consent or any protected health value.

## Owned paths

- `docs/app/tasks/TASK-017-safe-local-app-demo-environment.md`
- `docs/app/handoffs/TASK-017.md`
- `docs/app/LOCAL-DEMO.md`
- `docs/app/SUPABASE-ENVIRONMENT.md`
- `platform/.gitignore`
- `platform/package.json` (scripts only; no dependency change)
- `platform/tooling/local-demo/**`
- `platform/supabase/fixtures/local-demo.sql`
- `platform/apps/mobile/.env.example`
- `platform/apps/mobile/README.md`
- `platform/README.md`
- `platform/apps/mobile/src/lib/supabase/environment.ts`
- `platform/apps/mobile/src/lib/supabase/environment.test.ts`
- `platform/apps/mobile/src/lib/supabase/client.ts`

## Forbidden paths

- `athletes/`
- `team_data/`
- `garmin/`
- `scripts/`
- root `supabase/`
- root `CLAUDE.md`, `.agents/AGENTS.md`, `.claude/settings*.json`
- `platform/supabase/config.toml`
- `platform/supabase/migrations/**`
- `platform/supabase/tests/**`
- `platform/apps/mobile/src/lib/supabase/database.types.ts`
- `platform/pnpm-lock.yaml`, `platform/pnpm-workspace.yaml`
- `platform/apps/mobile/.env.local`
- every unrelated UI, auth, check-in, sharing, and coach source file

## References

- `AGENTS.md`, `platform/AGENTS.md`
- `docs/app/PRODUCT-CHARTER.md`
- `docs/app/AI-WORKING-AGREEMENT.md`
- `docs/app/CLAUDE-CODE-SETUP.md`
- `docs/app/SUPABASE-ENVIRONMENT.md`
- TASK-008 identity/teams/membership RLS, TASK-011 sharing grants, TASK-012 daily
  check-in RLS, TASK-013/014 athlete surfaces, TASK-016 coach review surface

## Acceptance criteria

- [ ] 1. Repeated `demo:reset` deterministically produces **2 profiles, 1 team,
      2 active memberships, 0 sharing grants, 0 check-ins**.
- [ ] 2. Both accounts authenticate through **real** local Supabase Auth.
- [ ] 3. The athlete routes to the athlete area; the coach routes to the coach
      area. Roles are read from `team_memberships` only.
- [ ] 4. Before consent, the coach **cannot** read the athlete's created
      check-in.
- [ ] 5. After an explicit athlete grant, the coach sees the latest check-in on a
      successful refresh.
- [ ] 6. After revoke, the coach loses access on the next query while the athlete
      keeps self-access.
- [ ] 7. No hosted endpoint is contacted.
- [ ] 8. No raw credential, password, token, user id, health value, Auth
      response, database error, or credential-bearing CLI output appears in logs,
      test failures, terminal handoff, or committed artifacts.
- [ ] 9. Existing cross-team and other-athlete authorization tests remain
      authoritative and unchanged.
- [ ] 10. No automatic consent and no seeded protected health data.
- [ ] 11. No new dependency, migration, RLS policy, or client provisioning
      capability.
- [ ] 12. Launching the app never resets or reseeds implicitly.

## Privacy classification

**Synthetic data only.** The task creates two `example.test` identities and one
synthetic team. It seeds **no** protected health value and **no** consent record.

The health-data path itself is untouched: no migration, policy, grant, or
authorization helper changes, so `private.can_current_user_read_shared_data`
remains the sole gate for coach access.

The one genuinely new secret-adjacent artifact is the generated local demo
password. It lives only in an ignored file under `platform/.local-demo/`, is
never printed, and is regenerated on every reset.

## Verification

```text
# From platform/
corepack pnpm install --frozen-lockfile
corepack pnpm test:tooling
corepack pnpm format:check
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test

# Local demo, local stack only
corepack pnpm demo:reset
corepack pnpm demo:verify

# Database authorization suite (local only)
corepack pnpm exec supabase db reset --local --no-seed
corepack pnpm exec supabase test db --local
corepack pnpm exec supabase db lint --local --schema public,private --level warning --fail-on warning

# Exports
corepack pnpm exec expo export -p web      # from apps/mobile
corepack pnpm exec expo export -p android  # from apps/mobile
corepack pnpm dlx expo-doctor@latest       # from apps/mobile

git diff --check
corepack pnpm demo:stop
docker ps -a --filter name=supabase --format "{{.Names}}"
git status --porcelain
```

Expected baselines: pgTAP **5 files / 583 assertions**, `db lint` **0 findings**,
Expo Doctor **no worse than 20/21**, **0** Supabase containers after
`demo:stop`, clean worktree.

## Dependencies and open decisions

- Depends on the local stack from TASK-007 and the RLS work in TASK-008 through
  TASK-016. All are merged into the base.
- Requires Docker Desktop with the WSL 2 backend running.
- No open decisions. Decisions 1–10 above are approved.

## Required handoff

`docs/app/handoffs/TASK-017.md`, in the canonical format from
`docs/app/AI-WORKING-AGREEMENT.md`:

- clean commit SHAs for every commit;
- changed files;
- verification results;
- privacy/security impact;
- known limitations;
- rollback instructions.

Stop for GPT/Codex read-only review. Do not merge, push, deploy, link, remotely
migrate, clean the worktree, or delete the task branch.
