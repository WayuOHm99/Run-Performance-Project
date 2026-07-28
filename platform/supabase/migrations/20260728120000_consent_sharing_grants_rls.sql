-- TASK-011: Consent and sharing grants RLS foundation.
--
-- TASK-008 built identity, teams, and membership, and recorded that active
-- membership alone must never be treated as sufficient for health access. This
-- migration supplies the missing half: an explicit, athlete-owned, per-team,
-- per-category consent record, plus the single authorization helper that every
-- future protected health table must consult.
--
-- Consent metadata only. No health value, measurement, or note is stored here.
--
-- This migration does not edit the TASK-008 or TASK-009 migrations, and does not
-- change the semantic behaviour of any existing membership policy, grant, or
-- constraint.

-- ---------------------------------------------------------------------------
-- Table
-- ---------------------------------------------------------------------------

create table public.sharing_grants (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null,
  athlete_profile_id uuid not null,
  data_category text not null,
  granted_at timestamptz not null default now(),
  revoked_at timestamptz,
  constraint sharing_grants_data_category_valid check (
    data_category in ('check_in', 'workout_summary', 'sleep_summary')
  ),
  constraint sharing_grants_revoked_after_granted check (
    revoked_at is null or revoked_at >= granted_at
  ),
  -- The integrity tie to the trusted membership row. A grant cannot exist
  -- without one, and deleting the membership, the profile, the auth user, or
  -- the team cascades the grant away instead of leaving a usable orphan.
  --
  -- ON UPDATE is deliberately NO ACTION: re-keying a membership row while an
  -- active grant exists is refused with 23503 rather than silently moving
  -- someone's consent to a different athlete or team.
  constraint sharing_grants_membership_fkey
    foreign key (team_id, athlete_profile_id)
    references public.team_memberships (team_id, profile_id)
    on delete cascade
);

comment on table public.sharing_grants is
  'Athlete consent to share one data category with one team. Consent metadata only; never health values. An active grant is exactly revoked_at is null; revoked rows are retained history.';

comment on column public.sharing_grants.granted_at is
  'Database-generated and immutable after insert. Never supplied by a client.';

comment on column public.sharing_grants.revoked_at is
  'Database-controlled and append-only. Null means the grant is active.';

-- At most one active grant per athlete, team, and category. Revoked history
-- rows are excluded, so they may accumulate freely.
create unique index sharing_grants_one_active_idx
  on public.sharing_grants (team_id, athlete_profile_id, data_category)
  where revoked_at is null;

-- Supports the athlete's own-history read.
create index sharing_grants_athlete_profile_id_idx
  on public.sharing_grants (athlete_profile_id);

-- Supports coach-side reads and the authorization helper.
create index sharing_grants_team_active_idx
  on public.sharing_grants (team_id, athlete_profile_id, data_category)
  where revoked_at is null;

-- ---------------------------------------------------------------------------
-- Database-controlled timestamps
-- ---------------------------------------------------------------------------
--
-- No client role holds a write privilege on this table, so the timestamps are
-- already unreachable from the outside. This trigger makes the guarantee a
-- property of the table rather than of the calling function, so it still holds
-- for any future writer inside the trusted boundary.

create function private.enforce_sharing_grant_timestamps()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    new.granted_at := pg_catalog.now();
    new.revoked_at := null;
    return new;
  end if;

  -- Identity and grant time are immutable once the row exists.
  new.id := old.id;
  new.team_id := old.team_id;
  new.athlete_profile_id := old.athlete_profile_id;
  new.data_category := old.data_category;
  new.granted_at := old.granted_at;

  if old.revoked_at is not null then
    -- History is append-only: a revoked row can never be un-revoked or
    -- re-stamped. A later re-grant creates a new row instead.
    new.revoked_at := old.revoked_at;
  elsif new.revoked_at is not null then
    new.revoked_at := pg_catalog.now();
  end if;

  return new;
end;
$$;

comment on function private.enforce_sharing_grant_timestamps() is
  'Forces granted_at and revoked_at to database time, keeps grant identity immutable, and makes revocation append-only.';

create trigger sharing_grants_enforce_timestamps
before insert or update on public.sharing_grants
for each row
execute function private.enforce_sharing_grant_timestamps();

-- ---------------------------------------------------------------------------
-- Membership revocation cascades to consent
-- ---------------------------------------------------------------------------
--
-- Decision 7: when a membership stops being an active athlete membership, its
-- active grants are revoked. The trigger never inserts and never clears
-- revoked_at, and it does not fire on reactivation, so a reactivated membership
-- starts with no active grant and the athlete must explicitly grant again.

