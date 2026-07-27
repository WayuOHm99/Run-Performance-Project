/**
 * The authentication gate.
 *
 * One pure function turns "what do we currently know" into "what may the user
 * see". Keeping it pure is what makes the fail-closed guarantee testable: every
 * state below is enumerated in the unit tests, and route authorization is
 * derived from the resulting status rather than re-implemented per screen.
 *
 * Two ordering rules in `resolveAuthGate` are load-bearing:
 *
 *   1. Restoration is checked before everything else, so neither a protected
 *      shell nor the sign-in screen can flash while storage is still being
 *      read.
 *   2. A load failure is checked before the membership count, so a network or
 *      RLS error can never be mistaken for "this user has no active team". The
 *      two states look similar in the data (no rows either way) and mean
 *      opposite things to the user.
 */

import { hasCompletedProfile, type DisplayNameRejection } from "./display-name";
import {
  resolveAuthorizedRoles,
  type AppRole,
  type MembershipRecord,
} from "./roles";
import type { AuthenticatedIdentity } from "./session";

export type AccountLoad =
  | { readonly kind: "loading" }
  | { readonly kind: "error"; readonly message: string }
  | {
      readonly kind: "loaded";
      readonly displayName: string | null;
      readonly memberships: readonly MembershipRecord[];
    };

export type AuthGateInput = {
  /** False until the stored session has been read, however that turns out. */
  readonly sessionRestored: boolean;
  /** Null means signed out, including after a corrupt session was rejected. */
  readonly identity: AuthenticatedIdentity | null;
  /** Set by a sign-up that returned no session. */
  readonly awaitingEmailConfirmation: boolean;
  readonly account: AccountLoad;
};

export type AuthGate =
  | { readonly status: "restoring" }
  | { readonly status: "signed-out" }
  | { readonly status: "check-email" }
  | { readonly status: "loading-account"; readonly userId: string }
  | {
      readonly status: "account-error";
      readonly userId: string;
      readonly message: string;
    }
  | { readonly status: "onboarding"; readonly userId: string }
  | { readonly status: "no-active-team"; readonly userId: string }
  | {
      readonly status: "ready";
      readonly userId: string;
      readonly authorizedRoles: readonly AppRole[];
    };

export type AuthGateStatus = AuthGate["status"];

export function resolveAuthGate(input: AuthGateInput): AuthGate {
  if (!input.sessionRestored) {
    return { status: "restoring" };
  }

  if (input.identity === null) {
    return input.awaitingEmailConfirmation
      ? { status: "check-email" }
      : { status: "signed-out" };
  }

  const userId = input.identity.userId;

  if (input.account.kind === "loading") {
    return { status: "loading-account", userId };
  }

  // Deliberately ahead of every membership check below.
  if (input.account.kind === "error") {
    return { status: "account-error", userId, message: input.account.message };
  }

  if (!hasCompletedProfile(input.account.displayName)) {
    return { status: "onboarding", userId };
  }

  const authorizedRoles = resolveAuthorizedRoles(input.account.memberships);

  if (authorizedRoles.length === 0) {
    return { status: "no-active-team", userId };
  }

  return { status: "ready", userId, authorizedRoles };
}

/**
 * Whether a role area may be entered.
 *
 * Fails closed by construction: only `ready` is ever considered, so restoring,
 * signed-out, check-email, loading, error, onboarding, and no-active-team all
 * deny without needing their own rule. Direct navigation to `/athlete` or
 * `/coach` is gated on this.
 *
 * This is UX protection only. PostgreSQL grants and RLS remain the
 * authorization boundary, and this function must never be the reason a query is
 * considered safe.
 */
export function canEnterRoleArea(gate: AuthGate, role: AppRole): boolean {
  if (gate.status !== "ready") {
    return false;
  }

  return gate.authorizedRoles.includes(role);
}

/** True only where an authenticated identity exists and the profile is set. */
export function canEditProfile(gate: AuthGate): boolean {
  return (
    gate.status === "ready" ||
    gate.status === "no-active-team" ||
    gate.status === "onboarding"
  );
}

/** A dual-role user is the only case that needs a chooser. */
export function needsRoleChoice(gate: AuthGate): boolean {
  return gate.status === "ready" && gate.authorizedRoles.length > 1;
}

export const ROUTES = {
  signIn: "/sign-in",
  signUp: "/sign-up",
  checkEmail: "/check-email",
  loading: "/loading",
  onboarding: "/onboarding",
  pending: "/pending",
  chooseRole: "/choose-role",
  profile: "/profile",
  athlete: "/athlete",
  coach: "/coach",
} as const;

export type AppRoute = (typeof ROUTES)[keyof typeof ROUTES];

const ROLE_ROUTES: Record<AppRole, AppRoute> = {
  athlete: ROUTES.athlete,
  coach: ROUTES.coach,
};

export function roleRoute(role: AppRole): AppRoute {
  return ROLE_ROUTES[role];
}

/**
 * Where the user belongs right now.
 *
 * A single-role user lands straight in their shell; only a genuinely dual-role
 * user is asked to choose, and that choice is view state that never widens what
 * the database returns.
 */
export function resolveLandingRoute(gate: AuthGate): AppRoute {
  switch (gate.status) {
    case "restoring":
      return ROUTES.loading;
    case "signed-out":
      return ROUTES.signIn;
    case "check-email":
      return ROUTES.checkEmail;
    case "loading-account":
      return ROUTES.loading;
    case "account-error":
      return ROUTES.loading;
    case "onboarding":
      return ROUTES.onboarding;
    case "no-active-team":
      return ROUTES.pending;
    case "ready": {
      if (gate.authorizedRoles.length > 1) {
        return ROUTES.chooseRole;
      }

      const [only] = gate.authorizedRoles;

      // Unreachable: `ready` implies at least one role. Falling back to the
      // pending screen rather than asserting keeps the failure closed.
      return only === undefined ? ROUTES.pending : roleRoute(only);
    }
  }
}

export type { AppRole, MembershipRecord, DisplayNameRejection };
