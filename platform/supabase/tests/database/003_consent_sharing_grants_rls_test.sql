-- TASK-011: Consent and sharing grants authorization tests.
--
-- Every fixture in this file is synthetic, transaction-scoped, and rolled back.
-- No seed file, no persistent fixture, no service-role key, and no real user
-- data is involved. Test addresses use the reserved example.test domain.
--
-- No health value appears anywhere in this file. The table under test carries
-- consent metadata only: a team, a profile, a category name, and two
-- timestamps.
--
-- Fixture setup runs as the local database owner. Every authorization assertion
-- switches to the anon or authenticated role with synthetic JWT claims, so Row
-- Level Security, table privileges, and function privileges are actually
-- exercised.

begin;

-- pgTAP is created inside the transaction and rolled back with everything else,
-- so it is never shipped in a migration.
create extension if not exists pgtap with schema extensions;

set local search_path = public, extensions, pg_catalog;

select plan(154);

-- ---------------------------------------------------------------------------
-- Synthetic fixtures
-- ---------------------------------------------------------------------------
--
-- Users
--   coach-a            active coach   in Team A
--   athlete-a          active athlete in Team A   (main consent subject)
--   athlete-a2         active athlete in Team A   (memberships, never grants)
--   athlete-a-toggle   active athlete in Team A   (membership revoke/reactivate)
--   coach-a-later      active coach   in Team A   (revoked mid-test)
--   coach-a-revoked    revoked coach  in Team A
--   athlete-a-revoked  revoked athlete in Team A
--   coach-dual         active coach   in Team A and active athlete in Team B
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
  ('00000000-0000-4000-8000-00000000000e', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-b@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000f', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-dual@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000010', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-a-revoked@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000011', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-a-revoked@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000012', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-a-toggle@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000013', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-a-later@example.test', '{}'::jsonb);

insert into public.teams (id, name)
values
  ('00000000-0000-4000-8000-0000000000a1', 'Team A'),
  ('00000000-0000-4000-8000-0000000000b1', 'Team B');

insert into public.team_memberships (team_id, profile_id, role, status, revoked_at)
values
  -- Team A
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000a',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-000000000013',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000f',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000b',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000c',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-000000000012',
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

select has_table('public', 'sharing_grants', 'public.sharing_grants exists');

select col_is_pk('public', 'sharing_grants', 'id', 'sharing_grants.id is the primary key');

select col_type_is('public', 'sharing_grants', 'id', 'uuid', 'sharing_grants.id is uuid');
select col_type_is('public', 'sharing_grants', 'team_id', 'uuid', 'sharing_grants.team_id is uuid');
select col_type_is('public', 'sharing_grants', 'athlete_profile_id', 'uuid', 'sharing_grants.athlete_profile_id is uuid');
select col_type_is('public', 'sharing_grants', 'data_category', 'text', 'sharing_grants.data_category is text');
select col_type_is('public', 'sharing_grants', 'granted_at', 'timestamp with time zone', 'sharing_grants.granted_at is timestamptz');
select col_type_is('public', 'sharing_grants', 'revoked_at', 'timestamp with time zone', 'sharing_grants.revoked_at is timestamptz');

select col_not_null('public', 'sharing_grants', 'team_id', 'sharing_grants.team_id is not null');
select col_not_null('public', 'sharing_grants', 'athlete_profile_id', 'sharing_grants.athlete_profile_id is not null');
select col_not_null('public', 'sharing_grants', 'data_category', 'sharing_grants.data_category is not null');
select col_not_null('public', 'sharing_grants', 'granted_at', 'sharing_grants.granted_at is not null');
select col_is_null('public', 'sharing_grants', 'revoked_at', 'sharing_grants.revoked_at is nullable; null means active');

select col_has_default('public', 'sharing_grants', 'granted_at',
  'granted_at carries a database default');

-- Decision 4: activeness has exactly one representation. A status column would
-- be a second source of truth.
select hasnt_column('public', 'sharing_grants', 'status',
  'sharing_grants has no status column');

