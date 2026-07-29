-- TASK-012: Daily check-in authorization tests.
--
-- Every fixture in this file is synthetic, transaction-scoped, and rolled back.
-- No seed file, no persistent fixture, no service-role key, and no real user
-- data is involved. Test addresses use the reserved example.test domain.
--
-- This is the first table in the product that stores protected health data, so
-- this file is deliberately written not to disclose any. No assertion
-- description names an RPE, an overall feeling, or a pain status, and no
-- assertion echoes one: every check compares a row count, a constant sentinel,
-- a column name, an error code, a boolean, or a snapshot join. Synthetic
-- fixture values appear only inside statement text, never in a value an
-- assertion returns. A failure therefore reports which authorization rule
-- broke, never a measurement and never a timestamp.
--
-- The rule that matters is about *failure* output, not passing output. pgTAP
-- prints the have/got value when an assertion fails, so any assertion that
-- returns a captured database error message would republish that message into
-- the test log at exactly the moment a disclosure regression occurred — the
-- test meant to catch the leak would become the leak. Captured MESSAGE_TEXT,
-- DETAIL, and HINT are therefore never returned to an assertion; they are
-- compared inside the query and only a count crosses the boundary. A captured
-- SQLSTATE is returned directly, because it is a five-character code from a
-- closed enumeration and cannot carry a value, an identifier, or a date.
--
-- Fixture setup runs as the local database owner. Every authorization assertion
-- switches to the anon or authenticated role with synthetic JWT claims, so Row
-- Level Security, table privileges, and column privileges are actually
-- exercised.

begin;

-- pgTAP is created inside the transaction and rolled back with everything else,
-- so it is never shipped in a migration.
create extension if not exists pgtap with schema extensions;

set local search_path = public, extensions, pg_catalog;

select plan(190);

-- ---------------------------------------------------------------------------
-- Failure-output-safe execution probe
-- ---------------------------------------------------------------------------
--
-- pgTAP's throws_ok() and lives_ok() print the caught database error — code,
-- message, and context — when they fail. On a protected-health table that makes
-- the assertion a disclosure path at exactly the moment a regression occurs:
-- the test written to catch a leak becomes the leak. This probe replaces both.
--
-- It runs the statement under the caller's current role and JWT claims
-- (SECURITY INVOKER, no pinned search_path), so privileges, RLS, and column
-- grants are exercised exactly as before. On success it returns a fixed
-- sentinel and the statement's effects persist, because a plpgsql exception
-- block only rolls back its subtransaction when an exception is actually
-- raised. On failure it returns the five-character SQLSTATE and nothing else:
-- SQLERRM, DETAIL, HINT, CONTEXT, and the statement text are never read, never
-- returned, and never raised onward.
--
-- The function lives in pg_temp, so it adds no schema surface, no RPC, and
-- disappears with the transaction.

create function pg_temp.probe_state(p_sql text)
returns text
language plpgsql
as $probe_state$
begin
  execute p_sql;
  return 'ok';
exception when others then
  return sqlstate;
end;
$probe_state$;

-- anon and authenticated must be able to call the probe, and "pg_temp" is a
-- search-path alias that GRANT does not resolve, so the session's real temp
-- schema name is looked up and granted explicitly.
do $grant_probe$
declare
  v_schema text := (select nspname from pg_catalog.pg_namespace
                     where oid = pg_catalog.pg_my_temp_schema());
begin
  execute format('grant usage on schema %I to anon, authenticated', v_schema);
  execute format(
    'grant execute on function %I.probe_state(text) to anon, authenticated',
    v_schema);
end;
$grant_probe$;

-- ---------------------------------------------------------------------------
-- Synthetic fixtures
-- ---------------------------------------------------------------------------
--
-- Users
--   coach-a          active coach   in Team A   (also owns one check-in)
--   coach-t          active coach   in Team A   (revoked mid-test)
--   coach-b          active coach   in Team B
--   athlete-a        active athlete in Team A   (grants check_in; main subject)
--   athlete-b        active athlete in Team A   (never grants anything)
--   athlete-w        active athlete in Team A   (grants the two wrong categories)
--   athlete-x        active athlete in Team A and Team B (grants check_in to
--                                                         Team B only)
--   athlete-t        active athlete in Team A   (membership revoked mid-test)

insert into auth.users (id, instance_id, aud, role, email, raw_user_meta_data)
values
  ('00000000-0000-4000-8000-00000000000a', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-a@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000b', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-a@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000c', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-b@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000d', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-b@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000e', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-w@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-00000000000f', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-x@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000012', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'athlete-t@example.test', '{}'::jsonb),
  ('00000000-0000-4000-8000-000000000013', '00000000-0000-0000-0000-000000000000',
   'authenticated', 'authenticated', 'coach-t@example.test', '{}'::jsonb);

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
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000b',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000c',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000e',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-00000000000f',
   'athlete', 'active', null),
  ('00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-000000000012',
   'athlete', 'active', null),
  -- Team B
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-00000000000d',
   'coach', 'active', null),
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-00000000000f',
   'athlete', 'active', null);

-- ---------------------------------------------------------------------------
-- 1. Structure
-- ---------------------------------------------------------------------------

select has_table('public', 'daily_check_ins', 'public.daily_check_ins exists');

select col_is_pk('public', 'daily_check_ins', 'id',
  'daily_check_ins.id is the primary key');

select col_type_is('public', 'daily_check_ins', 'id', 'uuid',
  'id is uuid');
select col_type_is('public', 'daily_check_ins', 'athlete_profile_id', 'uuid',
  'athlete_profile_id is uuid');
select col_type_is('public', 'daily_check_ins', 'check_in_date', 'date',
  'check_in_date is a date, so a check-in belongs to a calendar day rather than an instant');
select col_type_is('public', 'daily_check_ins', 'rpe', 'smallint',
  'rpe is smallint');
select col_type_is('public', 'daily_check_ins', 'overall_feeling', 'smallint',
  'overall_feeling is smallint');
select col_type_is('public', 'daily_check_ins', 'pain_status', 'text',
  'pain_status is text');
