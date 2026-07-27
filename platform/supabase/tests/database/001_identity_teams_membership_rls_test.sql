-- TASK-008: Identity, teams, and membership RLS authorization tests.
--
-- Every fixture in this file is synthetic, transaction-scoped, and rolled back.
-- No seed file, no persistent fixture, no service-role key, and no real user
-- data is involved. Test addresses use the reserved example.test domain.
--
-- Fixture setup runs as the local database owner. Every authorization
-- assertion switches to the anon or authenticated role with synthetic JWT
-- claims, so Row Level Security and table privileges are actually exercised.

begin;

-- pgTAP is created inside the transaction and rolled back with everything
-- else, so it is never shipped in a migration.
create extension if not exists pgtap with schema extensions;

set local search_path = public, extensions, pg_catalog;

select plan(172);

-- ---------------------------------------------------------------------------
-- Synthetic fixtures
-- ---------------------------------------------------------------------------
--
-- Users
--   coach-a            active coach   in Team A
--   coach-dual         active coach   in Team A and active athlete in Team B
--   athlete-a          active athlete in Team A
--   athlete-a2         active athlete in Team A
--   athlete-a-revoked  revoked athlete in Team A
--   coach-a-revoked    revoked coach  in Team A
--   coach-b            active coach   in Team B
--   athlete-b          active athlete in Team B

insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data)
values
  ('00000000-0000-4000-8000-00000000000a', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-a@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000b', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-a@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000c', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-a2@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000d', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-b@example.test', '{}'::jsonb),
  -- Carries synthetic metadata on purpose: the trigger must not copy it.
  ('00000000-0000-4000-8000-00000000000e', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-b@example.test',
   '{"full_name":"synthetic-metadata-name","name":"synthetic-metadata-name"}'::jsonb),
  ('00000000-0000-4000-8000-00000000000f', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-dual@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000010', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-a-revoked@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000011', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-a-revoked@example.test', '{}'::jsonb);

insert into public.teams (id, name)
values
  ('00000000-0000-4000-8000-0000000000a1', 'Team A'),
  ('00000000-0000-4000-8000-0000000000b1', 'Team B');

insert into public.team_memberships (team_id, profile_id, role, status, revoked_at)
values
  -- Team A
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000a',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000f',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000b',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000c',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-000000000010',
   'athlete', 'revoked', now()),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-000000000011',
   'coach', 'revoked', now()),
  -- Team B
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-00000000000d',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-00000000000e',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-00000000000f',
   'athlete', 'active', null);

-- ---------------------------------------------------------------------------
-- 1. Structure
-- ---------------------------------------------------------------------------

select has_table('public', 'profiles', 'public.profiles exists');
select has_table('public', 'teams', 'public.teams exists');
select has_table('public', 'team_memberships', 'public.team_memberships exists');

select col_is_pk('public', 'profiles', 'id', 'profiles.id is the primary key');
select col_is_pk('public', 'teams', 'id', 'teams.id is the primary key');
select col_is_pk('public', 'team_memberships', 'id', 'team_memberships.id is the primary key');

select col_type_is('public', 'profiles', 'id', 'uuid', 'profiles.id is uuid');
select col_type_is('public', 'teams', 'id', 'uuid', 'teams.id is uuid');
select col_type_is('public', 'team_memberships', 'team_id', 'uuid', 'team_memberships.team_id is uuid');
select col_type_is('public', 'team_memberships', 'profile_id', 'uuid', 'team_memberships.profile_id is uuid');

select col_is_null('public', 'profiles', 'display_name', 'profiles.display_name is nullable');
select col_not_null('public', 'profiles', 'created_at', 'profiles.created_at is not null');
select col_not_null('public', 'teams', 'name', 'teams.name is not null');
select col_not_null('public', 'teams', 'created_at', 'teams.created_at is not null');
select col_not_null('public', 'team_memberships', 'team_id', 'team_memberships.team_id is not null');
select col_not_null('public', 'team_memberships', 'profile_id', 'team_memberships.profile_id is not null');
select col_not_null('public', 'team_memberships', 'role', 'team_memberships.role is not null');
select col_not_null('public', 'team_memberships', 'status', 'team_memberships.status is not null');
select col_not_null('public', 'team_memberships', 'created_at', 'team_memberships.created_at is not null');
select col_is_null('public', 'team_memberships', 'revoked_at', 'team_memberships.revoked_at is nullable');

