/**
 * Role resolution.
 *
 * This is the single place a role may come from, and it accepts exactly one
 * input: membership rows returned by the database under RLS. A role is never
 * derived from auth metadata, the email address, local storage, a JWT claim, or
 * a UI choice, because none of those are re-checked by PostgreSQL on the next
 * query and so none of them survive a revocation.
 *
 * The function is pure so it can be tested exhaustively without a client, a
 * network, or a rendered screen.
 */

export const APP_ROLES = ["athlete", "coach"] as const;

export type AppRole = (typeof APP_ROLES)[number];

/**
 * The shape actually selected from public.team_memberships. Deliberately
 * permissive about `role` and `status`: the database constrains them, but this
 * function must stay correct if it is ever handed an unexpected value.
 */
export type MembershipRecord = {
  team_id: string;
  role: string;
  status: string;
};

const ACTIVE_STATUS = "active";

function isAppRole(value: string): value is AppRole {
  return (APP_ROLES as readonly string[]).includes(value);
}

/**
 * Returns the roles the caller may actually enter, in a stable order.
 *
 * Only `status = 'active'` rows count, so a revoked membership disappears from
 * role resolution as soon as a refreshed query stops returning it as active.
 * An unknown role value is ignored rather than trusted.
 */
export function resolveAuthorizedRoles(
  memberships: readonly MembershipRecord[] | null | undefined,
): readonly AppRole[] {
  if (!memberships) {
    return [];
  }

  const granted = new Set<AppRole>();

  for (const membership of memberships) {
    if (membership.status !== ACTIVE_STATUS) {
      continue;
    }

    if (isAppRole(membership.role)) {
      granted.add(membership.role);
    }
  }

  // Iterate APP_ROLES rather than the input so the order is stable regardless
  // of row order, which keeps the role chooser from reshuffling between loads.
  return APP_ROLES.filter((role) => granted.has(role));
}

export function isAuthorizedForRole(
  authorizedRoles: readonly AppRole[],
  role: AppRole,
): boolean {
  return authorizedRoles.includes(role);
}

export function hasAnyRole(authorizedRoles: readonly AppRole[]): boolean {
  return authorizedRoles.length > 0;
}
