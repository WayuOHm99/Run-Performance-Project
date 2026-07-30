/**
 * The sharing domain: one category, one branded write target, and the strict
 * validation that turns two server responses into the athlete-facing list.
 *
 * Nothing here is a health value. A `TeamSharingState` carries a team id, a team
 * name, and one boolean; the three protected check-in values are named only in
 * `copy.ts`, as explanation, and are never read by this feature.
 *
 * Three rules this module exists to hold:
 *
 * 1. **The category is a constant, not a parameter.** `CHECK_IN_CATEGORY` is the
 *    only value this feature ever sends or accepts. `workout_summary` and
 *    `sleep_summary` exist in the TASK-011 check constraint and are deliberately
 *    unreachable from here, so a caller cannot widen the consent being asked for.
 *
 * 2. **Validation is fail-closed and total.** A missing team name, an unexpected
 *    role or status, a category that is not `check_in`, a duplicate active state,
 *    or a grant naming a team the caller holds no active athlete membership in
 *    all reject the *whole* list. A partially trustworthy authorization view is
 *    worse than an error, because "not sharing" is exactly what a dropped row
 *    would look like.
 *
 * 3. **A write target can only come from a loaded list.** `SharingTarget` is
 *    branded and `resolveSharingTarget` is the only way to obtain one, so the
 *    repository cannot be handed a team id the server never returned. There is no
 *    athlete-id parameter anywhere in this module; the athlete is `auth.uid()`
 *    inside the RPC.
 */

/** The only category this feature reads or writes. */
export const CHECK_IN_CATEGORY = "check_in";

export type SharingCategory = typeof CHECK_IN_CATEGORY;

/** The only membership role and status a control may be built from. */
export const REQUIRED_ROLE = "athlete";
export const REQUIRED_STATUS = "active";

/** One row of the section: a team, its name, and whether sharing is on. */
export type TeamSharingState = {
  readonly teamId: string;
  readonly teamName: string;
  readonly sharing: boolean;
};

/**
 * The brand that makes a write target unforgeable in the type system.
 *
 * Declared and never assigned: it exists only as a property key no other module
 * can name, so `{ teamId }` is not assignable to `SharingTarget` from outside.
 */
declare const SERVER_LOADED: unique symbol;

/** A team id proved to have come from a successful server load. */
export type SharingTarget = {
  readonly teamId: string;
  readonly [SERVER_LOADED]: true;
};

/**
 * A parse result rather than a nullable list.
 *
 * An empty list is a real answer — "you hold no active athlete membership" — so a
 * rejection must not also be an empty list. Callers decide what a rejection
 * means; this module only decides validity.
 */
export type SharingListParse =
  | { readonly ok: true; readonly value: readonly TeamSharingState[] }
  | { readonly ok: false };

const REJECTED: SharingListParse = { ok: false };