select fk_ok(
  'public', 'team_memberships', 'team_id',
  'public', 'teams', 'id',
  'team_memberships.team_id references teams.id'
);
select fk_ok(
  'public', 'team_memberships', 'profile_id',
  'public', 'profiles', 'id',
  'team_memberships.profile_id references profiles.id'
);

select is(
  (select confdeltype from pg_catalog.pg_constraint
    where conrelid = 'public.profiles'::regclass and contype = 'f')::text,
  'c',
  'profiles.id cascades on auth.users delete'
);
select is(
  (select confdeltype from pg_catalog.pg_constraint
    where conrelid = 'public.team_memberships'::regclass
      and contype = 'f'
      and conname like '%team_id%')::text,
  'c',
  'team_memberships.team_id cascades on team delete'
);
select is(
  (select confdeltype from pg_catalog.pg_constraint
    where conrelid = 'public.team_memberships'::regclass
      and contype = 'f'
      and conname like '%profile_id%')::text,
  'c',
  'team_memberships.profile_id cascades on profile delete'
);

select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.profiles'::regclass
      and conname = 'profiles_display_name_valid'),
  1,
  'profiles_display_name_valid constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.teams'::regclass
      and conname = 'teams_name_valid'),
  1,
  'teams_name_valid constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.team_memberships'::regclass
      and conname = 'team_memberships_role_valid'),
  1,
  'team_memberships_role_valid constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.team_memberships'::regclass
      and conname = 'team_memberships_status_valid'),
  1,
  'team_memberships_status_valid constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.team_memberships'::regclass
      and conname = 'team_memberships_status_revoked_at_consistent'),
  1,
  'team_memberships_status_revoked_at_consistent constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.team_memberships'::regclass
      and conname = 'team_memberships_team_profile_unique'
      and contype = 'u'),
  1,
  'team_memberships unique (team_id, profile_id) constraint exists'
);

select has_index('public', 'team_memberships', 'team_memberships_profile_id_idx',
  'membership lookup index on profile_id exists');
select has_index('public', 'team_memberships', 'team_memberships_team_id_idx',
  'membership lookup index on team_id exists');
select has_index('public', 'team_memberships', 'team_memberships_active_coach_idx',
  'partial index for active coach lookups exists');
select has_index('public', 'team_memberships', 'team_memberships_active_team_idx',
  'partial index for active team lookups exists');

-- ---------------------------------------------------------------------------
-- 2. Constraint behaviour (positive controls run as the owner)
-- ---------------------------------------------------------------------------

select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status)
     values ('00000000-0000-4000-8000-0000000000a1',
             '00000000-0000-4000-8000-00000000000b', 'coach', 'active') $$,
  '23505', null,
  'a second membership row for the same user and team is rejected'
);
select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000b', 'manager', 'active') $$,
  '23514', null,
  'a role outside coach and athlete is rejected'
);
select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000b', 'athlete', 'suspended') $$,
  '23514', null,
  'a status outside active and revoked is rejected'
);
select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status, revoked_at)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000b', 'athlete', 'active', now()) $$,
  '23514', null,
  'an active membership with revoked_at set is rejected'
);
select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status, revoked_at)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000b', 'athlete', 'revoked', null) $$,
  '23514', null,
  'a revoked membership without revoked_at is rejected'
);
select throws_ok(
  $$ insert into public.teams (name) values ('   ') $$,
  '23514', null,
  'a blank team name is rejected'
);
select throws_ok(
  $$ update public.profiles set display_name = '   '
     where id = '00000000-0000-4000-8000-00000000000a' $$,
  '23514', null,
  'a blank display_name is rejected'
);
select lives_ok(
  $$ update public.profiles set display_name = 'synthetic-display-name'
     where id = '00000000-0000-4000-8000-00000000000a' $$,
  'a valid display_name is accepted by the constraint'
);
select lives_ok(
  $$ update public.profiles set display_name = null
     where id = '00000000-0000-4000-8000-00000000000a' $$,
  'display_name may be cleared back to null'
);

