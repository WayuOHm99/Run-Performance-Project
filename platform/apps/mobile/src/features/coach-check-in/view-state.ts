/**
 * The identity boundary for the coach-review query observer, and the single place
 * observer state becomes something rendered.
 *
 * ## Why the derivation is a pure function
 *
 * Decision 8 requires that health values are hidden **while a refresh is in
 * flight** and **after a refresh fails**. Both are properties of a state
 * transition, not of a snapshot, and both are exactly the kind of rule that a JSX
 * conditional quietly loses during a later edit. `readCoachReviewView` is
 * therefore total, pure, and the *only* function that can produce a value carrying
 * a check-in. The section renders what it returns and derives nothing itself, so
 * "a refreshing screen shows no health value" is asserted directly against a real
 * `QueryObserver` result rather than inferred from a rendered tree.
 *
 * The ordering of its branches is the whole safety argument:
 *
 *   1. **error first**, before any data check. A failed *refresh* leaves the
 *      previously loaded list in `data` — TanStack keeps the last successful value
 *      alongside the error — so checking data first would keep the old health
 *      values on screen while telling the coach the refresh failed. That is the
 *      one state decision 8 names explicitly, and the branch order is what
 *      prevents it.
 *
 *   2. **fetching second**, again before any data check. A background refetch also
 *      leaves the previous list in `data`. Rendering it would show the coach values
 *      that may already have been revoked, at the exact moment the app is asking
 *      whether they still may see them.
 *
 *   3. Only a settled, error-free, data-bearing state yields `ready`, and `ready`
 *      is the only variant with a `teams` field. A health value is therefore not
 *      merely hidden in the other states — it is **unrepresentable** in them.
 *
 * ## Why an identity key as well as a cleared cache
 *
 * `clearAuthScopedQueries` removes the previous account's entry from the
 * `QueryCache` on an identity change, but an **active** `QueryObserver` is not
 * detached by that removal: an in-flight fetch that settles afterwards transitions
 * the same observer and reports the previous account's result. Rendered through the
 * section, that would show one coach another coach's athletes.
 *
 * `coachReviewIdentityBoundaryKey` produces a React `key` for the component that
 * owns the hook. When the verified identity changes the key changes, React
 * **unmounts** the old subtree — destroying its observer — and mounts a fresh one.
 * A freshly constructed observer has no data, so it starts in `loading`. There is
 * no reset effect, so there is no frame in which the new identity renders the old
 * account's list.
 *
 * Nothing here performs I/O, reads an identity, logs, or persists anything.
 */

import type { CoachReviewTeam } from "./domain";
import { isCapacityFailure } from "./errors";

/**
 * The boundary key used while no verified identity exists.
 *
 * Signing out is an identity change like any other: the key changes, so the
 * observer is destroyed and a signed-out render can never inherit the previous
 * coach's list.
 */
export const NO_IDENTITY_BOUNDARY = "coach-review-boundary:no-identity";

const IDENTITY_PREFIX = "coach-review-boundary:identity:";

/**
 * The React key for the subtree that owns the coach-review query hook.
 *
 * Distinct per verified user id and distinct from the signed-out state. This value
 * is a reconciliation key only: React never renders it, and it is not a query key,
 * so it participates in no cache lookup.
 */
export function coachReviewIdentityBoundaryKey(
  userId: string | undefined,
): string {
  return userId === undefined || userId.length === 0
    ? NO_IDENTITY_BOUNDARY
    : `${IDENTITY_PREFIX}${userId}`;
}

/**
 * Whether a transition between two identities remounts the coach-review subtree.
 *
 * Exists so the remount condition is testable as a fact rather than as a claim
 * about React: if this returns true the key changed, and a changed key is what makes
 * React destroy the old observer.
 */
export function coachReviewBoundaryChanged(
  previousUserId: string | undefined,
  nextUserId: string | undefined,
): boolean {
  return (
    coachReviewIdentityBoundaryKey(previousUserId) !==
    coachReviewIdentityBoundaryKey(nextUserId)
  );
}

/**
 * The query state the section reads, structurally typed.
 *
 * Matches both a `useQuery` result and a `QueryObserver` result, which is what lets
 * the tests feed a genuine observer result through the exact function the component
 * uses.
 */
export type CoachReviewQueryState = {
  readonly data: readonly CoachReviewTeam[] | undefined;
  readonly isFetching: boolean;
  readonly isError: boolean;
  readonly error: unknown;
};

/**
 * Everything the section may render, and nothing more.
 *
 * `teams` exists on exactly one variant. That is deliberate: it makes "no health
 * value is rendered while loading, refreshing, or failing" a type-level property
 * rather than a discipline.
 */
export type CoachReviewView =
  /** First load for this identity. Nothing has ever been shown. */
  | { readonly status: "loading" }
  /**
   * A deliberate or mount-triggered refresh is in flight and a previous list
   * exists internally. It is **not** carried here.
   */
  | { readonly status: "refreshing" }
  /**
   * The load or refresh failed. Any previously loaded list is **not** carried
   * here, so it disappears from the screen along with the failure.
   */
  | { readonly status: "error"; readonly capacity: boolean }
  /** Settled, error-free, and server-confirmed. The only variant with data. */
  | { readonly status: "ready"; readonly teams: readonly CoachReviewTeam[] };

const LOADING: CoachReviewView = { status: "loading" };
const REFRESHING: CoachReviewView = { status: "refreshing" };

/**
 * Derives the rendered view from query state.
 *
 * Total and defensive, with the branch order documented above as the safety
 * argument. `capacity` is surfaced as a boolean rather than an error object so the
 * section can choose non-retryable wording without ever touching the error itself.
 */
export function readCoachReviewView(
  state: CoachReviewQueryState,
): CoachReviewView {
  if (state.isError) {
    // First, and before any data check. `data` still holds the last successful
    // list during a failed refresh; letting it through here is the exact leak
    // decision 8 forbids.
    return { status: "error", capacity: isCapacityFailure(state.error) };
  }

  if (state.isFetching) {
    // Also before any data check, and also on purpose: a refetch must blank the
    // screen rather than keep showing values whose consent is being re-verified.
    return state.data === undefined ? LOADING : REFRESHING;
  }

  if (state.data === undefined) {
    return LOADING;
  }

  return { status: "ready", teams: state.data };
}

/** True when the view carries no health value of any kind. */
export function hidesHealthValues(view: CoachReviewView): boolean {
  return view.status !== "ready";
}

/**
 * The teams a view is allowed to render, which is `[]` unless it is `ready`.
 *
 * A second, redundant gate. It exists so a section that reached for the data
 * without checking the status still renders nothing, and so the "hidden during
 * refresh" property can be asserted as a count.
 */
export function visibleTeams(
  view: CoachReviewView,
): readonly CoachReviewTeam[] {
  return view.status === "ready" ? view.teams : [];
}