-- No health value may ever appear on this table. Pinning the exact column set
-- makes a future health column a test failure rather than a review miss.
select is(
  (select string_agg(column_name, ',' order by column_name)
     from information_schema.columns
    where table_schema = 'public' and table_name = 'sharing_grants'),
  'athlete_profile_id,data_category,granted_at,id,revoked_at,team_id',
  'sharing_grants carries consent metadata only and no health value column'
);

-- ---------------------------------------------------------------------------
-- 2. Constraints and indexes
-- ---------------------------------------------------------------------------

select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.sharing_grants'::regclass
      and conname = 'sharing_grants_data_category_valid'),
  1,
  'sharing_grants_data_category_valid constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.sharing_grants'::regclass
      and conname = 'sharing_grants_revoked_after_granted'),
  1,
  'sharing_grants_revoked_after_granted constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.sharing_grants'::regclass
      and conname = 'sharing_grants_membership_fkey'
      and contype = 'f'),
  1,
  'the composite membership foreign key exists'
);
select is(
  (select confrelid::regclass::text from pg_catalog.pg_constraint
    where conrelid = 'public.sharing_grants'::regclass
      and conname = 'sharing_grants_membership_fkey'),
  'team_memberships',
  'the foreign key ties team_id and athlete_profile_id to team_memberships'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint
    where conrelid = 'public.sharing_grants'::regclass
      and conname = 'sharing_grants_membership_fkey'),
  'c',
  'deleting the trusted membership cascades the grant away'
);
select is(
  (select confupdtype::text from pg_catalog.pg_constraint
    where conrelid = 'public.sharing_grants'::regclass
      and conname = 'sharing_grants_membership_fkey'),
  'a',
  'the foreign key refuses to move consent on a membership re-key'
);

select has_index('public', 'sharing_grants', 'sharing_grants_one_active_idx',
  'the partial unique active-grant index exists');
select has_index('public', 'sharing_grants', 'sharing_grants_athlete_profile_id_idx',
  'the athlete history lookup index exists');
select has_index('public', 'sharing_grants', 'sharing_grants_team_active_idx',
  'the active team lookup index exists');

select ok(
  (select i.indisunique and i.indpred is not null
     from pg_catalog.pg_index i
    where i.indexrelid = 'public.sharing_grants_one_active_idx'::regclass),
  'the active-grant index is unique and partial, so revoked history is unconstrained'
);

select has_trigger('public', 'sharing_grants', 'sharing_grants_enforce_timestamps',
  'the timestamp enforcement trigger exists on sharing_grants');
select has_trigger('public', 'team_memberships', 'team_memberships_revoke_sharing_grants',
  'the membership revocation trigger exists on team_memberships');

-- ---------------------------------------------------------------------------
-- 3. Constraint and trigger behaviour (positive controls, run as the owner)
-- ---------------------------------------------------------------------------
--
-- These probes use Team B and athlete-b and are deleted at the end of the
-- section, so the authorization sections below start from a known state.

select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000e', 'heart_rate') $$,
  '23514', null,
  'a category outside the three approved values is rejected'
);
select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000e', 'rpe') $$,
  '23514', null,
  'an RPE category is rejected; this table never carries health values'
);
select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000a1',
             '00000000-0000-4000-8000-00000000000e', 'check_in') $$,
  '23503', null,
  'a grant without a matching membership row is rejected'
);
select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000c1',
             '00000000-0000-4000-8000-00000000000e', 'check_in') $$,
  '23503', null,
  'a grant for a nonexistent team is rejected'
);

select lives_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000e', 'sleep_summary') $$,
  'a valid grant backed by an active membership is accepted'
);
select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000b1',
             '00000000-0000-4000-8000-00000000000e', 'sleep_summary') $$,
  '23505', null,
  'a second active row for the same athlete, team, and category is rejected'
);

-- Forged timestamps are overwritten by the trigger even for a trusted writer.
insert into public.sharing_grants
  (team_id, athlete_profile_id, data_category, granted_at, revoked_at)
values
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-00000000000e',
   'check_in', timestamptz '2000-01-01 00:00:00+00', timestamptz '2000-01-02 00:00:00+00');

select is(
  (select granted_at from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
      and data_category = 'check_in'),
  now(),
  'a supplied granted_at is overwritten with database time on insert'
);
select is(
  (select revoked_at from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
      and data_category = 'check_in'),
  null,
  'a supplied revoked_at is cleared on insert, so a row is never born revoked'
);