-- ---------------------------------------------------------------------------
-- 3. Automatic profile creation
-- ---------------------------------------------------------------------------

select is(
  (select count(*)::int from public.profiles
    where id in (
      '00000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-00000000000b',
      '00000000-0000-4000-8000-00000000000c', '00000000-0000-4000-8000-00000000000d',
      '00000000-0000-4000-8000-00000000000e', '00000000-0000-4000-8000-00000000000f',
      '00000000-0000-4000-8000-000000000010', '00000000-0000-4000-8000-000000000011')),
  8,
  'an auth.users insert creates a linked profile for every synthetic user'
);
select ok(
  (select exists (select 1 from public.profiles
    where id = '00000000-0000-4000-8000-00000000000a')),
  'coach-a has an automatically created profile'
);
select is(
  (select display_name from public.profiles
    where id = '00000000-0000-4000-8000-00000000000e'),
  null,
  'auth metadata is never copied into display_name'
);
select is(
  (select count(*)::int from public.profiles where display_name is not null),
  0,
  'no profile receives a display_name at creation time'
);
select ok(
  (select created_at is not null from public.profiles
    where id = '00000000-0000-4000-8000-00000000000a'),
  'a created profile stamps created_at'
);

-- ---------------------------------------------------------------------------
-- 4. Anonymous access
-- ---------------------------------------------------------------------------

set local role anon;

select throws_ok(
  $$ select * from public.profiles $$,
  '42501', null,
  'anonymous cannot read profiles'
);
select throws_ok(
  $$ select * from public.teams $$,
  '42501', null,
  'anonymous cannot read teams'
);
select throws_ok(
  $$ select * from public.team_memberships $$,
  '42501', null,
  'anonymous cannot read team_memberships'
);
select throws_ok(
  $$ insert into public.teams (name) values ('anon team') $$,
  '42501', null,
  'anonymous cannot insert a team'
);

reset role;

