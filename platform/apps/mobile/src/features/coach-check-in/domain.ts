/**
 * The coach-review domain: the three validated stages, and the composition that
 * turns them into the coach-facing list.
 *
 * This module is where decisions 3, 4, 5, 6, and 7 actually live. Six rules it
 * exists to hold:
 *
 * 1. **The category is a constant, not a parameter.** `CHECK_IN_CATEGORY` is the
 *    only value this feature reads or accepts. `workout_summary` and
 *    `sleep_summary` exist in the TASK-011 check constraint and are deliberately
 *    unreachable from here, so a coach cannot see consent they were not given.
 *
 * 2. **A grant pair, not roster visibility, associates a health row with a team.**
 *    `profiles_select_self_or_coached` makes every coached athlete's *identity*
 *    visible across every team the caller coaches, and
 *    `daily_check_ins_select_shared_for_coach` is athlete-scoped rather than
 *    team-scoped. Composing on visibility alone would therefore file an athlete's
 *    check-in under a team they never shared it with. The composition below walks
 *    the validated `(team_id, athlete_profile_id)` grant pairs instead, so a row
 *    can only ever appear under the exact team whose grant produced it.
 *
 * 3. **Validation is fail-closed and total.** A malformed membership, team name,
 *    grant, profile, display name, date, or health value, a duplicate, an unknown
 *    category, a grant naming an uncoached team, a missing expected profile, or a
 *    second embedded check-in row all reject the **whole** list. A partially valid
 *    list is worse than an error: a dropped pair reads as "this athlete has not
 *    checked in", which is a false statement about a person's health record.
 *
 * 4. **A self-targeted grant among coached teams is impossible, so it is a
 *    failure.** `team_memberships` is unique on `(team_id, profile_id)`, so one
 *    person cannot hold both a coach and an athlete membership in the same team.
 *    A grant row naming the caller as the athlete, in a team the caller coaches,
 *    therefore cannot be a real database state — and it is exactly the shape a
 *    dual-role user's own check-in would have to take to leak in through the coach
 *    list. It is refused rather than filtered out.
 *
 * 5. **Capacity is refused, never truncated.** Above `MAX_SHARING_PAIRS` the whole
 *    load fails. A truncated list would understate what a coach can see and would
 *    do so silently.
 *
 * 6. **No UTC conversion, ever.** `check_in_date` is the athlete's own civil date.
 *    It is validated by `isLocalDateString` and carried through as the string it
 *    arrived as; nothing here constructs a `Date`, and nothing here calls the
 *    result "today".
 *
 * Nothing in this module logs, formats, or stringifies a health value.
 */

import { parseCheckInRow, type DailyCheckIn } from "../check-in/domain";
import { isLocalDateString } from "../check-in/local-date";

/** The only category this feature reads. */
export const CHECK_IN_CATEGORY = "check_in";

/** The only membership role and status a coached team may be built from. */
export const COACH_ROLE = "coach";
export const ACTIVE_STATUS = "active";

/**
 * The approved maximum scope, in active athlete/team sharing pairs.
 *
 * Stage b requests one more than this so overflow is *detectable* rather than
 * indistinguishable from a full page.
 */
export const MAX_SHARING_PAIRS = 100;

/** How many grant rows stage b asks for: the cap plus the overflow probe. */
export const GRANT_REQUEST_LIMIT = MAX_SHARING_PAIRS + 1;

/** The maximum embedded check-in rows a valid profile row may carry. */
export const MAX_EMBEDDED_CHECK_INS = 1;

/** One team the verified caller actively coaches. */
export type CoachedTeam = {
  readonly teamId: string;
  readonly teamName: string;
};

/** One active `check_in` consent: this athlete, for this exact team. */
export type GrantPair = {
  readonly teamId: string;
  readonly athleteProfileId: string;
};

/**
 * One latest check-in, as recorded by the athlete.
 *
 * The three health values plus the athlete's own civil date. No row id, no
 * `created_at`, no `updated_at`, no note, and no interpretation.
 */