create function private.revoke_sharing_grants_on_membership_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.sharing_grants as g
  set revoked_at = pg_catalog.now()
  where g.team_id = old.team_id
    and g.athlete_profile_id = old.profile_id
    and g.revoked_at is null;

  return new;
end;
$$;

comment on function private.revoke_sharing_grants_on_membership_change() is
  'Revokes every active sharing grant of a membership that has ceased to be an active athlete membership. Never revives a grant.';

-- The WHEN clause is the whole scope of this trigger: it fires only for a row
-- that was an active athlete membership and is no longer one. A coach-role
-- change, a reactivation, and an unrelated column update do not fire it.
create trigger team_memberships_revoke_sharing_grants
after update on public.team_memberships
for each row
when (
  (old.status = 'active' and old.role = 'athlete')
  and not (new.status = 'active' and new.role = 'athlete')
)
execute function private.revoke_sharing_grants_on_membership_change();

-- ---------------------------------------------------------------------------
-- Write API
-- ---------------------------------------------------------------------------
--
-- authenticated holds no write privilege on public.sharing_grants, so these two
-- functions are the only client-reachable write path. Neither accepts an
-- athlete identifier or a timestamp: the identity is always auth.uid() and the
-- timestamps are always the database's.
--
-- Every raised message is a fixed string. None interpolates a row, an athlete,
-- or a team, so a server error cannot leak another athlete's or team's data.

