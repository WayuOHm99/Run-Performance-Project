-- TASK-009: Self display-name update authorization tests.
--
-- Every fixture in this file is synthetic, transaction-scoped, and rolled back.
-- No seed file, no persistent fixture, no service-role key, and no real user
-- data is involved. Test addresses use the reserved example.test domain.
--
-- Fixture setup runs as the local database owner. Every authorization
-- assertion switches to the anon or authenticated role with synthetic JWT
-- claims, so Row Level Security and column privileges are actually exercised.
--
-- The capability under test is deliberately narrow: a user may change their own
-- display_name and nothing else. This file proves both halves of that -- that
-- the intended edit works, and that every adjacent write is still refused.

begin;

create extension if not exists pgtap with schema extensions;

set local search_path = public, extensions, pg_catalog;

select plan(43);

-- ---------------------------------------------------------------------------
-- Synthetic fixtures
-- ---------------------------------------------------------------------------
--
-- Users
--   self       active athlete in Team X, display_name initially null
--   other      active athlete in Team X, display_name already set
--   coach      active coach   in Team X
--   revoked    revoked athlete in Team X

insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data)
values
  ('00000000-0000-4000-9000-000000000001', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'self@example.test', '{}'::jsonb),
  ('00000000-0000-4000-9000-000000000002', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'other@example.test', '{}'::jsonb),
  ('00000000-0000-4000-9000-000000000003', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach@example.test', '{}'::jsonb),
  ('00000000-0000-4000-9000-000000000004', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'revoked@example.test', '{}'::jsonb);

insert into public.teams (id, name)
values ('00000000-0000-4000-9000-0000000000f1', 'Team X');

insert into public.team_memberships (team_id, profile_id, role, status, revoked_at)
values
  ('00000000-0000-4000-9000-0000000000f1', '00000000-0000-4000-9000-000000000001',
   'athlete', 'active', null),
  ('00000000-0000-4000-9000-0000000000f1', '00000000-0000-4000-9000-000000000002',
   'athlete', 'active', null),
  ('00000000-0000-4000-9000-0000000000f1', '00000000-0000-4000-9000-000000000003',
   'coach', 'active', null),
  ('00000000-0000-4000-9000-0000000000f1', '00000000-0000-4000-9000-000000000004',
   'athlete', 'revoked', now());

-- The signup trigger created every profile with a null display_name. Give one
-- user a name up front so "another user's existing name is never altered" is a
-- meaningful assertion.
update public.profiles
set display_name = 'other-original'
where id = '00000000-0000-4000-9000-000000000002';

-- A row filtered out by an UPDATE policy produces a successful statement that
-- affects zero rows, not an error, so the refusal has to be measured as an
-- affected-row count. PostgreSQL forbids a data-modifying CTE inside a scalar
-- subexpression, so the count is captured here instead.
--
-- SECURITY INVOKER on purpose: the update inside runs as whichever role calls
-- the function, so RLS is exercised exactly as it would be from the client.
-- A null p_id runs the update unqualified, which is how the mass-rename case
-- below is tested.
create function pg_temp.attempt_display_name_update(p_id uuid, p_name text)
returns integer
language plpgsql
as $$
declare
  affected integer;
begin
  update public.profiles
  set display_name = p_name
  where p_id is null or id = p_id;

  get diagnostics affected = row_count;
  return affected;
end;
$$;

-- ---------------------------------------------------------------------------
-- 1. Policy and privilege catalog
-- ---------------------------------------------------------------------------

select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'profiles'
      and policyname = 'profiles_update_self'),
  1,
  'the profiles_update_self policy exists'
);
select is(
  (select cmd from pg_catalog.pg_policies
    where schemaname = 'public' and policyname = 'profiles_update_self'),
  'UPDATE',
  'profiles_update_self is an UPDATE policy'
);
select is(
  (select array_to_string(roles, ',') from pg_catalog.pg_policies
    where schemaname = 'public' and policyname = 'profiles_update_self'),
  'authenticated',
  'profiles_update_self targets the authenticated role only'
);
select isnt(
  (select qual from pg_catalog.pg_policies
    where schemaname = 'public' and policyname = 'profiles_update_self'),
  null,
  'profiles_update_self defines a USING expression'
);
select isnt(
  (select with_check from pg_catalog.pg_policies
    where schemaname = 'public' and policyname = 'profiles_update_self'),
  null,
  'profiles_update_self defines a WITH CHECK expression'
);