export type SharedCheckIn = DailyCheckIn & {
  readonly checkInDate: string;
};

/**
 * One athlete under one team.
 *
 * `athleteProfileId` exists solely as a React reconciliation key and a join key.
 * It is never rendered — decision 9 forbids displaying a raw UUID — which the
 * source scan enforces structurally.
 */
export type CoachReviewAthlete = {
  readonly athleteProfileId: string;
  readonly athleteName: string;
  /** `null` is the one and only "has not checked in yet" state. */
  readonly checkIn: SharedCheckIn | null;
};

/** One team, with every athlete who actively shares check-in data with it. */
export type CoachReviewTeam = {
  readonly teamId: string;
  readonly teamName: string;
  readonly athletes: readonly CoachReviewAthlete[];
};

/**
 * Why a stage was rejected.
 *
 * Two reasons only, because the coach needs two different things: `invalid` is
 * retryable, `capacity` is not and must not be worded as if it were.
 */
export type CoachReviewReject = "invalid" | "capacity";

/**
 * A parse result rather than a thrown error or a nullable value.
 *
 * An empty list is a real answer at every stage — "you coach no team", "nobody
 * shares with you" — so a rejection must not also be an empty list.
 */
export type CoachReviewParse<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly reason: CoachReviewReject };

const INVALID = { ok: false, reason: "invalid" } as const;
const OVER_CAPACITY = { ok: false, reason: "capacity" } as const;

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
 * with its own id: "never display a raw team id as the team label" has to hold
 * even when RLS hides the team row.
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

/**
 * Validates one coach membership row.
 *
 * The query already filters on role and status, so an unexpected value here means
 * the response is not what was asked for. It is refused rather than trusted — the
 * filter is a statement of intent, not the check.
 */
function parseCoachMembershipRow(row: unknown): CoachedTeam | null {
  const teamId = readField(row, "team_id");
  const role = readField(row, "role");
  const status = readField(row, "status");
  const teamName = readEmbeddedTeamName(row);

  if (
    !isNonEmptyString(teamId) ||
    role !== COACH_ROLE ||
    status !== ACTIVE_STATUS ||
    teamName === null
  ) {
    return null;
  }

  return { teamId, teamName };
}

/**
 * Stage a: the verified caller's active coach memberships, with team names.
 *
 * An empty array is the genuine "you coach no active team" state. A duplicate team
 * id is a rejection: `team_memberships` is unique on `(team_id, profile_id)`, so a
 * repeat means the response is not the database's actual state.
 */
export function parseCoachedTeams(
  rows: unknown,
): CoachReviewParse<readonly CoachedTeam[]> {
  if (!Array.isArray(rows)) {
    return INVALID;
  }

  const teams = new Map<string, CoachedTeam>();

  for (const row of rows) {
    const team = parseCoachMembershipRow(row);

    if (team === null || teams.has(team.teamId)) {
      return INVALID;
    }

    teams.set(team.teamId, team);
  }

  return { ok: true, value: [...teams.values()] };
}

/**
 * Stage b: the active `check_in` grant pairs visible to this coach.
 *
 * Every rejection below fails the whole load:
 *
 * - a malformed row, or a category that is not exactly `check_in` — a mislabelled
 *   row must never be read as check-in consent;
 * - a team the caller does not actively coach — `sharing_grants_select_own_history`
 *   also matches the caller's *own* grants, so a response reaching this point with
 *   an uncoached team means the `in(...)` filter did not hold and the association
 *   between grant and team can no longer be trusted;
 * - a duplicate `(team, athlete)` pair — `sharing_grants_one_active_idx` allows one
 *   active row per team, athlete, and category;
 * - a pair naming the caller as the athlete (see rule 4 in the module comment);
 * - more than `MAX_SHARING_PAIRS` pairs, which is refused as `capacity`.
 */