-- ---------------------------------------------------------------------------
-- 5. Athlete A visibility
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'athlete-a reads their own profile'
);
select is(
  (select count(*)::int from public.profiles),
  1,
  'athlete-a sees exactly one profile in total'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'athlete-a cannot read athlete-a2'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000a'),
  0,
  'athlete-a cannot read coach-a'
);
select is(
  (select count(*)::int from public.team_memberships
    where profile_id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'athlete-a reads their own membership'
);
select is(
  (select count(*)::int from public.team_memberships),
  1,
  'athlete-a sees exactly one membership row in total'
);
select is(
  (select count(*)::int from public.team_memberships
    where profile_id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'athlete-a cannot read the membership of athlete-a2'
);
select is(
  (select count(*)::int from public.team_memberships
    where profile_id = '00000000-0000-4000-8000-00000000000a'),
  0,
  'athlete-a cannot read the membership of coach-a'
);
select is(
  (select count(*)::int from public.teams),
  1,
  'athlete-a sees exactly one team'
);
select is(
  (select name from public.teams
    where id = '00000000-0000-4000-8000-0000000000a1'),
  'Team A',
  'athlete-a reads the name of their active team'
);
select is(
  (select count(*)::int from public.teams
    where id = '00000000-0000-4000-8000-0000000000b1'),
  0,
  'athlete-a cannot read Team B'
);

-- ---------------------------------------------------------------------------
-- 6. Active coach A visibility
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select is(
  (select count(*)::int from public.profiles),
  4,
  'coach-a sees exactly the four active Team A profiles'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'coach-a reads athlete-a'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000c'),
  1,
  'coach-a reads athlete-a2'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000f'),
  1,
  'coach-a reads coach-dual, an active co-member of Team A'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-000000000010'),
  0,
  'coach-a cannot read a revoked Team A athlete profile'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-000000000011'),
  0,
  'coach-a cannot read a revoked Team A coach profile'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000e'),
  0,
  'coach-a cannot read athlete-b'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000d'),
  0,
  'coach-a cannot read coach-b'
);
select is(
  (select count(*)::int from public.team_memberships),
  4,
  'coach-a sees exactly the four active Team A membership rows'
);
select is(
  (select count(*)::int from public.team_memberships where status = 'revoked'),
  0,
  'coach-a sees no revoked membership row'
);
select is(
  (select count(*)::int from public.team_memberships
    where team_id = '00000000-0000-4000-8000-0000000000b1'),
  0,
  'coach-a sees no Team B membership row'
);
select is(
  (select count(*)::int from public.teams),
  1,
  'coach-a sees exactly one team'
);
select is(
  (select name from public.teams
    where id = '00000000-0000-4000-8000-0000000000a1'),
  'Team A',
  'coach-a reads Team A'
);
select is(
  (select count(*)::int from public.teams
    where id = '00000000-0000-4000-8000-0000000000b1'),
  0,
  'coach-a cannot read Team B'
);

-- ---------------------------------------------------------------------------
-- 7. Coach B isolation
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000d","role":"authenticated"}';

select is(
  (select count(*)::int from public.teams
    where id = '00000000-0000-4000-8000-0000000000a1'),
  0,
  'coach-b cannot read Team A'
);
select is(
  (select count(*)::int from public.teams),
  1,
  'coach-b sees only Team B'
);
select is(
  (select count(*)::int from public.profiles),
  3,
  'coach-b sees exactly the three active Team B profiles'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'coach-b cannot read athlete-a'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000a'),
  0,
  'coach-b cannot read coach-a'
);
select is(
  (select count(*)::int from public.team_memberships
    where team_id = '00000000-0000-4000-8000-0000000000a1'),
  0,
  'coach-b sees no Team A membership row'
);
select is(
  (select count(*)::int from public.team_memberships),
  3,
  'coach-b sees exactly the three active Team B membership rows'
);

-- ---------------------------------------------------------------------------
-- 8. Multi-team user: coach in Team A, athlete in Team B
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000f","role":"authenticated"}';

select is(
  (select count(*)::int from public.teams),
  2,
  'coach-dual sees both teams they actively belong to'
);
select is(
  (select count(*)::int from public.profiles),
  4,
  'coach-dual sees only the four active Team A profiles'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'coach-dual has coach visibility of athlete-a in the coached team'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000e'),
  0,
  'coach-dual has no coach visibility of athlete-b in the team where they are an athlete'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000d'),
  0,
  'coach-dual cannot read coach-b'
);
select is(
  (select count(*)::int from public.team_memberships),
  5,
  'coach-dual sees the four active Team A rows plus their own Team B row'
);
select is(
  (select count(*)::int from public.team_memberships
    where team_id = '00000000-0000-4000-8000-0000000000b1'),
  1,
  'coach-dual sees only their own row in the team where they are an athlete'
);
select is(
  (select role from public.team_memberships
    where team_id = '00000000-0000-4000-8000-0000000000b1'),
  'athlete',
  'the single visible Team B row is the athlete membership of coach-dual'
);

-- ---------------------------------------------------------------------------
-- 9. Revoked users
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000010","role":"authenticated"}';

select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-000000000010'),
  1,
  'a revoked athlete still reads their own profile'
);
select is(
  (select count(*)::int from public.profiles),
  1,
  'a revoked athlete sees no other profile'
);
select is(
  (select count(*)::int from public.team_memberships),
  1,
  'a revoked athlete still reads their own membership row'
);
select is(
  (select status from public.team_memberships),
  'revoked',
  'the retained membership row of a revoked athlete reads as revoked'
);
select ok(
  (select revoked_at is not null from public.team_memberships),
  'the retained membership row of a revoked athlete records revoked_at'
);
select is(
  (select count(*)::int from public.teams),
  0,
  'a revoked athlete loses access to the team'
);

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000011","role":"authenticated"}';

select is(
  (select count(*)::int from public.profiles),
  1,
  'a revoked coach sees only their own profile'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'a revoked coach loses access to former team members'
);
select is(
  (select count(*)::int from public.team_memberships),
  1,
  'a revoked coach still reads their own revoked membership row'
);
select is(
  (select count(*)::int from public.teams),
  0,
  'a revoked coach loses access to the team'
);

-- ---------------------------------------------------------------------------
-- 10. Authenticated writes are refused
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000b', 'coach', 'active') $$,
  '42501', null,
  'an authenticated user cannot self-insert a coach membership'
);
select throws_ok(
  $$ update public.team_memberships set role = 'coach'
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot change their own role'
);
select throws_ok(
  $$ update public.team_memberships set status = 'revoked', revoked_at = now()
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot change their own status'
);
select throws_ok(
  $$ update public.team_memberships
     set team_id = '00000000-0000-4000-8000-0000000000b1'
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot move their membership to another team'
);
select throws_ok(
  $$ update public.team_memberships
     set profile_id = '00000000-0000-4000-8000-00000000000c'
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot reassign their membership to another profile'
);
select throws_ok(
  $$ delete from public.team_memberships
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot delete their own membership'
);
select throws_ok(
  $$ insert into public.teams (name) values ('Team C') $$,
  '42501', null,
  'an authenticated user cannot insert a team'
);
select throws_ok(
  $$ update public.teams set name = 'Renamed'
     where id = '00000000-0000-4000-8000-0000000000a1' $$,
  '42501', null,
  'an authenticated user cannot update a team'
);
select throws_ok(
  $$ delete from public.teams where id = '00000000-0000-4000-8000-0000000000a1' $$,
  '42501', null,
  'an authenticated user cannot delete a team'
);
select throws_ok(
  $$ truncate public.teams $$,
  '42501', null,
  'an authenticated user cannot truncate a team table'
);
select throws_ok(
  $$ insert into public.profiles (id) values ('00000000-0000-4000-8000-000000000099') $$,
  '42501', null,
  'an authenticated user cannot insert a profile'
);
select throws_ok(
  $$ update public.profiles set display_name = 'renamed'
     where id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot update their own profile in this task'
);
select throws_ok(
  $$ delete from public.profiles where id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an authenticated user cannot delete their own profile'
);

