-- TASK-008: Identity, teams, and membership RLS foundation.
--
-- Creates the minimum authorization foundation for the two-role app:
-- profiles, teams, and team memberships, with read-only Row Level Security for
-- authenticated users and no access at all for anonymous users.
--
-- Authorization state lives in the database, never in JWT or user metadata, so
-- a revocation takes effect on the caller's next query.
--
-- Active membership is an identity boundary only. It must never be treated as
-- sufficient for future health-data access; health policies will additionally
-- require an explicit sharing grant.

-- ---------------------------------------------------------------------------
-- Private schema for SECURITY DEFINER authorization helpers.
-- ---------------------------------------------------------------------------

-- This schema is deliberately absent from the exposed API schemas in
-- config.toml (public, graphql_public), so nothing here is reachable through
-- PostgREST or GraphQL.
create schema if not exists private;

revoke all on schema private from public;
revoke all on schema private from anon;

comment on schema private is
  'Non-exposed schema for SECURITY DEFINER authorization helpers. Never add this schema to the exposed API schemas.';

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  constraint profiles_display_name_valid check (
    display_name is null
    or (
      char_length(btrim(display_name)) between 1 and 80
      and char_length(display_name) <= 80
    )
  )
);

comment on table public.profiles is
  'One application profile per auth user. Created automatically on signup; client editing is deferred.';

create table public.teams (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now(),
  constraint teams_name_valid check (
    char_length(btrim(name)) between 1 and 120
    and char_length(name) <= 120
  )
);

comment on table public.teams is
  'A coaching team. Team administration is not exposed to authenticated clients in TASK-008.';

create table public.team_memberships (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams (id) on delete cascade,
  profile_id uuid not null references public.profiles (id) on delete cascade,
  role text not null,
  status text not null,
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  constraint team_memberships_role_valid check (role in ('coach', 'athlete')),
  constraint team_memberships_status_valid check (status in ('active', 'revoked')),
  constraint team_memberships_team_profile_unique unique (team_id, profile_id),
  constraint team_memberships_status_revoked_at_consistent check (
    (status = 'active' and revoked_at is null)
    or (status = 'revoked' and revoked_at is not null)
  )
);

comment on table public.team_memberships is
  'One retained row per user and team. Revocation sets status = revoked and stamps revoked_at; no audit-history table exists yet.';

-- Membership and RLS lookup support. The unique constraint already indexes
-- (team_id, profile_id); these cover the reverse and role/status directions
-- used by the policies below.
create index team_memberships_profile_id_idx
  on public.team_memberships (profile_id);

create index team_memberships_team_id_idx
  on public.team_memberships (team_id);

create index team_memberships_active_coach_idx
  on public.team_memberships (profile_id, team_id)
  where status = 'active' and role = 'coach';

create index team_memberships_active_team_idx
  on public.team_memberships (team_id, profile_id)
  where status = 'active';

-- ---------------------------------------------------------------------------
-- Automatic profile creation
-- ---------------------------------------------------------------------------

-- Deliberately inserts the id only. Auth metadata (name, avatar, provider
-- claims) is never copied into display_name.
create function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id)
  values (new.id)
  on conflict (id) do nothing;

  return new;
end;
$$;

comment on function private.handle_new_user() is
  'Creates the minimal public.profiles row for a new auth user. Never copies auth metadata.';

create trigger on_auth_user_created
after insert on auth.users
for each row
execute function private.handle_new_user();

-- ---------------------------------------------------------------------------
-- Authorization helpers
-- ---------------------------------------------------------------------------
--
-- These run as the definer so the membership lookups inside them are not
-- themselves subject to the policies below. That is what keeps the
-- team_memberships policy non-recursive.

create function private.is_active_team_member(p_team_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.team_memberships as m
    where m.team_id = p_team_id
      and m.profile_id = (select auth.uid())
      and m.status = 'active'
  );
$$;

comment on function private.is_active_team_member(uuid) is
  'True when the calling user holds an active membership in the given team.';

create function private.is_active_team_coach(p_team_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.team_memberships as m
    where m.team_id = p_team_id
      and m.profile_id = (select auth.uid())
      and m.status = 'active'
      and m.role = 'coach'
  );
$$;

comment on function private.is_active_team_coach(uuid) is
  'True when the calling user holds an active coach membership in the given team.';

-- Identity visibility only. This is not, and must not become, a health-data
-- authorization helper.
create function private.is_coached_by_current_user(p_profile_id uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.team_memberships as target
    join public.team_memberships as caller
      on caller.team_id = target.team_id
    where target.profile_id = p_profile_id
      and target.status = 'active'
      and caller.profile_id = (select auth.uid())
      and caller.status = 'active'
      and caller.role = 'coach'
  );
$$;

comment on function private.is_coached_by_current_user(uuid) is
  'True when the target profile holds an active membership in a team where the calling user holds an active coach membership. Identity visibility only; never sufficient for health data.';

-- ---------------------------------------------------------------------------
-- Function privileges
-- ---------------------------------------------------------------------------

revoke all on function private.handle_new_user() from public;
revoke all on function private.is_active_team_member(uuid) from public;
revoke all on function private.is_active_team_coach(uuid) from public;
revoke all on function private.is_coached_by_current_user(uuid) from public;

-- Policies evaluate as the calling role, so authenticated needs schema usage
-- plus execute on exactly the three read helpers. anon receives nothing.
grant usage on schema private to authenticated;

grant execute on function private.is_active_team_member(uuid) to authenticated;
grant execute on function private.is_active_team_coach(uuid) to authenticated;
grant execute on function private.is_coached_by_current_user(uuid) to authenticated;

-- The signup trigger is invoked by the auth service, never by a client.
do $$
begin
  if exists (select 1 from pg_catalog.pg_roles where rolname = 'supabase_auth_admin') then
    execute 'grant usage on schema private to supabase_auth_admin';
    execute 'grant execute on function private.handle_new_user() to supabase_auth_admin';
  end if;
end;
$$;

-- ---------------------------------------------------------------------------
-- Table privileges
-- ---------------------------------------------------------------------------
--
-- Supabase default privileges grant ALL on new public tables to anon and
-- authenticated. Revoke that first, then grant back only SELECT to
-- authenticated. anon keeps nothing, so an anonymous read fails on privilege
-- before RLS is even consulted.

revoke all on table public.profiles from anon, authenticated;
revoke all on table public.teams from anon, authenticated;
revoke all on table public.team_memberships from anon, authenticated;

grant select on table public.profiles to authenticated;
grant select on table public.teams to authenticated;
grant select on table public.team_memberships to authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.profiles enable row level security;
alter table public.teams enable row level security;
alter table public.team_memberships enable row level security;

-- Self, or a profile the caller actively coaches. An athlete therefore sees no
-- other profile at all, including coach profiles.
create policy profiles_select_self_or_coached
on public.profiles
for select
to authenticated
using (
  id = (select auth.uid())
  or private.is_coached_by_current_user(id)
);

-- A team row and its name are visible only while the caller holds an active
-- membership in that team.
create policy teams_select_active_member
on public.teams
for select
to authenticated
using (private.is_active_team_member(id));

-- Own rows, including revoked ones, plus active rows in a team the caller
-- actively coaches.
create policy team_memberships_select_own_or_coached
on public.team_memberships
for select
to authenticated
using (
  profile_id = (select auth.uid())
  or (status = 'active' and private.is_active_team_coach(team_id))
);

-- No INSERT, UPDATE, or DELETE policy is created for any role in TASK-008.
-- Team and membership administration is a later, separately reviewed task.