select col_type_is('public', 'daily_check_ins', 'created_at',
  'timestamp with time zone', 'created_at is timestamptz');
select col_type_is('public', 'daily_check_ins', 'updated_at',
  'timestamp with time zone', 'updated_at is timestamptz');

select col_not_null('public', 'daily_check_ins', 'athlete_profile_id',
  'athlete_profile_id is not null');
select col_not_null('public', 'daily_check_ins', 'check_in_date',
  'check_in_date is not null');
select col_not_null('public', 'daily_check_ins', 'rpe',
  'rpe is required');
select col_not_null('public', 'daily_check_ins', 'overall_feeling',
  'overall_feeling is required');
select col_not_null('public', 'daily_check_ins', 'pain_status',
  'pain_status is required');
select col_not_null('public', 'daily_check_ins', 'created_at',
  'created_at is not null');
select col_not_null('public', 'daily_check_ins', 'updated_at',
  'updated_at is not null');

select col_has_default('public', 'daily_check_ins', 'id',
  'id carries a database default, so the client never supplies one');
select col_has_default('public', 'daily_check_ins', 'created_at',
  'created_at carries a database default');
select col_has_default('public', 'daily_check_ins', 'updated_at',
  'updated_at carries a database default');

-- Decision 1: a check-in is personal athlete data, not team-owned data.
select hasnt_column('public', 'daily_check_ins', 'team_id',
  'daily_check_ins has no team_id; sharing is per team through sharing_grants');

-- Decision 3: the three structured health fields and nothing else. Pinning the
-- exact column set makes a future note, body-location, diagnosis, or attachment
-- column a test failure rather than a review miss.
select is(
  (select string_agg(column_name, ',' order by column_name)
     from information_schema.columns
    where table_schema = 'public' and table_name = 'daily_check_ins'),
  'athlete_profile_id,check_in_date,created_at,id,overall_feeling,pain_status,rpe,updated_at',
  'daily_check_ins carries exactly the eight approved columns'
);
select is(
  (select coalesce(string_agg(column_name, ',' order by column_name), '')
     from information_schema.columns
    where table_schema = 'public' and table_name = 'daily_check_ins'
      and data_type in ('text', 'character varying', 'character', 'json', 'jsonb', 'bytea')),
  'pain_status',
  'the only free-form-capable column is pain_status, and a check constraint pins it to two values'
);

-- ---------------------------------------------------------------------------
-- 2. Constraints, indexes, and trigger
-- ---------------------------------------------------------------------------

select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.daily_check_ins'::regclass
      and conname = 'daily_check_ins_rpe_valid'
      and contype = 'c'),
  1,
  'the rpe range check constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.daily_check_ins'::regclass
      and conname = 'daily_check_ins_overall_feeling_valid'
      and contype = 'c'),
  1,
  'the overall_feeling range check constraint exists'
);
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.daily_check_ins'::regclass
      and conname = 'daily_check_ins_pain_status_valid'
      and contype = 'c'),
  1,
  'the pain_status check constraint exists'
);

-- Decision 2 is a constraint, not an application convention.
select is(
  (select count(*)::int from pg_catalog.pg_constraint
    where conrelid = 'public.daily_check_ins'::regclass
      and conname = 'daily_check_ins_athlete_date_unique'
      and contype = 'u'),
  1,
  'the one-check-in-per-athlete-per-date unique constraint exists'
);
select is(
  (select string_agg(a.attname, ',' order by a.attname)
     from pg_catalog.pg_constraint as c
     cross join unnest(c.conkey) as k(attnum)
     join pg_catalog.pg_attribute as a
       on a.attrelid = c.conrelid and a.attnum = k.attnum
    where c.conrelid = 'public.daily_check_ins'::regclass
      and c.conname = 'daily_check_ins_athlete_date_unique'),
  'athlete_profile_id,check_in_date',
  'the unique constraint covers exactly the athlete and the calendar date'
);

select is(
  (select confrelid::regclass::text from pg_catalog.pg_constraint
    where conrelid = 'public.daily_check_ins'::regclass
      and contype = 'f'),
  'profiles',
  'athlete_profile_id references public.profiles'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint
    where conrelid = 'public.daily_check_ins'::regclass
      and contype = 'f'),
  'c',
  'deleting the profile cascades the check-ins away, leaving no orphan health row'
);

-- Index justification: exactly one index exists, the unique constraint's, whose
-- leading column serves both the own-read and the coach-read query paths. A
-- speculative extra index on a protected-health table would be cost without a
-- query path.
select is(
  (select string_agg(i.indexrelid::regclass::text, ',' order by i.indexrelid::regclass::text)
     from pg_catalog.pg_index as i
    where i.indrelid = 'public.daily_check_ins'::regclass),
  'daily_check_ins_athlete_date_unique,daily_check_ins_pkey',
  'only the primary key and the athlete-and-date unique index exist; no unjustified index was added'
);

select has_trigger('public', 'daily_check_ins', 'daily_check_ins_enforce_columns',
  'the column enforcement trigger exists on daily_check_ins');

-- ---------------------------------------------------------------------------
-- 3. Constraint and trigger behaviour (positive controls, run as the owner)
-- ---------------------------------------------------------------------------
--
-- These probes use athlete-b and are removed at the end of the section, so the
-- authorization sections below start from a known state. The out-of-range
-- literals here are synthetic boundary probes, not anybody's measurements.
--
-- Every invalid value is refused with 22023, the sanitized error the trigger
-- raises, rather than with the native 23514 of the CHECK constraint behind it.
-- That is the point of the trigger: a native constraint failure would carry a
-- 'Failing row contains (...)' DETAIL holding the whole protected-health row.
-- The constraints are still present and still enforce the same rules; section
-- 3b proves the error a client actually receives discloses nothing.