-- The grant is column-level, so the table-level probe must stay false. That is
-- what keeps id and created_at out of reach.
select ok(
  not has_table_privilege('authenticated', 'public.profiles', 'update'),
  'authenticated holds no table-level UPDATE on profiles'
);
select ok(
  has_column_privilege('authenticated', 'public.profiles', 'display_name', 'update'),
  'authenticated may update the display_name column'
);
select ok(
  not has_column_privilege('authenticated', 'public.profiles', 'id', 'update'),
  'authenticated may not update the id column'
);
select ok(
  not has_column_privilege('authenticated', 'public.profiles', 'created_at', 'update'),
  'authenticated may not update the created_at column'
);
select ok(
  not has_column_privilege('anon', 'public.profiles', 'display_name', 'update'),
  'anon may not update the display_name column'
);
-- The table-wide SELECT grant from TASK-008 expands into a per-column SELECT
-- row here, so only the write privileges are meaningful to pin down.
select is(
  (select coalesce(string_agg(column_name || ':' || privilege_type, ', '
                              order by column_name, privilege_type), '')
     from information_schema.role_column_grants
    where table_schema = 'public'
      and table_name = 'profiles'
      and grantee = 'authenticated'
      and privilege_type <> 'SELECT'),
  'display_name:UPDATE',
  'display_name UPDATE is the only write column grant authenticated holds on profiles'
);
select is(
  (select count(*)::int from information_schema.role_column_grants
    where table_schema = 'public' and table_name = 'profiles' and grantee = 'anon'),
  0,
  'anon holds no column privilege on profiles'
);

-- ---------------------------------------------------------------------------
-- 2. The intended capability works
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-9000-000000000001","role":"authenticated"}';

select lives_ok(
  $$ update public.profiles set display_name = 'synthetic-self-name'
     where id = '00000000-0000-4000-9000-000000000001' $$,
  'a user may set their own display_name'
);
select is(
  (select display_name from public.profiles
    where id = '00000000-0000-4000-9000-000000000001'),
  'synthetic-self-name',
  'the new display_name is stored'
);
select lives_ok(
  $$ update public.profiles set display_name = 'synthetic-self-renamed'
     where id = '00000000-0000-4000-9000-000000000001' $$,
  'a user may edit an already-set display_name'
);
select is(
  (select display_name from public.profiles
    where id = '00000000-0000-4000-9000-000000000001'),
  'synthetic-self-renamed',
  'the edited display_name is stored'
);

-- ---------------------------------------------------------------------------
-- 3. Adjacent writes are still refused
-- ---------------------------------------------------------------------------
--
-- Two distinct refusal shapes appear below, and the difference is deliberate.
--
--   * A column the caller holds no grant on is refused at the privilege layer
--     and raises 42501.
--   * A row the policy's USING excludes is filtered out, so the statement
--     succeeds and affects zero rows rather than raising. Asserting the
--     affected-row count is the only correct way to test that case.

select throws_ok(
  $$ update public.profiles set id = '00000000-0000-4000-9000-0000000000ff'
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user cannot change their own profile id'
);
select throws_ok(
  $$ update public.profiles set created_at = now()
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user cannot change their own created_at'
);
select throws_ok(
  $$ update public.profiles
     set display_name = 'smuggled', created_at = now()
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a forbidden column cannot ride along with a permitted one'
);
select throws_ok(
  $$ update public.profiles set display_name = null
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user cannot clear their display_name back to null'
);
-- 42501, not the 23514 the profiles_display_name_valid constraint would give.
-- PostgreSQL evaluates the RLS WITH CHECK before the table CHECK constraint,
-- so for a client write the policy is what actually rejects a blank or
-- over-length name. The constraint is retained and still governs every
-- non-client write path, including the signup trigger.
select throws_ok(
  $$ update public.profiles set display_name = '   '
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user cannot store a blank display_name'
);
select throws_ok(
  $$ update public.profiles set display_name = repeat('x', 81)
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user cannot store an over-length display_name'
);
select throws_ok(
  $$ insert into public.profiles (id)
     values ('00000000-0000-4000-9000-0000000000fe') $$,
  '42501', null,
  'a user cannot insert a profile'
);
select throws_ok(
  $$ delete from public.profiles
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user cannot delete their own profile'
);