-- The same refusals apply to an active coach.
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status)
     values ('00000000-0000-4000-8000-0000000000a1',
             '00000000-0000-4000-8000-00000000000e', 'athlete', 'active') $$,
  '42501', null,
  'an active coach cannot add a membership'
);
select throws_ok(
  $$ update public.team_memberships set status = 'revoked', revoked_at = now()
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an active coach cannot revoke a membership'
);
select throws_ok(
  $$ update public.team_memberships set role = 'coach'
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an active coach cannot promote an athlete'
);
select throws_ok(
  $$ delete from public.team_memberships
     where profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an active coach cannot delete a membership'
);
select throws_ok(
  $$ update public.team_memberships set status = 'revoked', revoked_at = now()
     where team_id = '00000000-0000-4000-8000-0000000000b1' $$,
  '42501', null,
  'no cross-team update succeeds'
);
select throws_ok(
  $$ delete from public.team_memberships
     where team_id = '00000000-0000-4000-8000-0000000000b1' $$,
  '42501', null,
  'no cross-team delete succeeds'
);
select throws_ok(
  $$ update public.profiles set display_name = 'renamed'
     where id = '00000000-0000-4000-8000-00000000000b' $$,
  '42501', null,
  'an active coach cannot edit an athlete profile'
);

-- Positive control: nothing above actually changed any row.
reset role;