select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             -1, 3, 'none') $$),
  '22023',
  'an rpe below the allowed range is rejected'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             11, 3, 'none') $$),
  '22023',
  'an rpe above the allowed range is rejected'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 0, 'none') $$),
  '22023',
  'an overall_feeling below the allowed range is rejected'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 6, 'none') $$),
  '22023',
  'an overall_feeling above the allowed range is rejected'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 3, 'mild') $$),
  '22023',
  'a pain_status outside the two approved values is rejected'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 3, '') $$),
  '22023',
  'an empty pain_status is rejected, so there is no free-text escape hatch'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 3, 'NONE') $$),
  '22023',
  'pain_status is case-sensitive, so only the two exact approved values pass'
);

select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             0, 1, 'present') $$),
  'ok',
  'a row at the lower bound of both scales is accepted'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             10, 5, 'none') $$),
  '23505',
  'a second row for the same athlete and the same calendar date is rejected'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-21',
             10, 5, 'none') $$),
  'ok',
  'the same athlete may check in on a different calendar date'
);

-- Forged timestamps are overwritten by the trigger even for a trusted writer.
insert into public.daily_check_ins
  (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status,
   created_at, updated_at)
values
  ('00000000-0000-4000-8000-00000000000c', date '2026-07-22', 5, 3, 'none',
   timestamptz '2000-01-01 00:00:00+00', timestamptz '2000-01-02 00:00:00+00');

-- Counted, not compared: a direct scalar comparison would print both the stored
-- and the expected timestamp when it failed (Round 5, L1). The equality is
-- evaluated inside the query and only the matching row count leaves it.
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and check_in_date = date '2026-07-22'
      and created_at = now()),
  1,
  'a supplied created_at is overwritten with database time on insert'
);
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and check_in_date = date '2026-07-22'
      and updated_at = now()),
  1,
  'a supplied updated_at is overwritten with database time on insert'
);

-- A trusted update attempting to move the owner, the date, the identity, and
-- the creation time is silently corrected by the trigger.
update public.daily_check_ins
set id = '00000000-0000-4000-8000-0000000000ff',
    athlete_profile_id = '00000000-0000-4000-8000-00000000000b',
    check_in_date = date '2000-01-01',
    created_at = timestamptz '2000-01-01 00:00:00+00',
    updated_at = timestamptz '2000-01-01 00:00:00+00'
where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
  and check_in_date = date '2026-07-22';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and check_in_date = date '2026-07-22'
      and created_at = now()),
  1,
  'the owner, the calendar date, and created_at are immutable after insert'
);
select is(
  (select count(*)::int from public.daily_check_ins
    where id = '00000000-0000-4000-8000-0000000000ff'),
  0,
  'the row id is immutable after insert'
);
-- A forged updated_at is discarded, and the replacement is strictly later than
-- the value the row already held. created_at is the row's insert-time
-- updated_at, so comparing against it proves advancement without capturing or
-- printing either timestamp.
select ok(
  (select updated_at > created_at from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and check_in_date = date '2026-07-22'),
  'a supplied updated_at is discarded and replaced with a strictly later database time'
);
select ok(
  (select updated_at > now() from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and check_in_date = date '2026-07-22'),
  'the replacement does not come from transaction-stable now(), so it advances inside one transaction'
);

-- A second update in the same transaction must advance the timestamp again.
-- Under transaction-stable now() both updates would stamp the same instant.
create temporary table trusted_update_clock as
select updated_at
from public.daily_check_ins
where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
  and check_in_date = date '2026-07-22';

update public.daily_check_ins
set rpe = 7
where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
  and check_in_date = date '2026-07-22';

select ok(
  (select c.updated_at > k.updated_at
     from public.daily_check_ins as c
     cross join trusted_update_clock as k
    where c.athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and c.check_in_date = date '2026-07-22'),
  'a second update inside the same transaction advances updated_at again'
);
select ok(
  (select c.created_at = now()
     from public.daily_check_ins as c
    where c.athlete_profile_id = '00000000-0000-4000-8000-00000000000c'
      and c.check_in_date = date '2026-07-22'),
  'created_at is unaffected by the advancing updated_at'
);

-- ---------------------------------------------------------------------------
-- 3b. A rejected write discloses nothing
-- ---------------------------------------------------------------------------
--
-- The concern is not that an invalid write is refused; it is what the refusal
-- says. A native NOT NULL or CHECK failure carries a DETAIL naming the failing
-- column and reproducing the whole row, and that string reaches PostgREST error
-- objects and logs. These probes capture the four diagnostic fields a client or
-- a log line can actually observe and assert that all of them are inert.
--
-- The helper lives in pg_temp, so it adds no schema surface and no RPC, and it
-- disappears with the transaction.

create function pg_temp.probe_error(p_sql text)
returns table (err_state text, err_message text, err_detail text, err_hint text)
language plpgsql
as $probe$
begin
  execute p_sql;
  err_state := '<no error>';
  err_message := '<no error>';
  err_detail := '';
  err_hint := '';
  return next;
exception when others then
  get stacked diagnostics
    err_state = returned_sqlstate,
    err_message = message_text,
    err_detail = pg_exception_detail,
    err_hint = pg_exception_hint;
  return next;
end;
$probe$;

create temporary table rejection_probe as
select 'out of range' as probe, p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-28',
             11, 3, 'none') $$) as p
union all
select 'unapproved pain status', p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-28',
             5, 3, 'mild') $$) as p
union all
select 'null required health field', p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-28',
             null, 3, 'none') $$) as p
union all
select 'null required identity field', p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values (null, date '2026-07-28', 5, 3, 'none') $$) as p
union all
select 'null required date field', p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', null, 5, 3, 'none') $$) as p
union all
select 'invalid update', p.*
from pg_temp.probe_error(
  $$ update public.daily_check_ins set rpe = 11
      where athlete_profile_id = '00000000-0000-4000-8000-00000000000c' $$) as p;