create function public.grant_team_data_sharing(
  p_team_id uuid,
  p_data_category text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_actor uuid := (select auth.uid());
  v_grant_id uuid;
begin
  if v_actor is null then
    raise exception 'authentication required'
      using errcode = '42501';
  end if;

  if p_data_category is null
    or p_data_category not in ('check_in', 'workout_summary', 'sleep_summary')
  then
    raise exception 'unsupported data category'
      using errcode = '22023';
  end if;

  -- Decision 9 in miniature: only an active athlete membership may consent. A
  -- coach-role membership in the same team is refused here.
  if not exists (
    select 1
    from public.team_memberships as m
    where m.team_id = p_team_id
      and m.profile_id = v_actor
      and m.status = 'active'
      and m.role = 'athlete'
  ) then
    raise exception 'active athlete membership required'
      using errcode = '42501';
  end if;

  -- Idempotent: an existing active grant is returned unchanged.
  select g.id into v_grant_id
  from public.sharing_grants as g
  where g.team_id = p_team_id
    and g.athlete_profile_id = v_actor
    and g.data_category = p_data_category
    and g.revoked_at is null;

  if v_grant_id is not null then
    return v_grant_id;
  end if;

  begin
    insert into public.sharing_grants (team_id, athlete_profile_id, data_category)
    values (p_team_id, v_actor, p_data_category)
    returning id into v_grant_id;
  exception
    when unique_violation then
      -- A concurrent call won the partial unique index race. Resolve to the
      -- same result rather than surfacing an error; two active rows can never
      -- exist either way.
      select g.id into v_grant_id
      from public.sharing_grants as g
      where g.team_id = p_team_id
        and g.athlete_profile_id = v_actor
        and g.data_category = p_data_category
        and g.revoked_at is null;
  end;

  return v_grant_id;
end;
$$;

comment on function public.grant_team_data_sharing(uuid, text) is
  'Grants the calling athlete''s consent to share one category with one team. Returns the id of the resulting active grant. Idempotent. Requires an active athlete membership.';

create function public.revoke_team_data_sharing(
  p_team_id uuid,
  p_data_category text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_actor uuid := (select auth.uid());
  v_grant_id uuid;
begin
  if v_actor is null then
    raise exception 'authentication required'
      using errcode = '42501';
  end if;

  if p_data_category is null
    or p_data_category not in ('check_in', 'workout_summary', 'sleep_summary')
  then
    raise exception 'unsupported data category'
      using errcode = '22023';
  end if;

  -- Deliberately no membership check. Withdrawing consent must remain possible
  -- for the owner even after their membership has been revoked.
  --
  -- The athlete_profile_id predicate is what restricts this to the caller's own
  -- consent; there is no parameter through which another athlete's row could be
  -- named.
  update public.sharing_grants as g
  set revoked_at = pg_catalog.now()
  where g.team_id = p_team_id
    and g.athlete_profile_id = v_actor
    and g.data_category = p_data_category
    and g.revoked_at is null
  returning g.id into v_grant_id;

  -- Null when nothing was active, which is also what makes a repeat revoke
  -- safe.
  return v_grant_id;
end;
$$;

comment on function public.revoke_team_data_sharing(uuid, text) is
  'Revokes the calling athlete''s own active grant for one category and team. Returns the revoked row id, or null when nothing was active. Safe to repeat, and available even after the membership is revoked.';

-- ---------------------------------------------------------------------------
-- Authorization helper
-- ---------------------------------------------------------------------------
--
-- The single helper every future protected health table must consult. A grant
-- alone, a membership alone, or a role alone is never enough.
--
-- SECURITY DEFINER, so its lookup into public.sharing_grants is not subject to
-- the policies below. That is what keeps the coach policy non-recursive.

create function private.can_current_user_read_shared_data(
  p_team_id uuid,
  p_athlete_profile_id uuid,
  p_data_category text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.team_memberships as coach_membership
    join public.team_memberships as athlete_membership
      on athlete_membership.team_id = coach_membership.team_id
    join public.sharing_grants as g
      on g.team_id = coach_membership.team_id
     and g.athlete_profile_id = athlete_membership.profile_id
    where coach_membership.team_id = p_team_id
      and coach_membership.profile_id = (select auth.uid())
      and coach_membership.status = 'active'
      and coach_membership.role = 'coach'
      and athlete_membership.profile_id = p_athlete_profile_id
      and athlete_membership.status = 'active'
      and athlete_membership.role = 'athlete'
      and g.data_category = p_data_category
      and g.revoked_at is null
  );
$$;

comment on function private.can_current_user_read_shared_data(uuid, uuid, text) is
  'True only when the caller holds an active coach membership in the team, the target holds an active athlete membership in the same team, and the target has an active sharing grant for that category. The required gate for all future protected health data.';

-- ---------------------------------------------------------------------------
-- Function privileges
-- ---------------------------------------------------------------------------
--
-- Supabase default privileges grant EXECUTE on new public functions to anon and
-- authenticated, so anon is revoked explicitly rather than relying on the
-- PUBLIC revoke alone.

revoke all on function private.enforce_sharing_grant_timestamps() from public;
revoke all on function private.revoke_sharing_grants_on_membership_change() from public;
revoke all on function private.can_current_user_read_shared_data(uuid, uuid, text) from public;
revoke all on function public.grant_team_data_sharing(uuid, text) from public;
revoke all on function public.revoke_team_data_sharing(uuid, text) from public;

revoke all on function private.can_current_user_read_shared_data(uuid, uuid, text) from anon;
revoke all on function public.grant_team_data_sharing(uuid, text) from anon, authenticated;
revoke all on function public.revoke_team_data_sharing(uuid, text) from anon, authenticated;

-- A policy expression is evaluated as the calling role, so the helper needs an
-- execute grant to authenticated. The two trigger functions are invoked by the
-- database and are granted to nobody.
grant execute on function private.can_current_user_read_shared_data(uuid, uuid, text) to authenticated;

grant execute on function public.grant_team_data_sharing(uuid, text) to authenticated;
grant execute on function public.revoke_team_data_sharing(uuid, text) to authenticated;

-- ---------------------------------------------------------------------------
-- Table privileges
-- ---------------------------------------------------------------------------
--
-- Supabase default privileges grant ALL on a new public table to anon and
-- authenticated. Revoke that first, then grant back SELECT only, and only to
-- authenticated. anon keeps nothing, so an anonymous read fails on privilege
-- with 42501 before RLS is consulted, and every refused authenticated write
-- fails the same way rather than being filtered by a row policy.

revoke all on table public.sharing_grants from anon, authenticated;

grant select on table public.sharing_grants to authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.sharing_grants enable row level security;

-- The athlete owns their consent record and reads all of it, active and
-- revoked. Another athlete matches nothing.
create policy sharing_grants_select_own_history
on public.sharing_grants
for select
to authenticated
using (athlete_profile_id = (select auth.uid()));

comment on policy sharing_grants_select_own_history on public.sharing_grants is
  'An athlete reads their own complete consent history, including revoked rows.';

-- Coach visibility routes through the same helper that future health policies
-- must use, so the two cannot drift apart. The explicit revoked_at predicate
-- keeps consent history out of coach reach even though the helper already
-- requires an active grant.
create policy sharing_grants_select_active_for_coach
on public.sharing_grants
for select
to authenticated
using (
  revoked_at is null
  and private.can_current_user_read_shared_data(
    team_id, athlete_profile_id, data_category
  )
);

comment on policy sharing_grants_select_active_for_coach on public.sharing_grants is
  'An active coach reads only active grant rows of active athletes in a team they actively coach. Revoked consent history stays invisible to coaches.';

-- No INSERT, UPDATE, or DELETE policy is created for any role. The two RPCs
-- above are the entire client write path.