select is(
  (select count(*)::int from public.team_memberships),
  9,
  'every membership row survives the refused writes'
);
select is(
  (select role from public.team_memberships
    where profile_id = '00000000-0000-4000-8000-00000000000b'),
  'athlete',
  'athlete-a still holds the athlete role after the refused writes'
);
select is(
  (select status from public.team_memberships
    where profile_id = '00000000-0000-4000-8000-00000000000b'),
  'active',
  'athlete-a is still active after the refused writes'
);
select is(
  (select count(*)::int from public.teams),
  2,
  'both teams survive the refused writes'
);

-- ---------------------------------------------------------------------------
-- 11. Revocation takes effect on the next query
-- ---------------------------------------------------------------------------

update public.team_memberships
set status = 'revoked', revoked_at = now()
where profile_id = '00000000-0000-4000-8000-00000000000b'
  and team_id = '00000000-0000-4000-8000-0000000000a1';

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select is(
  (select count(*)::int from public.teams),
  0,
  'a freshly revoked athlete loses the team on the next query'
);
select is(
  (select count(*)::int from public.profiles),
  1,
  'a freshly revoked athlete keeps only their own profile'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'a freshly revoked athlete still reads their own profile'
);
select is(
  (select count(*)::int from public.team_memberships),
  1,
  'a freshly revoked athlete still reads their own membership row'
);
select is(
  (select status from public.team_memberships),
  'revoked',
  'the retained row reads as revoked immediately'
);

set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'the coach loses access to the revoked athlete on the next query'
);
select is(
  (select count(*)::int from public.profiles),
  3,
  'the coach roster shrinks to the remaining active members'
);
select is(
  (select count(*)::int from public.team_memberships),
  3,
  'the coach sees only the remaining active membership rows'
);

reset role;

-- Restore the fixture so the remaining sections read a normal state.
update public.team_memberships
set status = 'active', revoked_at = null
where profile_id = '00000000-0000-4000-8000-00000000000b'
  and team_id = '00000000-0000-4000-8000-0000000000a1';

-- ---------------------------------------------------------------------------
-- 12. Row Level Security is enabled
-- ---------------------------------------------------------------------------

select ok(
  (select relrowsecurity from pg_catalog.pg_class where oid = 'public.profiles'::regclass),
  'RLS is enabled on public.profiles'
);
select ok(
  (select relrowsecurity from pg_catalog.pg_class where oid = 'public.teams'::regclass),
  'RLS is enabled on public.teams'
);
select ok(
  (select relrowsecurity from pg_catalog.pg_class where oid = 'public.team_memberships'::regclass),
  'RLS is enabled on public.team_memberships'
);

select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename in ('profiles', 'teams', 'team_memberships')
      and cmd = 'SELECT'),
  3,
  'exactly one SELECT policy exists per table'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename in ('profiles', 'teams', 'team_memberships')
      and cmd <> 'SELECT'),
  0,
  'no write policy exists on any of the three tables'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename in ('profiles', 'teams', 'team_memberships')
      and 'anon' = any (roles)),
  0,
  'no policy targets the anon role'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename in ('profiles', 'teams', 'team_memberships')
      and 'public' = any (roles)),
  0,
  'no policy targets every role'
);

-- ---------------------------------------------------------------------------
-- 13. Grants
-- ---------------------------------------------------------------------------

select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('profiles', 'teams', 'team_memberships')
      and grantee = 'anon'),
  0,
  'anon holds no table privilege on the three tables'
);
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('profiles', 'teams', 'team_memberships')
      and grantee = 'authenticated'
      and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')),
  0,
  'authenticated holds no write privilege on the three tables'
);
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('profiles', 'teams', 'team_memberships')
      and grantee = 'authenticated'
      and privilege_type = 'SELECT'),
  3,
  'authenticated holds SELECT on exactly the three tables'
);
select ok(
  not has_table_privilege('anon', 'public.profiles', 'select'),
  'anon cannot select from profiles'
);
select ok(
  not has_table_privilege('anon', 'public.teams', 'select'),
  'anon cannot select from teams'
);
select ok(
  not has_table_privilege('anon', 'public.team_memberships', 'select'),
  'anon cannot select from team_memberships'
);
select ok(
  has_table_privilege('authenticated', 'public.profiles', 'select'),
  'authenticated can select from profiles'
);
select ok(
  not has_table_privilege('authenticated', 'public.profiles', 'insert'),
  'authenticated cannot insert into profiles'
);
select ok(
  not has_table_privilege('authenticated', 'public.team_memberships', 'update'),
  'authenticated cannot update team_memberships'
);
select ok(
  not has_table_privilege('authenticated', 'public.teams', 'delete'),
  'authenticated cannot delete from teams'
);