-- Another user's profile: the row is filtered, so nothing is updated.
select is(
  pg_temp.attempt_display_name_update(
    '00000000-0000-4000-9000-000000000002', 'hijacked'),
  0,
  'a user cannot edit another user display_name'
);
-- An unqualified update must not become a mass rename either.
select is(
  pg_temp.attempt_display_name_update(null, 'mass-rename'),
  1,
  'an unqualified update reaches only the caller own row'
);

-- Membership and team writes are untouched by TASK-009.
select throws_ok(
  $$ insert into public.team_memberships (team_id, profile_id, role, status)
     values ('00000000-0000-4000-9000-0000000000f1',
             '00000000-0000-4000-9000-000000000001', 'coach', 'active') $$,
  '42501', null,
  'a user still cannot insert a membership'
);
select throws_ok(
  $$ update public.team_memberships set role = 'coach'
     where profile_id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user still cannot promote themselves to coach'
);
select throws_ok(
  $$ update public.team_memberships set status = 'active', revoked_at = null
     where profile_id = '00000000-0000-4000-9000-000000000004' $$,
  '42501', null,
  'a user still cannot reactivate a revoked membership'
);
select throws_ok(
  $$ delete from public.team_memberships
     where profile_id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'a user still cannot delete a membership'
);
select throws_ok(
  $$ update public.teams set name = 'renamed'
     where id = '00000000-0000-4000-9000-0000000000f1' $$,
  '42501', null,
  'a user still cannot rename a team'
);

-- ---------------------------------------------------------------------------
-- 4. A coach gains nothing over another user profile
-- ---------------------------------------------------------------------------

set local request.jwt.claims = '{"sub":"00000000-0000-4000-9000-000000000003","role":"authenticated"}';

select is(
  pg_temp.attempt_display_name_update(
    '00000000-0000-4000-9000-000000000002', 'coach-renamed-athlete'),
  0,
  'an active coach cannot rename an athlete they coach'
);
select is(
  (select display_name from public.profiles
    where id = '00000000-0000-4000-9000-000000000002'),
  'other-original',
  'the coached athlete display_name is unchanged'
);

-- ---------------------------------------------------------------------------
-- 5. Anonymous callers
-- ---------------------------------------------------------------------------

reset role;
set local role anon;
set local request.jwt.claims = '{"role":"anon"}';

select throws_ok(
  $$ update public.profiles set display_name = 'anonymous'
     where id = '00000000-0000-4000-9000-000000000001' $$,
  '42501', null,
  'an anonymous caller cannot update a display_name'
);
select throws_ok(
  $$ select * from public.profiles $$,
  '42501', null,
  'an anonymous caller still cannot read profiles'
);

-- ---------------------------------------------------------------------------
-- 6. A revoked user keeps exactly this one capability
-- ---------------------------------------------------------------------------
--
-- Decision 6 of the task packet: a revoked user may still edit their own
-- display name, but reaches no role area. The routing half is a client
-- concern; the database half is that the profile write still works while every
-- team-scoped read is already gone.

reset role;
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-9000-000000000004","role":"authenticated"}';

select lives_ok(
  $$ update public.profiles set display_name = 'synthetic-revoked-name'
     where id = '00000000-0000-4000-9000-000000000004' $$,
  'a revoked user may still update their own display_name'
);
select is(
  (select display_name from public.profiles
    where id = '00000000-0000-4000-9000-000000000004'),
  'synthetic-revoked-name',
  'the revoked user new display_name is stored'
);
select is(
  pg_temp.attempt_display_name_update(
    '00000000-0000-4000-9000-000000000002', 'revoked-hijack'),
  0,
  'a revoked user cannot edit another user display_name'
);
select is(
  (select count(*)::int from public.teams),
  0,
  'a revoked user still sees no team'
);
select is(
  (select count(*)::int from public.team_memberships where status = 'active'),
  0,
  'a revoked user still sees no active membership'
);

-- ---------------------------------------------------------------------------
-- 7. Positive control
-- ---------------------------------------------------------------------------

reset role;

select is(
  (select display_name from public.profiles
    where id = '00000000-0000-4000-9000-000000000002'),
  'other-original',
  'no refused write altered the other user display_name'
);
select is(
  (select count(*)::int from public.team_memberships),
  4,
  'every membership row survives the refused writes'
);
select is(
  (select count(*)::int from public.profiles),
  4,
  'no profile was inserted or deleted'
);

select * from finish();

rollback;