update public.sharing_grants
set granted_at = timestamptz '2000-01-01 00:00:00+00',
    data_category = 'workout_summary',
    team_id = '00000000-0000-4000-8000-0000000000a1'
where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
  and data_category = 'check_in';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
      and data_category = 'check_in'
      and team_id = '00000000-0000-4000-8000-0000000000b1'
      and granted_at = now()),
  1,
  'granted_at, data_category, and team_id are immutable after insert'
);

update public.sharing_grants
set revoked_at = timestamptz '2000-01-01 00:00:00+00'
where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
  and data_category = 'check_in';

select is(
  (select revoked_at from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
      and data_category = 'check_in'),
  now(),
  'a supplied revoked_at is overwritten with database time on revocation'
);

update public.sharing_grants
set revoked_at = null
where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
  and data_category = 'check_in';

select is(
  (select revoked_at from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'
      and data_category = 'check_in'),
  now(),
  'consent history is append-only: a revoked row cannot be un-revoked'
);

delete from public.sharing_grants
where athlete_profile_id = '00000000-0000-4000-8000-00000000000e';

select is(
  (select count(*)::int from public.sharing_grants),
  0,
  'the owner-level probe rows are cleared before the authorization sections'
);

-- ---------------------------------------------------------------------------
-- 4. Anonymous access
-- ---------------------------------------------------------------------------

set local role anon;

select throws_ok(
  $$ select * from public.sharing_grants $$,
  '42501', null,
  'anonymous cannot read sharing_grants'
);
select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in') $$,
  '42501', null,
  'anonymous cannot execute the grant RPC'
);
select throws_ok(
  $$ select public.revoke_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in') $$,
  '42501', null,
  'anonymous cannot execute the revoke RPC'
);
select throws_ok(
  $$ select private.can_current_user_read_shared_data(
       '00000000-0000-4000-8000-0000000000a1'::uuid,
       '00000000-0000-4000-8000-00000000000b'::uuid, 'check_in') $$,
  '42501', null,
  'anonymous cannot execute the authorization helper'
);

reset role;

-- ---------------------------------------------------------------------------
-- 5. Authenticated direct table writes are refused
-- ---------------------------------------------------------------------------
--
-- authenticated holds no write privilege at all, so every one of these fails
-- with 42501 at the privilege layer, which is strictly stronger than an RLS row
-- filter.

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000a1',
             '00000000-0000-4000-8000-00000000000b', 'check_in') $$,
  '42501', null,
  'an authenticated client cannot insert a grant directly'
);
select throws_ok(
  $$ insert into public.sharing_grants
       (team_id, athlete_profile_id, data_category, granted_at)
     values ('00000000-0000-4000-8000-0000000000a1',
             '00000000-0000-4000-8000-00000000000b', 'check_in',
             timestamptz '2000-01-01 00:00:00+00') $$,
  '42501', null,
  'an authenticated client cannot forge granted_at through a direct insert'
);
select throws_ok(
  $$ insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
     values ('00000000-0000-4000-8000-0000000000a1',
             '00000000-0000-4000-8000-00000000000c', 'check_in') $$,
  '42501', null,
  'an authenticated client cannot forge another athlete''s identity on insert'
);
select throws_ok(
  $$ update public.sharing_grants set revoked_at = null $$,
  '42501', null,
  'an authenticated client cannot update a grant directly'
);
select throws_ok(
  $$ delete from public.sharing_grants $$,
  '42501', null,
  'an authenticated client cannot delete a grant directly'
);

reset role;

-- ---------------------------------------------------------------------------
-- 6. Grant RPC
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')) is not null,
  'an active athlete can grant sharing and receives the new grant id'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and revoked_at is null),
  1,
  'the grant produced exactly one active row'
);
select is(
  (select athlete_profile_id from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000a1'
      and data_category = 'check_in'
      and revoked_at is null),
  '00000000-0000-4000-8000-00000000000b'::uuid,
  'the stored athlete identity comes from auth.uid(), not from the client'
);
select is(
  (select granted_at from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000a1'
      and data_category = 'check_in'
      and revoked_at is null),
  now(),
  'granted_at comes from the database'
);