select is(
  (select count(*)::int from rejection_probe),
  6,
  'six rejection paths were probed as the owner, covering range, status, and three required fields'
);
select is(
  (select count(distinct err_state)::int from rejection_probe),
  1,
  'every rejection path returns the same SQLSTATE, so the error cannot be used to probe which field was wrong'
);
select is(
  (select min(err_state) from rejection_probe),
  '22023',
  'that SQLSTATE is the documented sanitized code'
);
select is(
  (select count(distinct err_message)::int from rejection_probe),
  1,
  'every rejection path returns the same message text'
);
-- Counted rather than compared. pgTAP prints the have/got value when is()
-- fails, so returning a captured message here would make the very test that
-- detects a disclosure republish it into the test log. The comparison happens
-- inside the query and only the row count crosses the boundary.
select is(
  (select count(*)::int from rejection_probe
    where err_message is distinct from 'daily check-in rejected: invalid input'),
  0,
  'no rejection message differs from the fixed generic one'
);
select is(
  (select count(*)::int from rejection_probe where coalesce(err_detail, '') <> ''),
  0,
  'no rejection carries a DETAIL'
);
select is(
  (select count(*)::int from rejection_probe where coalesce(err_hint, '') <> ''),
  0,
  'no rejection carries a HINT'
);
select is(
  (select count(*)::int from rejection_probe
    where err_message like '%Failing row%'
       or err_message like '%daily_check_ins_%_valid%'
       or err_message like '%rpe%'
       or err_message like '%overall_feeling%'
       or err_message like '%pain_status%'
       or err_message like '%00000000-0000-4000-8000%'
       or err_message like '%2026-07-28%'),
  0,
  'no rejection message names a column, a constraint, a row representation, an identifier, or a date'
);

-- The probes above run as the database owner, which proves the trigger raises a
-- sanitized error but not that a real client observes one. A client reaches the
-- table through column privileges and RLS as well, so these two probes repeat
-- the exercise as role authenticated with synthetic JWT claims, writing the
-- caller's own row. They also cover the two required fields the owner matrix
-- above does not: a null overall_feeling and a null pain_status. Removing
-- either trigger guard would let PostgreSQL's native NOT NULL error through,
-- and its DETAIL reproduces the whole protected-health row.
--
-- The capture table is created and read by the owner and only written by
-- authenticated, so no assertion depends on a temp table the client owns.

create temporary table client_rejection_probe (
  probe       text,
  err_state   text,
  err_message text,
  err_detail  text,
  err_hint    text
);
grant insert on client_rejection_probe to authenticated;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

-- Without this the probes below would return an identical sanitized result if
-- the role switch silently failed, and the section would prove nothing new.
select is(
  current_user::text,
  'authenticated',
  'the rejection probes below execute as the authenticated client role, not as the database owner'
);

insert into client_rejection_probe
select 'null overall feeling', p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-28',
             5, null, 'none') $$) as p;

insert into client_rejection_probe
select 'null pain status', p.*
from pg_temp.probe_error(
  $$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-28',
             5, 3, null) $$) as p;

reset request.jwt.claims;
reset role;

select is(
  (select count(*)::int from client_rejection_probe),
  2,
  'both remaining required fields were probed as an authenticated client writing their own row'
);
select is(
  (select count(distinct err_state)::int from client_rejection_probe),
  1,
  'an authenticated client sees one SQLSTATE for both, so the error cannot be used to probe which field was wrong'
);
select is(
  (select min(err_state) from client_rejection_probe),
  '22023',
  'the SQLSTATE an authenticated client sees is the documented sanitized code, not a native NOT NULL failure'
);
select is(
  (select count(distinct err_message)::int from client_rejection_probe),
  1,
  'an authenticated client sees the same message text for both'
);
-- Counted, not compared, for the same reason as the owner matrix above.
select is(
  (select count(*)::int from client_rejection_probe
    where err_message is distinct from 'daily check-in rejected: invalid input'),
  0,
  'no rejection message an authenticated client sees differs from the fixed generic one'
);
select is(
  (select count(*)::int from client_rejection_probe
    where coalesce(err_detail, '') <> ''),
  0,
  'no rejection an authenticated client sees carries a DETAIL'
);
select is(
  (select count(*)::int from client_rejection_probe
    where coalesce(err_hint, '') <> ''),
  0,
  'no rejection an authenticated client sees carries a HINT'
);
select is(
  (select count(*)::int from client_rejection_probe
    where err_message like '%Failing row%'
       or err_message like '%daily_check_ins%'
       or err_message like '%overall_feeling%'
       or err_message like '%pain_status%'
       or err_message like '%null value%'
       or err_message like '%00000000-0000-4000-8000%'
       or err_message like '%2026-07-28%'),
  0,
  'no rejection an authenticated client sees names a column, a constraint, a row representation, an identifier, or a date'
);

delete from public.daily_check_ins
where athlete_profile_id = '00000000-0000-4000-8000-00000000000c';

select is(
  (select count(*)::int from public.daily_check_ins),
  0,
  'every owner-level and client-level probe row is cleared before the authorization sections'
);

-- ---------------------------------------------------------------------------
-- 4. Anonymous access
-- ---------------------------------------------------------------------------
--
-- anon holds no privilege at all, so every statement fails at the privilege
-- layer with 42501, which is strictly stronger than an RLS row filter.

set local role anon;

select is(
  pg_temp.probe_state($$ select * from public.daily_check_ins $$),
  '42501',
  'anonymous cannot read daily_check_ins'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-20',
             5, 3, 'none') $$),
  '42501',
  'anonymous cannot insert a check-in'
);
select is(
  pg_temp.probe_state($$ update public.daily_check_ins set rpe = rpe $$),
  '42501',
  'anonymous cannot update a check-in'
);
select is(
  pg_temp.probe_state($$ delete from public.daily_check_ins $$),
  '42501',
  'anonymous cannot delete a check-in'
);
select is(
  pg_temp.probe_state($$ select private.can_current_user_read_check_in(
       '00000000-0000-4000-8000-00000000000b'::uuid) $$),
  '42501',
  'anonymous cannot execute the check-in read helper'
);

reset role;

-- ---------------------------------------------------------------------------
-- 5. The data subject owns their row
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-20',
             5, 3, 'none') $$),
  'ok',
  'an authenticated athlete inserts their own check-in'
);
select is(
  (select count(*)::int from public.daily_check_ins),
  1,
  'the athlete reads back exactly their own one row'
);
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and created_at = now()
      and updated_at = now()),
  1,
  'both timestamps came from the database on a client insert'
);

