-- TASK-009: Self-service display-name editing.
--
-- TASK-008 deliberately deferred all client profile editing. TASK-009 needs a
-- user to set and later edit their own display name during onboarding, so this
-- migration opens the narrowest possible hole in that surface:
--
--   * a COLUMN-level UPDATE grant on display_name only, so an UPDATE that
--     touches id or created_at fails with 42501 before RLS is consulted;
--   * one UPDATE policy restricted to the row owner in both USING and
--     WITH CHECK.
--
-- Everything else from TASK-008 is unchanged. profiles remains INSERT- and
-- DELETE-denied for clients, teams and team_memberships remain read-only, anon
-- still holds no privilege at all, and no role is ever derived from a JWT claim
-- or auth metadata.
--
-- This migration does not edit the TASK-008 migration.

-- ---------------------------------------------------------------------------
-- Column privilege
-- ---------------------------------------------------------------------------
--
-- Deliberately a column grant, not a table grant. It is the mechanism that
-- keeps id and created_at non-updatable: PostgreSQL checks column privileges
-- before evaluating row policies, so a client attempting to rewrite either
-- column is refused on privilege rather than filtered by RLS.
grant update (display_name) on table public.profiles to authenticated;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
--
-- USING selects the rows the caller may update at all; WITH CHECK validates the
-- row that results. Both are required: USING alone would let a caller move a
-- row they own into a state they should not be able to produce.
--
-- WITH CHECK also refuses to store a null or blank name, so a client cannot
-- clear an onboarded profile back to the pre-onboarding state and re-enter the
-- app in an inconsistent identity. The automatic signup path is unaffected,
-- because private.handle_new_user() performs an INSERT as a SECURITY DEFINER
-- and is not subject to this policy.
--
-- The bounds mirror the existing profiles_display_name_valid constraint, which
-- is retained and remains the authoritative shape check.
create policy profiles_update_self
on public.profiles
for update
to authenticated
using (id = (select auth.uid()))
with check (
  id = (select auth.uid())
  and display_name is not null
  and char_length(btrim(display_name)) between 1 and 80
  and char_length(display_name) <= 80
);

comment on policy profiles_update_self on public.profiles is
  'A user may update only their own display_name, and only to a valid non-blank value. Paired with a column-level UPDATE grant so id and created_at stay non-updatable.';

-- No INSERT or DELETE policy is added for public.profiles.
-- No grant or policy of any kind is added for public.teams or
-- public.team_memberships; membership administration remains a later,
-- separately reviewed task.
-- No service-role policy, JWT role claim, or auth-metadata role is introduced.