-- Idempotence.
select is(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')),
  (select id from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000a1'
      and data_category = 'check_in'
      and revoked_at is null),
  'a repeated grant returns the existing active grant id'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'check_in'),
  1,
  'a repeated grant cannot create a second active row'
);

select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'heart_rate') $$,
  '22023', null,
  'the grant RPC rejects a category outside the three approved values'
);
select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, null) $$,
  '22023', null,
  'the grant RPC rejects a null category'
);
select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000b1'::uuid, 'check_in') $$,
  '42501', null,
  'an athlete cannot grant for a team where they hold no active athlete membership'
);
select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000c1'::uuid, 'check_in') $$,
  '42501', null,
  'an athlete cannot grant for a team that does not exist'
);

-- Consent history: grant, revoke, re-grant, revoke, repeat revoke.
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'sleep_summary')) is not null,
  'the athlete grants a second category'
);
select ok(
  (select public.revoke_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'sleep_summary')) is not null,
  'the athlete revokes that category and receives the revoked row id'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'sleep_summary'
      and revoked_at is not null),
  1,
  'revocation stamps revoked_at and retains the row'
);
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'sleep_summary')) is not null,
  'the athlete may grant the same category again'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'sleep_summary'),
  2,
  'a re-grant creates a new consent-history row rather than reviving the old one'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'sleep_summary'
      and revoked_at is null),
  1,
  'only one of the two history rows is active'
);
select ok(
  (select public.revoke_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'sleep_summary')) is not null,
  'the athlete revokes the re-granted category'
);
select is(
  (select public.revoke_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'sleep_summary')),
  null,
  'a repeated revoke is safe and reports that nothing was active'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'sleep_summary'),
  2,
  'a repeated revoke changes no history row'
);
select throws_ok(
  $$ select public.revoke_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'heart_rate') $$,
  '22023', null,
  'the revoke RPC rejects a category outside the three approved values'
);

reset role;

-- athlete-a-toggle grants a category that later sections revoke through
-- membership changes.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000012","role":"authenticated"}';

select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'workout_summary')) is not null,
  'a second Team A athlete grants a category'
);

reset role;

-- ---------------------------------------------------------------------------
-- 7. A coach cannot grant or revoke athlete sharing
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in') $$,
  '42501', null,
  'an active coach cannot grant sharing in their own team'
);
select is(
  (select public.revoke_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')),
  null,
  'an active coach revoking finds nothing, because the RPC only ever touches the caller''s own consent'
);

reset role;

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'check_in'
      and revoked_at is null),
  1,
  'the athlete''s grant is still active after a coach attempted to revoke it'
);

-- A user who is a coach in one team and an athlete in another is bound by the
-- role of the membership in the team named by the call.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000f","role":"authenticated"}';

select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in') $$,
  '42501', null,
  'a coach-role membership cannot grant athlete sharing even for a dual-role user'
);
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000b1'::uuid, 'check_in')) is not null,
  'the same dual-role user can grant in the team where they are an active athlete'
);

reset role;

-- A revoked athlete cannot create new consent.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000010","role":"authenticated"}';

select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in') $$,
  '42501', null,
  'a revoked athlete membership cannot grant sharing'
);

reset role;

-- ---------------------------------------------------------------------------
-- 8. Athlete visibility of their own consent history
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants),
  3,
  'the athlete reads their own complete consent history, active and revoked'
);
select is(
  (select count(*)::int from public.sharing_grants where revoked_at is null),
  1,
  'one of the athlete''s own rows is active'
);
select is(
  (select count(*)::int from public.sharing_grants where revoked_at is not null),
  2,
  'the athlete''s two revoked history rows remain readable to them'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id <> '00000000-0000-4000-8000-00000000000b'),
  0,
  'the athlete sees no row belonging to anyone else'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000c","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'another athlete in the same team cannot read the first athlete''s grants'
);
select is(
  (select count(*)::int from public.sharing_grants),
  0,
  'an athlete with no grants of their own sees nothing at all'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000e","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'an athlete in another team cannot read the first athlete''s grants'
);

reset role;