-- Column privileges, not merely trigger correction: the client cannot even name
-- the database-controlled columns.
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (id, athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-0000000000fe',
             '00000000-0000-4000-8000-00000000000b', date '2026-07-25',
             5, 3, 'none') $$),
  '42501',
  'a client insert cannot name the id column'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status,
        created_at)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-25',
             5, 3, 'none', timestamptz '2000-01-01 00:00:00+00') $$),
  '42501',
  'a client insert cannot name the created_at column'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status,
        updated_at)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-25',
             5, 3, 'none', timestamptz '2000-01-01 00:00:00+00') $$),
  '42501',
  'a client insert cannot name the updated_at column'
);

select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 3, 'none') $$),
  '42501',
  'a client cannot insert a check-in for another profile'
);
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-20',
             8, 4, 'present') $$),
  '23505',
  'a client cannot create a second check-in for the same calendar date'
);

-- Decision 5: the data subject may change exactly the three health fields.
--
-- Round 2, high finding. A bare "the statement succeeded" check cannot
-- distinguish a successful update from one that matched no row, because RLS
-- filters rather than errors, so an update that reaches nothing still
-- succeeds — and that is equally true of the probe's 'ok' sentinel as it was
-- of the lives_ok() this file used to call. Every update path in this file
-- therefore counts the rows the statement actually affected. RETURNING yields a
-- constant sentinel, never a column, so no protected value reaches the output.
--
-- The attempted values differ from the stored ones: the fixture inserted one
-- triple and this update writes a different one, so the assertions below fail
-- if the write silently reached zero rows.
--
-- The clock snapshot is taken as the table owner, because a temporary table is
-- not readable by the authenticated role.
reset role;
create temporary table owner_update_clock as
select updated_at
from public.daily_check_ins
where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
  and check_in_date = date '2026-07-20';
set local role authenticated;

with owner_update as (
  update public.daily_check_ins
     set rpe = 8, overall_feeling = 4, pain_status = 'present'
   where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
  returning 1 as touched
)
select is(
  (select count(*)::int from owner_update),
  1,
  'the data subject''s own update affects exactly one row'
);

reset role;

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and check_in_date = date '2026-07-20'
      and rpe = 8
      and overall_feeling = 4
      and pain_status = 'present'),
  1,
  'the post-image holds the attempted values, so the update landed on the row'
);
select ok(
  (select c.updated_at > k.updated_at
     from public.daily_check_ins as c
     cross join owner_update_clock as k
    where c.athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and c.check_in_date = date '2026-07-20'),
  'the update advanced updated_at strictly past the value captured before it'
);
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and check_in_date = date '2026-07-20'
      and created_at = now()),
  1,
  'the updated row keeps its owner and date, and created_at is untouched'
);

set local role authenticated;

select is(
  pg_temp.probe_state($$ update public.daily_check_ins
        set athlete_profile_id = '00000000-0000-4000-8000-00000000000c' $$),
  '42501',
  'a client update cannot name the athlete_profile_id column'
);
select is(
  pg_temp.probe_state($$ update public.daily_check_ins set check_in_date = date '2026-07-01' $$),
  '42501',
  'a client update cannot name the check_in_date column'
);
select is(
  pg_temp.probe_state($$ update public.daily_check_ins
        set id = '00000000-0000-4000-8000-0000000000fd' $$),
  '42501',
  'a client update cannot name the id column'
);
select is(
  pg_temp.probe_state($$ update public.daily_check_ins
        set created_at = timestamptz '2000-01-01 00:00:00+00' $$),
  '42501',
  'a client update cannot name the created_at column'
);
select is(
  pg_temp.probe_state($$ update public.daily_check_ins
        set updated_at = timestamptz '2000-01-01 00:00:00+00' $$),
  '42501',
  'a client update cannot name the updated_at column'
);

-- Decision 5: there is no client DELETE privilege and no DELETE policy.
select is(
  pg_temp.probe_state($$ delete from public.daily_check_ins $$),
  '42501',
  'the data subject cannot delete their own check-in, because no client DELETE path exists'
);

reset role;

-- The remaining synthetic subjects insert their own rows the same way, which
-- also proves the insert policy is not specific to one fixture.

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000c","role":"authenticated"}';
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000c', date '2026-07-20',
             5, 3, 'none') $$),
  'ok',
  'a second Team A athlete inserts their own check-in'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000e","role":"authenticated"}';
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000e', date '2026-07-20',
             5, 3, 'none') $$),
  'ok',
  'the wrong-category athlete inserts their own check-in'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000f","role":"authenticated"}';
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000f', date '2026-07-20',
             5, 3, 'none') $$),
  'ok',
  'the dual-team athlete inserts their own check-in'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000012","role":"authenticated"}';
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-000000000012', date '2026-07-20',
             5, 3, 'none') $$),
  'ok',
  'the toggle athlete inserts their own check-in'
);
reset role;

-- Decision 6 is about the data subject, not about a role. A user who holds a
-- coach membership is still the owner of their own check-in, and that row is
-- exposed to nobody by the self policies.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000a', date '2026-07-20',
             5, 3, 'none') $$),
  'ok',
  'self insert is identity-owned, so a user who is also a coach may record their own check-in'
);
reset role;

-- A snapshot of every stored row. Later sections assert against this join to
-- prove that a refused mutation changed nothing, without ever echoing a health
-- value into the test output.
-- updated_at is part of the snapshot on purpose. Without it a refused mutation
-- that nevertheless fired the trigger would leave the health columns equal and
-- still pass the join, so the timestamp is the tell-tale.
create temporary table check_in_snapshot as
select id, athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status,
       updated_at
from public.daily_check_ins;

select is(
  (select count(*)::int from check_in_snapshot),
  6,
  'six synthetic check-in rows exist, one per subject'
);

-- ---------------------------------------------------------------------------
-- 6. One athlete cannot reach another athlete's row
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000c","role":"authenticated"}';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'an athlete in the same team cannot read another athlete''s check-in'
);
select is(
  (select count(*)::int from public.daily_check_ins),
  1,
  'that athlete sees only their own row and nothing else at all'
);

