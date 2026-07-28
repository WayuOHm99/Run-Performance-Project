-- TASK-012: Daily check-in RLS foundation.
--
-- The first protected-health-data table in the product. It stores an athlete's
-- own daily RPE, overall feeling, and pain status, and nothing else.
--
-- TASK-008 built identity, teams, and membership, and recorded that active
-- membership alone must never be treated as sufficient for health access.
-- TASK-011 supplied the missing half: an athlete-owned, per-team, per-category
-- consent record and the single authorization helper
-- private.can_current_user_read_shared_data. This migration is the first
-- consumer of that helper, and it calls it rather than reimplementing it.
--
-- A check-in is personal athlete data, not team-owned data, so there is no
-- team_id column. The same personal row is shared independently with each team
-- through sharing_grants.
--
-- This migration does not edit the TASK-008, TASK-009, or TASK-011 migrations,
-- and changes no existing policy, grant, constraint, or column semantic.

-- ---------------------------------------------------------------------------
-- Table
-- ---------------------------------------------------------------------------

create table public.daily_check_ins (
  id uuid primary key default gen_random_uuid(),
  athlete_profile_id uuid not null
    references public.profiles (id) on delete cascade,
  -- The client's local calendar date. A date, not a timestamptz: which day a
  -- check-in belongs to is a calendar fact for the athlete, and storing an
  -- instant would make it depend on the reader's time zone.
  check_in_date date not null,
  rpe smallint not null,
  overall_feeling smallint not null,
  pain_status text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint daily_check_ins_rpe_valid check (rpe between 0 and 10),
  constraint daily_check_ins_overall_feeling_valid check (
    overall_feeling between 1 and 5
  ),
  constraint daily_check_ins_pain_status_valid check (
    pain_status in ('none', 'present')
  ),
  -- At most one check-in per athlete per local calendar date. A correction is
  -- an update to this row, never a second row.
  constraint daily_check_ins_athlete_date_unique
    unique (athlete_profile_id, check_in_date)
);

comment on table public.daily_check_ins is
  'One athlete-owned daily check-in per local calendar date. Protected health data: RPE, overall feeling, and pain status only. Personal data, not team data; there is deliberately no team_id, and sharing is granted per team through sharing_grants.';

comment on column public.daily_check_ins.athlete_profile_id is
  'The data subject. Immutable after insert, and always the inserting client''s own auth.uid().';

comment on column public.daily_check_ins.check_in_date is
  'The client-supplied local calendar date the check-in belongs to. Immutable after insert.';

comment on column public.daily_check_ins.rpe is
  'Protected health value: session rating of perceived exertion, 0 through 10.';

comment on column public.daily_check_ins.overall_feeling is
  'Protected health value: subjective overall feeling, 1 through 5.';

comment on column public.daily_check_ins.pain_status is
  'Protected health value: exactly none or present. Deliberately not free text, and never a body location or a diagnosis.';

comment on column public.daily_check_ins.created_at is
  'Database-controlled and immutable after insert. Never supplied by a client.';

comment on column public.daily_check_ins.updated_at is
  'Database-controlled. Never supplied by a client.';

-- No index is created here.
--
-- daily_check_ins_athlete_date_unique already provides a b-tree index on
-- (athlete_profile_id, check_in_date), and its leading column serves both query
-- paths this task has: the data subject reading their own check-ins, and a
-- coach reading one athlete's check-ins once the authorization helper has
-- passed. Neither path scans by date across athletes, so a date-only index
-- would be unused cost on a protected-health table.

-- ---------------------------------------------------------------------------
-- Database-controlled and immutable columns
-- ---------------------------------------------------------------------------
--
-- Defence in depth behind the column privileges below, not instead of them. No
-- client role holds INSERT or UPDATE privilege on id, created_at, or
-- updated_at, and no client role holds UPDATE privilege on athlete_profile_id
-- or check_in_date, so a client attempt is refused with 42501 before this
-- trigger is reached. The trigger keeps the guarantee true for any future
-- writer inside the trusted boundary.
--
-- The name deliberately contains no 'health' substring, so the TASK-008
-- assertion that no broad health-data authorization helper exists in the
-- private schema stays meaningful.

create function private.enforce_daily_check_in_columns()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    -- A row can never be backdated, even by a trusted writer.
    new.created_at := pg_catalog.now();
    new.updated_at := pg_catalog.now();
    return new;
  end if;

  -- Decision 4: the owner, the calendar date, the identity, and the creation
  -- time are immutable once the row exists. Only the three health fields may
  -- change.
  new.id := old.id;
  new.athlete_profile_id := old.athlete_profile_id;
  new.check_in_date := old.check_in_date;
  new.created_at := old.created_at;

  new.updated_at := pg_catalog.now();

  return new;
end;
$$;

comment on function private.enforce_daily_check_in_columns() is
  'Forces created_at and updated_at to database time and keeps id, athlete_profile_id, check_in_date, and created_at immutable after insert.';

create trigger daily_check_ins_enforce_columns
before insert or update on public.daily_check_ins
for each row
execute function private.enforce_daily_check_in_columns();