-- ---------------------------------------------------------------------------
-- 9. Coach visibility
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'an active coach sees the active grant of an active athlete in the same team'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'check_in'),
  1,
  'the visible row is the active check_in grant'
);
select is(
  (select count(*)::int from public.sharing_grants where revoked_at is not null),
  0,
  'a coach cannot see revoked consent history'
);
select is(
  (select count(*)::int from public.sharing_grants),
  2,
  'the coach sees exactly the two active Team A grants and nothing else'
);
select is(
  (select count(*)::int from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000b1'),
  0,
  'a Team A coach sees no Team B grant'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000d","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000a1'),
  0,
  'a Team B coach sees no Team A grant'
);
select is(
  (select count(*)::int from public.sharing_grants),
  1,
  'the Team B coach sees only the active Team B grant'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000011","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants),
  0,
  'a revoked coach sees nothing through coach access'
);

reset role;

-- A coach who is active now and revoked a moment later loses access on the next
-- query, with no re-login and no token change.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000013","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants),
  2,
  'a second active Team A coach sees the same two active grants'
);

reset role;

update public.team_memberships
set status = 'revoked', revoked_at = now()
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000013';

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000013","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants),
  0,
  'that coach loses all access on the very next query after revocation'
);

reset role;

-- Revoking a coach membership must not touch anyone's consent.
select is(
  (select count(*)::int from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000a1'
      and revoked_at is null),
  2,
  'revoking a coach membership revokes no athlete consent'
);

-- ---------------------------------------------------------------------------
-- 10. Authorization helper truth table
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select ok(
  private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'check_in'),
  'the helper is true only when an active grant and both active memberships match'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'workout_summary'),
  'the helper is false for the wrong category'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'sleep_summary'),
  'the helper is false for a category the athlete revoked'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000c', 'check_in'),
  'the helper is false when both memberships are active but no grant exists'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000b1',
    '00000000-0000-4000-8000-00000000000f', 'check_in'),
  'a Team A coach cannot reach a Team B athlete through the helper'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-000000000010', 'check_in'),
  'the helper is false for a revoked athlete membership'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000c","role":"authenticated"}';

select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'check_in'),
  'the helper is false for a caller who holds a grant-bearing team membership but no coach role'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000d","role":"authenticated"}';

select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'check_in'),
  'a coach of another team cannot reach the athlete through the helper'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000011","role":"authenticated"}';

select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'check_in'),
  'a revoked coach membership makes the helper false'
);

reset role;

-- ---------------------------------------------------------------------------
-- 11. Revocation takes effect on the coach's next query
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select ok(
  (select public.revoke_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')) is not null,
  'the athlete withdraws the check_in consent'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'the revoked grant disappears from coach access on the next query'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-00000000000b', 'check_in'),
  'the helper turns false for that athlete and category immediately'
);

reset role;

-- ---------------------------------------------------------------------------
-- 12. Membership revocation, reactivation, and role change
-- ---------------------------------------------------------------------------

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'
      and revoked_at is null),
  1,
  'the toggle athlete starts with one active grant'
);

update public.team_memberships
set status = 'revoked', revoked_at = now()
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000012';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'
      and revoked_at is null),
  0,
  'revoking the athlete membership revokes its active grants'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'
      and revoked_at = now()),
  1,
  'the membership trigger stamps revoked_at with database time and retains the row'
);

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'),
  0,
  'the coach loses access to that athlete immediately'
);
select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-000000000012', 'workout_summary'),
  'the helper is false for the revoked athlete membership'
);

reset role;

-- Reactivation must not revive anything.
update public.team_memberships
set status = 'active', revoked_at = null
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000012';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'
      and revoked_at is null),
  0,
  'reactivating the membership does not revive the old grant'
);
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'),
  1,
  'the old revoked grant is retained as history, not deleted'
);

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select ok(
  not private.can_current_user_read_shared_data(
    '00000000-0000-4000-8000-0000000000a1',
    '00000000-0000-4000-8000-000000000012', 'workout_summary'),
  'the helper stays false after reactivation until the athlete grants again'
);

reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000012","role":"authenticated"}';

select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'workout_summary')) is not null,
  'the reactivated athlete must grant again explicitly, and can'
);