export function parseGrantPairs(args: {
  readonly rows: unknown;
  readonly coachedTeamIds: ReadonlySet<string>;
  /** The verified caller. Used only to refuse an impossible self-target. */
  readonly callerUserId: string;
}): CoachReviewParse<readonly GrantPair[]> {
  const { rows, coachedTeamIds, callerUserId } = args;

  if (!Array.isArray(rows)) {
    return INVALID;
  }

  // Checked before any row is interpreted, so an oversized response is refused
  // rather than partially parsed and then dropped.
  if (rows.length > MAX_SHARING_PAIRS) {
    return OVER_CAPACITY;
  }

  const pairs: GrantPair[] = [];
  const seen = new Set<string>();

  for (const row of rows) {
    const teamId = readField(row, "team_id");
    const athleteProfileId = readField(row, "athlete_profile_id");
    const category = readField(row, "data_category");

    if (
      !isNonEmptyString(teamId) ||
      !isNonEmptyString(athleteProfileId) ||
      category !== CHECK_IN_CATEGORY ||
      !coachedTeamIds.has(teamId) ||
      athleteProfileId === callerUserId
    ) {
      return INVALID;
    }

    const pairKey = `${teamId} ${athleteProfileId}`;

    if (seen.has(pairKey)) {
      return INVALID;
    }

    seen.add(pairKey);
    pairs.push({ teamId, athleteProfileId });
  }

  return { ok: true, value: pairs };
}

/** The distinct athlete profile ids stage c must read, in first-seen order. */
export function athleteIdsToRead(
  pairs: readonly GrantPair[],
): readonly string[] {
  return [...new Set(pairs.map((pair) => pair.athleteProfileId))];
}

/** One athlete's validated profile and latest check-in, before materialization. */
type AthleteRecord = {
  readonly athleteName: string;
  readonly checkIn: SharedCheckIn | null;
};

/**
 * Validates the embedded latest check-in of one profile row.
 *
 * Returns `undefined` for a rejection so it stays distinguishable from `null`,
 * which is the meaningful "this athlete has not checked in" answer.
 *
 * Only an array is accepted: `profiles → daily_check_ins` is a to-many embed, so a
 * non-array response is not the shape that was asked for. Two or more rows means
 * the referenced-table `limit(1)` did not apply, in which case "latest" is no
 * longer a claim this client can make — and rendering the first element would be
 * showing an arbitrary historical record, which decision 4 forbids outright.
 */
function parseEmbeddedCheckIn(row: unknown): SharedCheckIn | null | undefined {
  const embedded = readField(row, "daily_check_ins");

  if (!Array.isArray(embedded)) {
    return undefined;
  }

  if (embedded.length === 0) {
    return null;
  }

  if (embedded.length > MAX_EMBEDDED_CHECK_INS) {
    return undefined;
  }

  const [latest] = embedded;
  const checkInDate = readField(latest, "check_in_date");

  // Validated as a civil date string and kept as one. No `Date` is constructed
  // here, so no UTC boundary can move the athlete's recorded day.
  if (!isLocalDateString(checkInDate)) {
    return undefined;
  }

  const parsed = parseCheckInRow(latest);

  if (!parsed.ok) {
    return undefined;
  }

  return {
    checkInDate,
    rpe: parsed.value.rpe,
    overallFeeling: parsed.value.overallFeeling,
    painStatus: parsed.value.painStatus,
  };
}

/**
 * Stage c: the profile rows, keyed by athlete id.
 *
 * The returned id set must equal the requested id set **exactly**. A missing
 * profile means a pair could not be materialized, and an unexpected one means the
 * response is not the answer to the query that was sent; both are refusals. A
 * blank `display_name` is also a refusal, because the alternative is labelling a
 * person with their raw UUID.
 */