-- ---------------------------------------------------------------------------
-- 14. Helper functions
-- ---------------------------------------------------------------------------

select has_schema('private', 'the private schema exists');

select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private'),
  4,
  'all four helpers live in the private schema'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private' and p.prosecdef),
  4,
  'every private helper is SECURITY DEFINER'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private'
      and coalesce(array_to_string(p.proconfig, ','), '') like '%search_path=%'),
  4,
  'every private helper pins a search_path'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private'
      and exists (
        select 1 from unnest(p.proconfig) as cfg
        -- PostgreSQL stores an empty search_path canonically as search_path=""
        where cfg in ('search_path=""', 'search_path='))),
  4,
  'every private helper pins an empty search_path'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('public', 'graphql_public')
      and p.proname in (
        'handle_new_user', 'is_active_team_member',
        'is_active_team_coach', 'is_coached_by_current_user')),
  0,
  'no helper is defined in an exposed schema'
);
select ok(
  not has_schema_privilege('anon', 'private', 'usage'),
  'anon holds no usage on the private schema'
);
select ok(
  has_schema_privilege('authenticated', 'private', 'usage'),
  'authenticated holds usage on the private schema so policies can run'
);
select ok(
  not has_function_privilege('anon', 'private.is_active_team_member(uuid)', 'execute'),
  'anon cannot execute the membership helper'
);
select ok(
  not has_function_privilege('anon', 'private.is_active_team_coach(uuid)', 'execute'),
  'anon cannot execute the coach helper'
);
select ok(
  not has_function_privilege('anon', 'private.is_coached_by_current_user(uuid)', 'execute'),
  'anon cannot execute the coached-profile helper'
);
select ok(
  not has_function_privilege('authenticated', 'private.handle_new_user()', 'execute'),
  'authenticated cannot execute the signup trigger function'
);
select ok(
  has_function_privilege('authenticated', 'private.is_active_team_member(uuid)', 'execute'),
  'authenticated can execute the membership helper used by the policies'
);
select ok(
  has_function_privilege('authenticated', 'private.is_active_team_coach(uuid)', 'execute'),
  'authenticated can execute the coach helper used by the policies'
);
select ok(
  has_function_privilege('authenticated', 'private.is_coached_by_current_user(uuid)', 'execute'),
  'authenticated can execute the coached-profile helper used by the policies'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private' and p.proname like '%health%'),
  0,
  'no broad health-data authorization helper exists'
);

-- ---------------------------------------------------------------------------
-- 15. Trusted cascade deletion
-- ---------------------------------------------------------------------------

delete from auth.users where id = '00000000-0000-4000-8000-00000000000c';

select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'deleting an auth user cascades to the profile'
);
select is(
  (select count(*)::int from public.team_memberships
    where profile_id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'deleting an auth user cascades to the membership row'
);

delete from public.teams where id = '00000000-0000-4000-8000-0000000000b1';

select is(
  (select count(*)::int from public.team_memberships
    where team_id = '00000000-0000-4000-8000-0000000000b1'),
  0,
  'deleting a team cascades to its membership rows'
);
select is(
  (select count(*)::int from public.profiles
    where id = '00000000-0000-4000-8000-00000000000e'),
  1,
  'deleting a team leaves the member profiles intact'
);

select * from finish();

rollback;