reset role;

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'),
  2,
  'the explicit re-grant is a new consent-history row'
);

-- A membership that stops being an active athlete membership by role change is
-- treated the same as a revocation.
update public.team_memberships
set role = 'coach'
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000012';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'
      and revoked_at is null),
  0,
  'changing the role away from active athlete also revokes the active grants'
);

-- A trusted re-key of a membership row is refused while any grant references
-- it, rather than silently moving someone's consent.
select throws_ok(
  $$ update public.team_memberships
       set team_id = '00000000-0000-4000-8000-0000000000b1'
     where team_id = '00000000-0000-4000-8000-0000000000a1'
       and profile_id = '00000000-0000-4000-8000-00000000000b' $$,
  '23503', null,
  'a membership re-key is refused while grants reference it'
);

-- ---------------------------------------------------------------------------
-- 13. Row Level Security, policies, and table privileges
-- ---------------------------------------------------------------------------

select ok(
  (select relrowsecurity from pg_catalog.pg_class
    where oid = 'public.sharing_grants'::regclass),
  'RLS is enabled on public.sharing_grants'
);

select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'sharing_grants'),
  2,
  'sharing_grants carries exactly two policies'
);
select is(
  (select coalesce(string_agg(policyname || ':' || cmd, ', ' order by policyname), '')
     from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'sharing_grants'),
  'sharing_grants_select_active_for_coach:SELECT, sharing_grants_select_own_history:SELECT',
  'both policies are SELECT only; no write policy exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'sharing_grants'
      and cmd <> 'SELECT'),
  0,
  'no INSERT, UPDATE, or DELETE policy exists on sharing_grants'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'sharing_grants'
      and 'anon' = any (roles)),
  0,
  'no sharing_grants policy targets the anon role'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'sharing_grants'
      and 'public' = any (roles)),
  0,
  'no sharing_grants policy targets every role'
);

select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'sharing_grants'
      and grantee = 'anon'),
  0,
  'anon holds no table privilege on sharing_grants'
);
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'sharing_grants'
      and grantee = 'authenticated'
      and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')),
  0,
  'authenticated holds no write privilege on sharing_grants'
);
select ok(
  has_table_privilege('authenticated', 'public.sharing_grants', 'select'),
  'authenticated can select from sharing_grants'
);
select ok(
  not has_table_privilege('anon', 'public.sharing_grants', 'select'),
  'anon cannot select from sharing_grants'
);
select ok(
  not has_table_privilege('authenticated', 'public.sharing_grants', 'insert'),
  'authenticated cannot insert into sharing_grants'
);
select ok(
  not has_table_privilege('authenticated', 'public.sharing_grants', 'update'),
  'authenticated cannot update sharing_grants'
);
select ok(
  not has_table_privilege('authenticated', 'public.sharing_grants', 'delete'),
  'authenticated cannot delete from sharing_grants'
);

-- The TASK-008 tables are untouched by this migration.
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('profiles', 'teams', 'team_memberships')
      and grantee = 'anon'),
  0,
  'anon still holds no privilege on the TASK-008 tables'
);
select is(
  (select coalesce(string_agg(distinct privilege_type, ',' order by privilege_type), '')
     from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('teams', 'team_memberships')
      and grantee = 'authenticated'),
  'SELECT',
  'the TASK-008 membership and team tables remain read-only for authenticated'
);

-- ---------------------------------------------------------------------------
-- 14. Function catalog and privileges
-- ---------------------------------------------------------------------------

select has_function('private', 'can_current_user_read_shared_data',
  array['uuid', 'uuid', 'text'], 'the authorization helper exists in the private schema');
select has_function('public', 'grant_team_data_sharing',
  array['uuid', 'text'], 'the grant RPC exists');
select has_function('public', 'revoke_team_data_sharing',
  array['uuid', 'text'], 'the revoke RPC exists');

select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('public', 'graphql_public')
      and p.proname = 'can_current_user_read_shared_data'),
  0,
  'the authorization helper is not defined in an exposed schema'
);