function readField(source: unknown, field: string): unknown {
  if (typeof source !== "object" || source === null) {
    return undefined;
  }

  return (source as Record<string, unknown>)[field];
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * The team name from an embedded `teams` resource.
 *
 * PostgREST returns `null` for an embedded row the caller cannot see, which is
 * what an inaccessible team looks like. That is a rejection, not a team to label
 * with its own id: decision "never display a raw team id as the team label" has
 * to hold even when RLS hides the team row.
 *
 * An array is accepted as well as an object because PostgREST shapes a to-one
 * embed as an object but some builder/version combinations return a one-element
 * array. Anything other than exactly one visible row is refused.
 */
function readEmbeddedTeamName(row: unknown): string | null {
  const team = readField(row, "teams");

  if (Array.isArray(team)) {
    if (team.length !== 1) {
      return null;
    }

    const name = readField(team[0], "name");

    return isNonEmptyString(name) ? name : null;
  }

  const name = readField(team, "name");

  return isNonEmptyString(name) ? name : null;
}

/** A membership row reduced to the team it authorizes a control for. */
type ActiveAthleteTeam = {
  readonly teamId: string;
  readonly teamName: string;
};

/**
 * Validates one membership row.
 *
 * The query already filters on role and status, so an unexpected value here means
 * the response is not what was asked for. It is refused rather than trusted — the
 * filter is a statement of intent, not the check.
 */
function parseMembershipRow(row: unknown): ActiveAthleteTeam | null {
  const teamId = readField(row, "team_id");
  const role = readField(row, "role");
  const status = readField(row, "status");
  const teamName = readEmbeddedTeamName(row);

  if (
    !isNonEmptyString(teamId) ||
    role !== REQUIRED_ROLE ||
    status !== REQUIRED_STATUS ||
    teamName === null
  ) {
    return null;
  }

  return { teamId, teamName };
}

/**
 * Validates one grant row and returns the team it belongs to.
 *
 * `revoked_at` is not selected: the query filters on it being null, and returning
 * revoked history to the UI is forbidden. The category is re-checked against the
 * constant so a response carrying `workout_summary` or `sleep_summary` cannot be
 * mistaken for check-in consent.
 */
function parseGrantRow(row: unknown): string | null {
  const teamId = readField(row, "team_id");
  const category = readField(row, "data_category");

  if (!isNonEmptyString(teamId) || category !== CHECK_IN_CATEGORY) {
    return null;
  }

  return teamId;
}

/** Ordered by name, then id, so the section never reshuffles between loads. */
function byTeamNameThenId(
  left: TeamSharingState,
  right: TeamSharingState,
): number {
  if (left.teamName !== right.teamName) {
    return left.teamName < right.teamName ? -1 : 1;
  }

  if (left.teamId === right.teamId) {
    return 0;
  }

  return left.teamId < right.teamId ? -1 : 1;
}

/**
 * Composes the two validated responses into the athlete-facing list.
 *
 * Every rejection below fails the whole list on purpose:
 *
 * - a malformed membership or grant row — a dropped grant row reads as "not
 *   sharing", which silently understates what the coach can see;
 * - a duplicate team in either response — `team_memberships` is unique on
 *   `(team_id, profile_id)` and `sharing_grants_one_active_idx` allows one active
 *   row per team, athlete, and category, so a duplicate means the response is not
 *   the database's actual state;
 * - an active grant for a team with no active athlete membership — the TASK-011
 *   membership trigger revokes grants when a membership stops being an active
 *   athlete membership, so this combination is inconsistent. Refusing it is the
 *   safe direction; the cost is one retryable error if a membership is activated
 *   between the two reads.
 */
export function parseCheckInSharingList(args: {
  readonly membershipRows: unknown;
  readonly grantRows: unknown;
}): SharingListParse {
  const { membershipRows, grantRows } = args;

  if (!Array.isArray(membershipRows) || !Array.isArray(grantRows)) {
    return REJECTED;
  }

  const teams = new Map<string, ActiveAthleteTeam>();

  for (const row of membershipRows) {
    const team = parseMembershipRow(row);

    if (team === null || teams.has(team.teamId)) {
      return REJECTED;
    }

    teams.set(team.teamId, team);
  }

  const granted = new Set<string>();

  for (const row of grantRows) {
    const teamId = parseGrantRow(row);

    if (teamId === null || granted.has(teamId) || !teams.has(teamId)) {
      return REJECTED;
    }

    granted.add(teamId);
  }

  const value = [...teams.values()]
    .map<TeamSharingState>((team) => ({
      teamId: team.teamId,
      teamName: team.teamName,
      sharing: granted.has(team.teamId),
    }))
    .sort(byTeamNameThenId);

  return { ok: true, value };
}

/**
 * Turns a pressed team id into a write target, or refuses it.
 *
 * The only producer of a `SharingTarget`. An id that is not in the loaded list —
 * forged, stale, or belonging to a team the caller does not actively play for —
 * yields `null` and no RPC is attempted. The assertion is the single place the
 * brand is applied, and it is applied only after the id was matched against
 * server-loaded state.
 */
export function resolveSharingTarget(
  teamId: unknown,
  teams: readonly TeamSharingState[],
): SharingTarget | null {
  if (!isNonEmptyString(teamId)) {
    return null;
  }

  const match = teams.find((team) => team.teamId === teamId);

  return match === undefined
    ? null
    : ({ teamId: match.teamId } as SharingTarget);
}

/** The team id a target names. The only way to read it back out. */
export function targetTeamId(target: SharingTarget): string {
  return target.teamId;
}
