/**
 * The identity boundary for the sharing section's mutation observer, and the one
 * place its rendered outcome is derived.
 *
 * ## Why this module exists
 *
 * Round 1 proved that a mid-flight identity change cannot redirect the *write* or
 * the *refetch*: `mutationFn` is read once when execution begins, so the key it
 * captures and the RPC it calls belong to the identity the action was started as.
 * That is still true and is still tested.
 *
 * It is not sufficient. A `MutationObserver` that is still **active** survives the
 * removal of its mutation from the `MutationCache`, which is what
 * `clearAuthScopedQueries` does on an identity change. `MutationCache.clear()`
 * removes the mutation from the cache but does not abort it and does not detach its
 * observers, so when the old action finally settles the *same* observer transitions
 * to success or error and reports the **previous account's** result and variables —
 * verified directly against the installed TanStack version. Rendered through the
 * section, that would show the new account:
 *
 * - the previous account's success or failure banner;
 * - controls still disabled by the previous account's pending request;
 * - the previous account's team in the busy slot.
 *
 * No cross-account database write is possible, so this is a UI, privacy, and
 * correctness defect rather than an authorization one. It is still a defect: one
 * person is shown another person's consent outcome.
 *
 * ## The fix
 *
 * `sharingIdentityBoundaryKey` produces a React `key` for the component that owns
 * the hooks. When the verified identity changes, the key changes, React **unmounts**
 * the old subtree — destroying its mutation observer and its query observer — and
 * mounts a fresh one. A freshly constructed observer has no current mutation, so it
 * starts idle. There is no reset effect, so there is no frame in which the new
 * identity renders the old outcome; the old observer is gone before the new one
 * exists.
 *
 * `MutationCache.clear()` remains necessary and is unchanged — it stops the old
 * mutation from being *found* again — but it is not what makes the UI safe, and
 * relying on it alone was the defect.
 *
 * `readSharingOutcome` is the single place the section turns observer state into
 * something rendered. Keeping it pure and total means the "new identity begins
 * fully idle" property is asserted directly against a real observer result rather
 * than inferred from a rendered tree.
 *
 * Nothing here performs I/O, reads an identity, holds a health value, or logs.
 */

import type {
  SharingAction,
  SharingActionResult,
  SharingActionVariables,
} from "./query-options";

/**
 * The boundary key used while no verified identity exists.
 *
 * Signing out is an identity change like any other: the key changes, so the
 * observer is destroyed and a signed-out render can never inherit the previous
 * account's outcome.
 */
export const NO_IDENTITY_BOUNDARY = "sharing-boundary:no-identity";

const IDENTITY_PREFIX = "sharing-boundary:identity:";

/**
 * The React key for the sharing subtree that owns the query and mutation hooks.
 *
 * Distinct per verified user id and distinct from the signed-out state. This value
 * is a reconciliation key only: React never renders it, and it is not a query key,
 * so it participates in no cache lookup.
 */
export function sharingIdentityBoundaryKey(userId: string | undefined): string {
  return userId === undefined || userId.length === 0
    ? NO_IDENTITY_BOUNDARY
    : `${IDENTITY_PREFIX}${userId}`;
}

/**
 * Whether a transition between two identities remounts the sharing subtree.
 *
 * Exists so the remount condition is testable as a fact rather than as a claim
 * about React: if this returns true, the key changed, and a changed key is what
 * makes React destroy the old observer.
 */
export function sharingBoundaryChanged(
  previousUserId: string | undefined,
  nextUserId: string | undefined,
): boolean {
  return (
    sharingIdentityBoundaryKey(previousUserId) !==
    sharingIdentityBoundaryKey(nextUserId)
  );
}

/**
 * The mutation state the section reads, structurally typed.
 *
 * Matches both a `useMutation` result and a `MutationObserver` result, which is
 * what lets the regression tests feed a genuine observer result through the exact
 * function the component uses.
 */
export type SharingMutationState = {
  readonly isPending: boolean;
  readonly isSuccess: boolean;
  readonly isError: boolean;
  readonly data: SharingActionResult | undefined;
  readonly variables: SharingActionVariables | undefined;
};

/** Everything the section renders from mutation state, and nothing more. */
export type SharingOutcomeView = {
  /** True while an action is in flight. Disables every control. */
  readonly busy: boolean;
  /** The team whose control shows the working label, if any. */
  readonly busyTeamId: string | undefined;
  /** The direction to congratulate, or null for no success banner. */
  readonly successAction: SharingAction | null;
  /** The direction that failed, or null for no error banner. */
  readonly failedAction: SharingAction | null;
};

/** A completely idle view: no banner, no busy control, nothing disabled. */
export const IDLE_SHARING_OUTCOME: SharingOutcomeView = {
  busy: false,
  busyTeamId: undefined,
  successAction: null,
  failedAction: null,
};

/**
 * Derives the rendered outcome from mutation state.
 *
 * Deliberately total and defensive. Each branch requires **both** the status flag
 * and the value it needs, so a state that claims success without data, or reports an
 * error without variables, renders no banner rather than a partial one. A fresh
 * observer under a new identity satisfies none of the branches, which is what makes
 * "the new identity begins idle" a property of this function instead of a hope
 * about lifecycle ordering.
 */
export function readSharingOutcome(
  state: SharingMutationState,
): SharingOutcomeView {
  if (state.isPending) {
    // Busy is checked first: an in-flight action must disable every control even
    // if a previous outcome is still nominally present.
    return {
      busy: true,
      busyTeamId: state.variables?.teamId,
      successAction: null,
      failedAction: null,
    };
  }

  if (state.isSuccess && state.data !== undefined) {
    return {
      busy: false,
      busyTeamId: undefined,
      successAction: state.data.action,
      failedAction: null,
    };
  }

  if (state.isError && state.variables !== undefined) {
    return {
      busy: false,
      busyTeamId: undefined,
      successAction: null,
      failedAction: state.variables.action,
    };
  }

  return IDLE_SHARING_OUTCOME;
}

/** True when nothing from any action would be rendered. */
export function isIdleSharingOutcome(view: SharingOutcomeView): boolean {
  return (
    !view.busy &&
    view.busyTeamId === undefined &&
    view.successAction === null &&
    view.failedAction === null
  );
}