-- The update matches no row through the policy rather than erroring, so the
-- affected-row count is the assertion that has teeth. The attempted values are
-- deliberately different from the stored ones, and the snapshot join below is
-- kept as defence in depth.
with cross_athlete_update as (
  update public.daily_check_ins as c
     set rpe = 1, overall_feeling = 1, pain_status = 'none'
   where c.athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
  returning 1 as touched
)
select is(
  (select count(*)::int from cross_athlete_update),
  0,
  'another athlete''s update of a check-in affects exactly zero rows'
);

select is(
  pg_temp.probe_state($$ delete from public.daily_check_ins
      where athlete_profile_id = '00000000-0000-4000-8000-00000000000b' $$),
  '42501',
  'an athlete cannot delete another athlete''s check-in'
);

reset role;

select is(
  (select count(*)::int
     from public.daily_check_ins as c
     join check_in_snapshot as s
       on s.id = c.id
      and s.athlete_profile_id = c.athlete_profile_id
      and s.check_in_date = c.check_in_date
      and s.rpe = c.rpe
      and s.overall_feeling = c.overall_feeling
      and s.pain_status = c.pain_status
      and s.updated_at = c.updated_at),
  6,
  'every stored row is unchanged after another athlete attempted an update'
);

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000a'),
  0,
  'an athlete cannot read the check-in owned by a coach of their own team'
);

reset role;

-- ---------------------------------------------------------------------------
-- 7. Consent is what a coach's read depends on
-- ---------------------------------------------------------------------------
--
-- Grants are created through the TASK-011 RPCs, as a real client would, so the
-- coach-read path is exercised end to end rather than against hand-written
-- grant rows.

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')) is not null,
  'the main subject grants check_in sharing to Team A'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000e","role":"authenticated"}';
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'workout_summary')) is not null,
  'the wrong-category athlete grants workout_summary to Team A'
);
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'sleep_summary')) is not null,
  'the wrong-category athlete grants sleep_summary to Team A'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000f","role":"authenticated"}';
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000b1'::uuid, 'check_in')) is not null,
  'the dual-team athlete grants check_in to Team B only'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000012","role":"authenticated"}';
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')) is not null,
  'the toggle athlete grants check_in sharing to Team A'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'an active coach reads the check-in of an actively sharing athlete in the same team'
);
select ok(
  private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000b'),
  'the read helper is true for that athlete'
);

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'both memberships active but no grant at all means the coach reads nothing'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000c'),
  'the read helper is false without a grant'
);

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000e'),
  0,
  'a workout_summary and sleep_summary grant does not authorize check-in access'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000e'),
  'the read helper is false for a grant in another category'
);

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000f'),
  0,
  'a Team A coach cannot read an athlete who shares only through Team B'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000f'),
  'the read helper is false across a team the caller does not coach'
);

select is(
  (select count(*)::int from public.daily_check_ins),
  3,
  'the coach sees exactly the two actively shared rows plus their own, and nothing else'
);

-- Decision 8: the coach has no write path, even to a row they may read.
select is(
  pg_temp.probe_state($$ insert into public.daily_check_ins
       (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
     values ('00000000-0000-4000-8000-00000000000b', date '2026-07-23',
             5, 3, 'none') $$),
  '42501',
  'a coach cannot insert a check-in for an athlete who shares with them'
);
-- Readable is not writable. The coach can see this row, so a widened UPDATE
-- policy would silently modify it; the affected-row count is what catches that.
with coach_update as (
  update public.daily_check_ins as c
     set rpe = 2, overall_feeling = 2, pain_status = 'none'
   where c.athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
  returning 1 as touched
)
select is(
  (select count(*)::int from coach_update),
  0,
  'a coach''s update of a check-in they may read affects exactly zero rows'
);
select is(
  pg_temp.probe_state($$ delete from public.daily_check_ins
      where athlete_profile_id = '00000000-0000-4000-8000-00000000000b' $$),
  '42501',
  'a coach cannot delete a check-in'
);

reset role;

select is(
  (select count(*)::int
     from public.daily_check_ins as c
     join check_in_snapshot as s
       on s.id = c.id
      and s.athlete_profile_id = c.athlete_profile_id
      and s.check_in_date = c.check_in_date
      and s.rpe = c.rpe
      and s.overall_feeling = c.overall_feeling
      and s.pain_status = c.pain_status
      and s.updated_at = c.updated_at),
  6,
  'every stored row is unchanged after a coach attempted an update'
);

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000d","role":"authenticated"}';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000f'),
  1,
  'the Team B coach reads the athlete who granted through Team B'
);
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'the Team B coach reads nothing belonging to a Team A athlete'
);
select is(
  (select count(*)::int from public.daily_check_ins),
  1,
  'the Team B coach sees exactly that one shared row'
);

reset role;

-- Another athlete of the same team cannot ride the coach's grant.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000c","role":"authenticated"}';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'a teammate athlete cannot use the grant that authorizes the coach'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000b'),
  'the read helper is false for a caller who holds no coach membership'
);

reset role;

-- ---------------------------------------------------------------------------
-- 8. Revoking the grant removes coach visibility on the next query
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
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'the coach loses that athlete''s check-in on the very next query, with no token change'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000b'),
  'the read helper turns false immediately after revocation'
);
reset role;

-- Decision 6: revocation is about the coach, never about the owner.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins),
  1,
  'the data subject still reads their own check-in after revoking sharing'
);
reset role;

-- Retained consent history must never authorize a read.
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'
      and data_category = 'check_in'
      and revoked_at is not null),
  1,
  'the revoked grant is retained as consent history'
);

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  0,
  'the retained revoked grant authorizes nothing'
);
reset role;

-- Only an explicit new grant restores access.
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';
select ok(
  (select public.grant_team_data_sharing(
     '00000000-0000-4000-8000-0000000000a1'::uuid, 'check_in')) is not null,
  'the athlete grants check_in sharing again'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'coach access returns only after an explicit new grant'
);
reset role;

-- ---------------------------------------------------------------------------
-- 9. Revoking the coach membership removes coach visibility
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000013","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'a second active Team A coach also reads the shared check-in'
);
reset role;