-- The RPC signatures are the enforcement point for decision 6: there is no
-- parameter through which a client could name another athlete or a timestamp.
select is(
  (select pg_catalog.pg_get_function_arguments(p.oid)
     from pg_catalog.pg_proc p
     join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'grant_team_data_sharing'),
  'p_team_id uuid, p_data_category text',
  'the grant RPC accepts no athlete identifier and no timestamp'
);
select is(
  (select pg_catalog.pg_get_function_arguments(p.oid)
     from pg_catalog.pg_proc p
     join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = 'revoke_team_data_sharing'),
  'p_team_id uuid, p_data_category text',
  'the revoke RPC accepts no athlete identifier and no timestamp'
);
select throws_ok(
  $$ select public.grant_team_data_sharing(
       '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in',
       '00000000-0000-4000-8000-00000000000c'::uuid) $$,
  '42883', null,
  'no overload accepts an athlete identifier, so identity cannot be forged through the RPC'
);

select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where p.prosecdef
      and ((n.nspname = 'private' and p.proname in (
              'can_current_user_read_shared_data',
              'enforce_sharing_grant_timestamps',
              'revoke_sharing_grants_on_membership_change'))
        or (n.nspname = 'public' and p.proname in (
              'grant_team_data_sharing', 'revoke_team_data_sharing')))),
  5,
  'all five TASK-011 functions are SECURITY DEFINER'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where exists (
        select 1 from unnest(p.proconfig) as cfg
        -- PostgreSQL stores an empty search_path canonically as search_path=""
        where cfg in ('search_path=""', 'search_path='))
      and ((n.nspname = 'private' and p.proname in (
              'can_current_user_read_shared_data',
              'enforce_sharing_grant_timestamps',
              'revoke_sharing_grants_on_membership_change'))
        or (n.nspname = 'public' and p.proname in (
              'grant_team_data_sharing', 'revoke_team_data_sharing')))),
  5,
  'all five TASK-011 functions pin an empty search_path'
);

select ok(
  not has_function_privilege('anon',
    'private.can_current_user_read_shared_data(uuid, uuid, text)', 'execute'),
  'anon cannot execute the authorization helper'
);
select ok(
  has_function_privilege('authenticated',
    'private.can_current_user_read_shared_data(uuid, uuid, text)', 'execute'),
  'authenticated can execute the helper, which the coach policy requires'
);
select ok(
  not has_function_privilege('anon',
    'public.grant_team_data_sharing(uuid, text)', 'execute'),
  'anon cannot execute the grant RPC'
);
select ok(
  not has_function_privilege('anon',
    'public.revoke_team_data_sharing(uuid, text)', 'execute'),
  'anon cannot execute the revoke RPC'
);
select ok(
  has_function_privilege('authenticated',
    'public.grant_team_data_sharing(uuid, text)', 'execute'),
  'authenticated can execute the grant RPC'
);
select ok(
  has_function_privilege('authenticated',
    'public.revoke_team_data_sharing(uuid, text)', 'execute'),
  'authenticated can execute the revoke RPC'
);
select ok(
  not has_function_privilege('authenticated',
    'private.enforce_sharing_grant_timestamps()', 'execute'),
  'authenticated cannot execute the timestamp trigger function'
);
select ok(
  not has_function_privilege('authenticated',
    'private.revoke_sharing_grants_on_membership_change()', 'execute'),
  'authenticated cannot execute the membership revocation trigger function'
);
select ok(
  not has_schema_privilege('anon', 'private', 'usage'),
  'anon still holds no usage on the private schema'
);

-- ---------------------------------------------------------------------------
-- 15. Trusted cascade deletion leaves no usable orphan grant
-- ---------------------------------------------------------------------------

insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
values ('00000000-0000-4000-8000-0000000000a1',
        '00000000-0000-4000-8000-00000000000c', 'check_in');

delete from public.team_memberships
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-00000000000c';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'deleting the membership row cascades its grants away'
);

delete from auth.users where id = '00000000-0000-4000-8000-00000000000b';

select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'deleting the auth user cascades through profile and membership to every grant, including history'
);

delete from public.teams where id = '00000000-0000-4000-8000-0000000000b1';

select is(
  (select count(*)::int from public.sharing_grants
    where team_id = '00000000-0000-4000-8000-0000000000b1'),
  0,
  'deleting the team cascades its grants away'
);

select * from finish();

rollback;