function parseProfileRows(args: {
  readonly rows: unknown;
  readonly requestedIds: readonly string[];
}): CoachReviewParse<ReadonlyMap<string, AthleteRecord>> {
  const { rows, requestedIds } = args;

  if (!Array.isArray(rows)) {
    return INVALID;
  }

  const requested = new Set(requestedIds);
  const records = new Map<string, AthleteRecord>();

  for (const row of rows) {
    const athleteProfileId = readField(row, "id");
    const athleteName = readField(row, "display_name");

    if (
      !isNonEmptyString(athleteProfileId) ||
      !isNonEmptyString(athleteName) ||
      !requested.has(athleteProfileId) ||
      records.has(athleteProfileId)
    ) {
      return INVALID;
    }

    const checkIn = parseEmbeddedCheckIn(row);

    if (checkIn === undefined) {
      return INVALID;
    }

    records.set(athleteProfileId, { athleteName, checkIn });
  }

  if (records.size !== requested.size) {
    // A profile that was asked for and did not come back. Rendering the rest
    // would silently drop a consenting athlete from their coach's list.
    return INVALID;
  }

  return { ok: true, value: records };
}

function compareStrings(left: string, right: string): number {
  if (left === right) {
    return 0;
  }

  return left < right ? -1 : 1;
}

/**
 * Composes the three validated stages into the coach-facing list.
 *
 * The walk is over **grant pairs**, so an athlete who actively shares with two
 * coached teams is materialized under both exact teams from one deduplicated
 * profile read, and an athlete visible on the roster without a grant appears
 * nowhere at all.
 *
 * Teams with no grant pair are still returned, carrying an empty athlete list.
 * That is what lets the UI distinguish "this team has no consenting athlete" from
 * "you coach no team", which decision 7 requires as two separate states.
 *
 * Order is fixed: team name, then team id, then athlete display name, then athlete
 * id. Names alone are not unique, so the ids are the tiebreak that keeps the list
 * from reshuffling between loads.
 */
export function composeCoachReview(args: {
  readonly teams: readonly CoachedTeam[];
  readonly pairs: readonly GrantPair[];
  readonly profileRows: unknown;
}): CoachReviewParse<readonly CoachReviewTeam[]> {
  const { teams, pairs, profileRows } = args;

  const parsedProfiles = parseProfileRows({
    rows: profileRows,
    requestedIds: athleteIdsToRead(pairs),
  });

  if (!parsedProfiles.ok) {
    return parsedProfiles;
  }

  const records = parsedProfiles.value;
  const byTeam = new Map<string, CoachReviewAthlete[]>(
    teams.map((team) => [team.teamId, []]),
  );

  for (const pair of pairs) {
    const record = records.get(pair.athleteProfileId);
    const bucket = byTeam.get(pair.teamId);

    if (record === undefined || bucket === undefined) {
      // `parseGrantPairs` already refused an uncoached team and
      // `parseProfileRows` already refused a missing profile, so neither is
      // reachable from a validated input. Kept as a total branch rather than an
      // assertion: a future caller composing unvalidated stages must fail closed,
      // not throw an unsanitized error.
      return INVALID;
    }

    bucket.push({
      athleteProfileId: pair.athleteProfileId,
      athleteName: record.athleteName,
      checkIn: record.checkIn,
    });
  }

  const value = teams
    .map<CoachReviewTeam>((team) => ({
      teamId: team.teamId,
      teamName: team.teamName,
      athletes: (byTeam.get(team.teamId) ?? []).sort(
        (left, right) =>
          compareStrings(left.athleteName, right.athleteName) ||
          compareStrings(left.athleteProfileId, right.athleteProfileId),
      ),
    }))
    .sort(
      (left, right) =>
        compareStrings(left.teamName, right.teamName) ||
        compareStrings(left.teamId, right.teamId),
    );

  return { ok: true, value };
}

/** How many athlete/team pairs a composed list holds. A count, never a value. */
export function sharedPairCount(teams: readonly CoachReviewTeam[]): number {
  return teams.reduce((total, team) => total + team.athletes.length, 0);
}