update public.team_memberships
set status = 'revoked', revoked_at = now()
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000013';

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000013","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins),
  0,
  'that coach loses every check-in on the very next query after their membership is revoked'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-00000000000b'),
  'the read helper is false for a revoked coach membership'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000b'),
  1,
  'revoking one coach does not affect another active coach of the same team'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000b","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins),
  1,
  'the data subject still reads their own check-in after a coach membership is revoked'
);
reset role;

-- ---------------------------------------------------------------------------
-- 10. Revoking the athlete membership removes coach visibility
-- ---------------------------------------------------------------------------

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'),
  1,
  'the coach reads the toggle athlete''s check-in while both memberships are active'
);
reset role;

update public.team_memberships
set status = 'revoked', revoked_at = now()
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000012';

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'),
  0,
  'the coach loses that check-in on the next query after the athlete membership is revoked'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-000000000012'),
  'the read helper is false for a revoked athlete membership'
);
reset role;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000012","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins),
  1,
  'the data subject still reads their own check-in after their membership is revoked'
);
reset role;

-- The TASK-011 trigger revoked the grant as well, and reactivation revives
-- nothing.
select is(
  (select count(*)::int from public.sharing_grants
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'
      and revoked_at is null),
  0,
  'revoking the athlete membership left no active grant behind'
);

update public.team_memberships
set status = 'active', revoked_at = null
where team_id = '00000000-0000-4000-8000-0000000000a1'
  and profile_id = '00000000-0000-4000-8000-000000000012';

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-00000000000a","role":"authenticated"}';
select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-000000000012'),
  0,
  'reactivating the membership does not restore coach access to the check-in'
);
select ok(
  not private.can_current_user_read_check_in('00000000-0000-4000-8000-000000000012'),
  'the read helper stays false after reactivation until the athlete grants again'
);
reset role;

-- ---------------------------------------------------------------------------
-- 11. Row Level Security, policies, and privileges
-- ---------------------------------------------------------------------------

select ok(
  (select relrowsecurity from pg_catalog.pg_class
    where oid = 'public.daily_check_ins'::regclass),
  'RLS is enabled on public.daily_check_ins'
);

select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'),
  4,
  'daily_check_ins carries exactly four policies'
);
select is(
  (select coalesce(string_agg(policyname || ':' || cmd, ', ' order by policyname), '')
     from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'),
  'daily_check_ins_insert_own:INSERT, daily_check_ins_select_own:SELECT, '
  || 'daily_check_ins_select_shared_for_coach:SELECT, daily_check_ins_update_own:UPDATE',
  'the four policies are exactly one INSERT, two SELECT, and one UPDATE'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'
      and cmd = 'DELETE'),
  0,
  'no DELETE policy exists on daily_check_ins'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'
      and 'anon' = any (roles)),
  0,
  'no daily_check_ins policy targets the anon role'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'
      and 'public' = any (roles)),
  0,
  'no daily_check_ins policy targets every role'
);
-- The coach path is read-only: it must not appear on a write policy.
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'
      and cmd <> 'SELECT'
      and coalesce(qual, '') || coalesce(with_check, '')
          like '%can_current_user_read_check_in%'),
  0,
  'no write policy consults the coach read helper'
);
select is(
  (select count(*)::int from pg_catalog.pg_policies
    where schemaname = 'public' and tablename = 'daily_check_ins'
      and cmd <> 'SELECT'
      and coalesce(with_check, '') not like '%auth.uid()%'),
  0,
  'every write policy constrains the row to the caller''s own identity'
);

select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'daily_check_ins'
      and grantee = 'anon'),
  0,
  'anon holds no table privilege on daily_check_ins'
);
select is(
  (select count(*)::int from pg_catalog.pg_attribute as a
     cross join pg_catalog.aclexplode(a.attacl) as acl
    where a.attrelid = 'public.daily_check_ins'::regclass
      and acl.grantee = 'anon'::regrole),
  0,
  'anon holds no column privilege on daily_check_ins either'
);
select is(
  (select coalesce(string_agg(distinct privilege_type, ',' order by privilege_type), '')
     from information_schema.role_table_grants
    where table_schema = 'public' and table_name = 'daily_check_ins'
      and grantee = 'authenticated'),
  'SELECT',
  'the only table-wide privilege authenticated holds is SELECT'
);

-- The write privileges are column-level, which is what makes the
-- database-controlled and immutable columns unwritable rather than merely
-- unwritten.
select is(
  (select coalesce(string_agg(a.attname, ',' order by a.attname), '')
     from pg_catalog.pg_attribute as a
     cross join pg_catalog.aclexplode(a.attacl) as acl
    where a.attrelid = 'public.daily_check_ins'::regclass
      and acl.grantee = 'authenticated'::regrole
      and acl.privilege_type = 'INSERT'),
  'athlete_profile_id,check_in_date,overall_feeling,pain_status,rpe',
  'authenticated may insert exactly the five client-supplied columns'
);
select is(
  (select coalesce(string_agg(a.attname, ',' order by a.attname), '')
     from pg_catalog.pg_attribute as a
     cross join pg_catalog.aclexplode(a.attacl) as acl
    where a.attrelid = 'public.daily_check_ins'::regclass
      and acl.grantee = 'authenticated'::regrole
      and acl.privilege_type = 'UPDATE'),
  'overall_feeling,pain_status,rpe',
  'authenticated may update exactly the three health columns'
);
select is(
  (select count(*)::int from pg_catalog.pg_attribute as a
     cross join pg_catalog.aclexplode(a.attacl) as acl
    where a.attrelid = 'public.daily_check_ins'::regclass
      and acl.grantee = 'authenticated'::regrole
      and acl.privilege_type not in ('INSERT', 'UPDATE')),
  0,
  'authenticated holds no other column-level privilege'
);

