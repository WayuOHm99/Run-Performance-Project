-- TASK-017: local demo fixture.
--
-- This is NOT a migration and NOT a seed. It lives outside
-- `supabase/migrations/`, and outside the `[db.seed] sql_paths` list in
-- `config.toml`, so `supabase db reset` never applies it implicitly. It runs only
-- when `demo:reset` applies it explicitly, and only against the local stack.
--
-- It is applied as the local database owner, which is why it can write
-- `public.teams` and `public.team_memberships` at all: no client role holds an
-- INSERT privilege on either table, and TASK-008 created no write policy for
-- them. That is deliberate — team administration is not a client capability, and
-- this fixture does not make it one.
--
-- What it does NOT do, by decision 6: it never creates an auth user, never
-- writes a password, an identity, or any other `auth` schema row. The two users
-- must already exist, created through the real public signup flow before this
-- runs. If they do not, this fails loudly rather than inventing them.
--
-- What it does NOT do, by decision 9: it inserts no `sharing_grants` row and no
-- `daily_check_ins` row. Consent is never automatic, and no protected health
-- value is ever seeded. The deletes below are what make that a property of the
-- fixture rather than a property of having just run `db reset`.
--
-- The whole fixture is deliberately **one** `DO` statement. `supabase db query
-- --file` sends the file as a single prepared statement, which cannot carry
-- multiple commands, so an explicit `begin; ... commit;` fails outright. One
-- statement is atomic anyway: any exception raised below rolls back every write
-- here, which is exactly the guarantee the transaction block was there to give.

do $$
declare
  v_athlete_id uuid;
  v_coach_id   uuid;
  v_team_id    constant uuid := '00000000-0000-4000-8000-000000000017';
begin
  select id into v_athlete_id
  from auth.users
  where email = 'athlete-a@example.test';

  select id into v_coach_id
  from auth.users
  where email = 'coach-a@example.test';

  -- Fixed message. It names neither address nor id, so a failure here cannot
  -- become a way to enumerate local accounts.
  if v_athlete_id is null or v_coach_id is null then
    raise exception
      'local demo fixture: the expected synthetic auth users do not exist; run the signup step first'
      using errcode = '23503';
  end if;

  -- The signup trigger already created these rows with a null display_name.
  -- A null one would make the coach surface fail closed (TASK-016 limitation 2),
  -- so the demo would look broken for a reason unrelated to consent.
  insert into public.profiles (id, display_name)
  values (v_athlete_id, 'Athlete A')
  on conflict (id) do update set display_name = excluded.display_name;

  insert into public.profiles (id, display_name)
  values (v_coach_id, 'Coach A')
  on conflict (id) do update set display_name = excluded.display_name;

  -- One team. Decision 8 explicitly excludes a persistent Team B: the
  -- cross-team negative case is owned by the pgTAP suite, which builds and rolls
  -- back its own fixtures, and duplicating it here would leave a second team
  -- lying around in a demo whose whole point is a single clear story.
  insert into public.teams (id, name)
  values (v_team_id, 'Demo Team A')
  on conflict (id) do update set name = excluded.name;

  -- Exactly one active athlete membership and one active coach membership.
  -- `revoked_at` is reset to null alongside `status` so a re-applied fixture
  -- cannot violate `team_memberships_status_revoked_at_consistent`.
  --
  -- These two rows are the *only* source of role in the product. The app reads
  -- roles from here under RLS and never from Auth metadata or a JWT claim.
  insert into public.team_memberships (team_id, profile_id, role, status)
  values (v_team_id, v_athlete_id, 'athlete', 'active')
  on conflict (team_id, profile_id) do update
    set role = excluded.role,
        status = excluded.status,
        revoked_at = null;

  insert into public.team_memberships (team_id, profile_id, role, status)
  values (v_team_id, v_coach_id, 'coach', 'active')
  on conflict (team_id, profile_id) do update
    set role = excluded.role,
        status = excluded.status,
        revoked_at = null;

  -- Decision 9, made explicit. After `db reset --no-seed` both tables are
  -- already empty, so these are normally no-ops; they are here so that "the
  -- baseline has zero consent and zero health rows" is guaranteed by the
  -- fixture itself rather than by what happened to run before it.
  --
  -- Only the owner can run these: `authenticated` holds no DELETE privilege on
  -- either table and no DELETE policy exists, so this is not a capability the
  -- application gains.
  delete from public.sharing_grants;
  delete from public.daily_check_ins;
end;
$$;