-- ---------------------------------------------------------------------------
-- Read-authorization helper
-- ---------------------------------------------------------------------------
--
-- public.daily_check_ins has no team_id, because a check-in is personal data
-- shared independently per team. This helper therefore enumerates the teams in
-- which the target holds an active athlete membership and asks the TASK-011
-- helper, unchanged, whether the caller may read check_in data for that athlete
-- in that team.
--
-- It adds no authorization condition of its own and removes none. Every
-- coach-role check, athlete-membership check, grant check, category check, and
-- revocation check stays inside private.can_current_user_read_shared_data. The
-- outer predicates here are a strict subset of what that helper re-checks
-- anyway, so this cannot widen access; it only supplies candidate team ids.
--
-- SECURITY DEFINER, so the enumeration is not filtered by the team_memberships
-- policies. That keeps the coach policy fail-closed rather than dependent on
-- another table's read policy, and it keeps the policy non-recursive.

create function private.can_current_user_read_check_in(
  p_athlete_profile_id uuid
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.team_memberships as athlete_membership
    where athlete_membership.profile_id = p_athlete_profile_id
      and athlete_membership.status = 'active'
      and athlete_membership.role = 'athlete'
      and private.can_current_user_read_shared_data(
            athlete_membership.team_id, p_athlete_profile_id, 'check_in')
  );
$$;

comment on function private.can_current_user_read_check_in(uuid) is
  'True only when some team gives the caller an active coach membership, the target an active athlete membership, and an active check_in sharing grant. Delegates the whole authorization decision to private.can_current_user_read_shared_data; adds no condition of its own.';

-- ---------------------------------------------------------------------------
-- Function privileges
-- ---------------------------------------------------------------------------

revoke all on function private.enforce_daily_check_in_columns() from public;
revoke all on function private.can_current_user_read_check_in(uuid) from public;

revoke all on function private.can_current_user_read_check_in(uuid) from anon;

-- A policy expression is evaluated as the calling role, so the read helper
-- needs an execute grant to authenticated. The trigger function is invoked by
-- the database and is granted to nobody.
grant execute on function private.can_current_user_read_check_in(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Table and column privileges
-- ---------------------------------------------------------------------------
--
-- Supabase default privileges grant ALL on a new public table to anon and
-- authenticated. Revoke that first, then grant back the minimum.
--
-- The write grants are deliberately column-level. That is what makes the
-- database-controlled and immutable columns unwritable rather than merely
-- unwritten: a client insert cannot name id, created_at, or updated_at at all,
-- and a client update cannot name id, athlete_profile_id, check_in_date,
-- created_at, or updated_at at all. Each attempt fails with 42501 at the
-- privilege layer, before RLS and before the trigger.
--
-- anon keeps nothing, so every anonymous statement fails with 42501 before RLS
-- is consulted. No DELETE privilege is granted to any client role, and no
-- DELETE policy exists.

revoke all on table public.daily_check_ins from anon, authenticated;

grant select on table public.daily_check_ins to authenticated;

grant insert (athlete_profile_id, check_in_date, rpe, overall_feeling, pain_status)
  on table public.daily_check_ins to authenticated;

grant update (rpe, overall_feeling, pain_status)
  on table public.daily_check_ins to authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.daily_check_ins enable row level security;

-- Decision 6: the data subject always reads their own check-ins, independent of
-- team membership and of sharing status. Nothing about this policy can expose a
-- row to anybody else.
create policy daily_check_ins_select_own
on public.daily_check_ins
for select
to authenticated
using (athlete_profile_id = (select auth.uid()));

comment on policy daily_check_ins_select_own on public.daily_check_ins is
  'The data subject reads their own check-ins unconditionally.';

-- Decisions 7 and 8: coach access is read-only and routes entirely through the
-- TASK-011 authorization helper, so coach visibility and consent cannot drift
-- apart. Revoking the grant, the coach membership, or the athlete membership
-- takes effect on the coach's next query, because the helper is evaluated fresh
-- every time and no authorization state lives in the token.
create policy daily_check_ins_select_shared_for_coach
on public.daily_check_ins
for select
to authenticated
using (private.can_current_user_read_check_in(athlete_profile_id));

comment on policy daily_check_ins_select_shared_for_coach on public.daily_check_ins is
  'A coach reads a check-in only while an active coach membership, an active athlete membership in the same team, and an active check_in sharing grant all exist.';

-- Decision 6: self insert is identity-owned. A row can only ever be created for
-- the caller, so no client can write health data attributed to somebody else.
create policy daily_check_ins_insert_own
on public.daily_check_ins
for insert
to authenticated
with check (athlete_profile_id = (select auth.uid()));

comment on policy daily_check_ins_insert_own on public.daily_check_ins is
  'A client may insert a check-in only for themselves.';

-- Decision 5: the data subject updates only their own row. Which columns may
-- change is settled by the column-level UPDATE grant above, so this policy only
-- has to settle which rows.
--
-- The WITH CHECK is not redundant with the USING: without it, the post-image
-- would be unchecked. It cannot in fact be violated, because athlete_profile_id
-- is outside the column grant and the trigger restores it, but leaving the
-- post-image unconstrained on a health table would be the wrong default.
create policy daily_check_ins_update_own
on public.daily_check_ins
for update
to authenticated
using (athlete_profile_id = (select auth.uid()))
with check (athlete_profile_id = (select auth.uid()));

comment on policy daily_check_ins_update_own on public.daily_check_ins is
  'A client may update only their own check-in row, and only the three health columns the column-level grant allows.';

-- No DELETE policy is created for any role, and no DELETE privilege is granted.
-- Deletion and export are a later, separately reviewed privacy-request task.