select ok(
  has_table_privilege('authenticated', 'public.daily_check_ins', 'select'),
  'authenticated can select from daily_check_ins'
);
select ok(
  not has_table_privilege('anon', 'public.daily_check_ins', 'select'),
  'anon cannot select from daily_check_ins'
);
select ok(
  not has_table_privilege('authenticated', 'public.daily_check_ins', 'insert'),
  'authenticated holds no table-wide insert privilege'
);
select ok(
  not has_table_privilege('authenticated', 'public.daily_check_ins', 'update'),
  'authenticated holds no table-wide update privilege'
);
select ok(
  has_any_column_privilege('authenticated', 'public.daily_check_ins', 'insert'),
  'authenticated holds a column-level insert privilege instead'
);
select ok(
  has_any_column_privilege('authenticated', 'public.daily_check_ins', 'update'),
  'authenticated holds a column-level update privilege instead'
);
select ok(
  not has_table_privilege('authenticated', 'public.daily_check_ins', 'delete'),
  'authenticated cannot delete from daily_check_ins'
);
select ok(
  not has_any_column_privilege('anon', 'public.daily_check_ins', 'insert'),
  'anon holds no insert privilege on any column'
);
select ok(
  not has_any_column_privilege('anon', 'public.daily_check_ins', 'update'),
  'anon holds no update privilege on any column'
);
select ok(
  not has_table_privilege('anon', 'public.daily_check_ins', 'delete'),
  'anon cannot delete from daily_check_ins'
);
select ok(
  not has_table_privilege('authenticated', 'public.daily_check_ins', 'truncate'),
  'authenticated cannot truncate daily_check_ins'
);
select ok(
  not has_table_privilege('authenticated', 'public.daily_check_ins', 'references'),
  'authenticated holds no references privilege on daily_check_ins'
);
select ok(
  not has_table_privilege('authenticated', 'public.daily_check_ins', 'trigger'),
  'authenticated holds no trigger privilege on daily_check_ins'
);

-- The earlier tables are untouched by this migration.
select is(
  (select count(*)::int from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('profiles', 'teams', 'team_memberships', 'sharing_grants')
      and grantee = 'anon'),
  0,
  'anon still holds no privilege on the TASK-008 and TASK-011 tables'
);
select is(
  (select coalesce(string_agg(distinct privilege_type, ',' order by privilege_type), '')
     from information_schema.role_table_grants
    where table_schema = 'public'
      and table_name in ('teams', 'team_memberships', 'sharing_grants')
      and grantee = 'authenticated'),
  'SELECT',
  'the TASK-008 and TASK-011 tables remain read-only for authenticated'
);

-- ---------------------------------------------------------------------------
-- 12. Function catalog, privileges, and reuse of the TASK-011 helper
-- ---------------------------------------------------------------------------

select has_function('private', 'can_current_user_read_check_in',
  array['uuid'], 'the check-in read helper exists in the private schema');
select has_function('private', 'enforce_daily_check_in_columns',
  array[]::text[], 'the column enforcement trigger function exists in the private schema');

select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('public', 'graphql_public')
      and p.proname in ('can_current_user_read_check_in',
                        'enforce_daily_check_in_columns')),
  0,
  'neither TASK-012 function is defined in an exposed schema'
);

select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private' and p.prosecdef
      and p.proname in ('can_current_user_read_check_in',
                        'enforce_daily_check_in_columns')),
  2,
  'both TASK-012 functions are SECURITY DEFINER'
);
select is(
  (select count(*)::int from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private'
      and p.proname in ('can_current_user_read_check_in',
                        'enforce_daily_check_in_columns')
      and exists (
        select 1 from unnest(p.proconfig) as cfg
        -- PostgreSQL stores an empty search_path canonically as search_path=""
        where cfg in ('search_path=""', 'search_path='))),
  2,
  'both TASK-012 functions pin an empty search_path'
);

select ok(
  not has_function_privilege('anon',
    'private.can_current_user_read_check_in(uuid)', 'execute'),
  'anon cannot execute the check-in read helper'
);
select ok(
  has_function_privilege('authenticated',
    'private.can_current_user_read_check_in(uuid)', 'execute'),
  'authenticated can execute the read helper, which the coach policy requires'
);
select ok(
  not has_function_privilege('authenticated',
    'private.enforce_daily_check_in_columns()', 'execute'),
  'authenticated cannot execute the column enforcement trigger function'
);
select ok(
  not has_schema_privilege('anon', 'private', 'usage'),
  'anon still holds no usage on the private schema'
);

-- Decision 7: the coach path reuses the TASK-011 authorization helper rather
-- than duplicating or weakening it. These assertions fail the moment somebody
-- forks that logic into this table's helper.
select has_function('private', 'can_current_user_read_shared_data',
  array['uuid', 'uuid', 'text'],
  'the TASK-011 authorization helper still exists with its original signature');
select ok(
  (select p.prosrc like '%can_current_user_read_shared_data%'
     from pg_catalog.pg_proc p
     join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private' and p.proname = 'can_current_user_read_check_in'),
  'the check-in read helper calls the TASK-011 authorization helper'
);
select ok(
  (select p.prosrc not like '%sharing_grants%'
     from pg_catalog.pg_proc p
     join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private' and p.proname = 'can_current_user_read_check_in'),
  'it does not reimplement the sharing-grant lookup'
);
select ok(
  (select p.prosrc not like '%coach%'
     from pg_catalog.pg_proc p
     join pg_catalog.pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'private' and p.proname = 'can_current_user_read_check_in'),
  'it does not reimplement the coach-role check'
);
select ok(
  (select count(*)::int from pg_catalog.pg_policies
     where schemaname = 'public' and tablename = 'daily_check_ins'
       and policyname = 'daily_check_ins_select_shared_for_coach'
       and qual like '%can_current_user_read_check_in%') = 1,
  'the coach SELECT policy delegates entirely to the read helper'
);

-- ---------------------------------------------------------------------------
-- 13. Trusted cascade deletion leaves no orphan health row
-- ---------------------------------------------------------------------------

delete from auth.users where id = '00000000-0000-4000-8000-00000000000c';

select is(
  (select count(*)::int from public.daily_check_ins
    where athlete_profile_id = '00000000-0000-4000-8000-00000000000c'),
  0,
  'deleting the auth user cascades through the profile to every check-in'
);

select * from finish();

rollback;
