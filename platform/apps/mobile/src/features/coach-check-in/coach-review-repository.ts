/**
 * The three-stage read that produces the coach's daily check-in review.
 *
 * The client is injected, so every path below is unit-tested against a
 * hand-written double with no network and no local database.
 *
 * Six rules this module exists to hold:
 *
 * 1. **A failure is not an empty list.** "You coach no active team", "nobody
 *    shares with you", and "the read was refused" all produce zero usable rows,
 *    but only the first two are answers. Every failure raises
 *    `CoachReviewDataError`; an empty array is returned only for a genuine
 *    absence.
 *
 * 2. **The coach id is never taken from the UI.** `loadCoachCheckInReview`
 *    requires the verified authenticated user id from the auth provider and
 *    filters stage a to it. `team_memberships_select_own_or_coached`,
 *    `sharing_grants_select_active_for_coach`, `profiles_select_self_or_coached`,
 *    and `daily_check_ins_select_shared_for_coach` are the actual boundary, but a
 *    query written as if it were unscoped must not rely on a policy to scope it.
 *
 * 3. **The stages are ordered so the health-bearing read is last, and are each
 *    fully validated before the next begins.** Stage c is the only read that can
 *    return a protected value, and it is issued only after the caller's coach
 *    memberships and the exact consent pairs have both been validated. It is not
 *    issued at all when there is no active grant, so a coach with no consenting
 *    athlete never causes a health-bearing query to exist.
 *
 * 4. **Explicit columns only, never `*`.** Each stage names exactly the fields
 *    decision 5 permits. No row id, `created_at`, `updated_at`, or `revoked_at`
 *    is selected; `revoked_at` is filtered on and deliberately not returned.
 *
 * 5. **"Latest" is the server's claim, and it is checked.** Stage c uses the
 *    referenced-table `order`/`limit` pair so the database returns one row per
 *    athlete, and `composeCoachReview` refuses a response carrying more. Without
 *    both halves, "latest" would be an arbitrary row from an athlete's history.
 *
 * 6. **Nothing raw escapes, and nothing logs.** Resolved `{ error }` responses,
 *    synchronous throws, rejected builders and thenables, and unexpected internal
 *    failures are all collapsed to a `CoachReviewDataError` carrying a fixed
 *    string.
 */

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

import {
  ACTIVE_STATUS,
  CHECK_IN_CATEGORY,
  COACH_ROLE,
  GRANT_REQUEST_LIMIT,
  MAX_EMBEDDED_CHECK_INS,
  athleteIdsToRead,
  composeCoachReview,
  parseCoachedTeams,
  parseGrantPairs,
  type CoachReviewReject,
  type CoachReviewTeam,
} from "./domain";
import { CoachReviewDataError, coachReviewErrorFrom } from "./errors";

export type { AppSupabaseClient };

const MEMBERSHIP_TABLE = "team_memberships";
const GRANT_TABLE = "sharing_grants";
const PROFILE_TABLE = "profiles";

/**
 * Stage a columns.
 *
 * `teams(name)` is the team label, resolved through `teams_select_active_member`
 * rather than displayed from the id. No membership id, profile id, or timestamp is
 * selected, because none is needed to decide what a coach may see.
 */
const MEMBERSHIP_COLUMNS = "team_id, role, status, teams(name)";

/**
 * Stage b columns.
 *
 * `revoked_at` is filtered on but not selected: revoked consent history must never
 * reach a coach, and the category is re-validated downstream so a mislabelled row
 * cannot be read as check-in consent. `granted_at` is not selected either — when
 * consent began is not something this screen shows.
 */
const GRANT_COLUMNS = "team_id, athlete_profile_id, data_category";

/**
 * Stage c columns, including the embedded latest check-in.
 *
 * `id` is the join key that materializes a grant pair; it is never rendered. The
 * embed names the four permitted check-in fields and nothing else, so the row id,
 * `athlete_profile_id`, `created_at`, and `updated_at` never leave the database.
 */
const PROFILE_COLUMNS =
  "id, display_name, daily_check_ins(check_in_date, rpe, overall_feeling, pain_status)";

/** The embedded relationship stage c orders and limits. */
const CHECK_IN_RELATION = "daily_check_ins";

/** The athlete's own civil date, and the column "latest" is defined by. */
const CHECK_IN_DATE_COLUMN = "check_in_date";

function isVerifiedUserId(userId: unknown): userId is string {
  return typeof userId === "string" && userId.length > 0;
}

/** Turns a domain rejection into the matching sanitized failure. */
function rejection(reason: CoachReviewReject): CoachReviewDataError {
  return new CoachReviewDataError(
    "load",
    reason === "capacity" ? "capacity" : "unknown",
  );
}

/**
 * Collapses anything thrown inside this module into a sanitized error.
 *
 * `{ error }` in a resolved PostgREST response is the *expected* failure shape but
 * not the only one: a client method can throw synchronously, a builder can reject,
 * a thenable can settle with a rejection, and a bug in this module can raise a
 * `TypeError`. Any of those escaping unsanitized would put a raw server object —
 * with its message, `details`, `hint`, and possibly an athlete id — into TanStack
 * Query's error state, from which the section would read it.
 *
 * An already-sanitized `CoachReviewDataError` passes through unchanged so its
 * `failure` survives, which is what keeps the capacity wording distinct from a
 * retryable one. Everything else is classified from its `code`/`status`/constructor
 * name only; nothing from it is retained.
 */
function sanitize(error: unknown): CoachReviewDataError {
  return error instanceof CoachReviewDataError
    ? error
    : coachReviewErrorFrom("load", error);
}

/**
 * Loads every team the caller actively coaches, with the latest shared check-in of
 * every athlete who actively consents to that exact team.
 *
 * An empty array means "you coach no active team" and is a real answer. A team with
 * an empty athlete list means "nobody in this team actively shares" and is also a
 * real answer. Any failure, including a malformed or inconsistent response, raises
 * `CoachReviewDataError`.
 */
export async function loadCoachCheckInReview(
  client: AppSupabaseClient,
  userId: string,
): Promise<readonly CoachReviewTeam[]> {
  try {
    return await performLoad(client, userId);
  } catch (error) {
    throw sanitize(error);
  }
}

async function performLoad(
  client: AppSupabaseClient,
  userId: string,
): Promise<readonly CoachReviewTeam[]> {
  if (!isVerifiedUserId(userId)) {
    // Refused before any client call, so a missing or malformed identity is never
    // sent as a filter and no query is issued for a placeholder caller.
    throw new CoachReviewDataError("load", "unknown");
  }

  // ---------------------------------------------------------------------------
  // Stage a — the caller's active coach memberships and their team names.
  // ---------------------------------------------------------------------------
  const membershipResult = await client
    .from(MEMBERSHIP_TABLE)
    .select(MEMBERSHIP_COLUMNS)
    .eq("profile_id", userId)
    .eq("role", COACH_ROLE)
    .eq("status", ACTIVE_STATUS);

  if (membershipResult.error) {
    throw coachReviewErrorFrom("load", membershipResult.error);
  }

  const parsedTeams = parseCoachedTeams(membershipResult.data);

  if (!parsedTeams.ok) {
    throw rejection(parsedTeams.reason);
  }

  const teams = parsedTeams.value;

  if (teams.length === 0) {
    // The genuine no-active-coach-team state. Stage b is not issued: there is no
    // team to scope it to, and an unscoped grant read would match the caller's own
    // athlete-side consent through `sharing_grants_select_own_history`.
    return [];
  }

  const coachedTeamIds = teams.map((team) => team.teamId);

  // ---------------------------------------------------------------------------
  // Stage b — the active check_in consent pairs, scoped to those exact teams.
  // ---------------------------------------------------------------------------
  const grantResult = await client
    .from(GRANT_TABLE)
    .select(GRANT_COLUMNS)
    .eq("data_category", CHECK_IN_CATEGORY)
    .is("revoked_at", null)
    .in("team_id", coachedTeamIds)
    .limit(GRANT_REQUEST_LIMIT);

  if (grantResult.error) {
    throw coachReviewErrorFrom("load", grantResult.error);
  }

  const parsedPairs = parseGrantPairs({
    rows: grantResult.data,
    coachedTeamIds: new Set(coachedTeamIds),
    callerUserId: userId,
  });

  if (!parsedPairs.ok) {
    throw rejection(parsedPairs.reason);
  }

  const pairs = parsedPairs.value;

  if (pairs.length === 0) {
    // Teams exist but nobody actively shares. Stage c — the only health-bearing
    // read — is not issued at all, so no protected value is requested on behalf of
    // a coach who has been granted nothing.
    return composeOrThrow({ teams, pairs, profileRows: [] });
  }

  // ---------------------------------------------------------------------------
  // Stage c — the strictly required profiles and their latest visible check-in.
  // ---------------------------------------------------------------------------
  const athleteIds = athleteIdsToRead(pairs);

  const profileResult = await client
    .from(PROFILE_TABLE)
    .select(PROFILE_COLUMNS)
    .in("id", athleteIds)
    // "Latest" is defined by the athlete's own recorded civil date, descending,
    // and capped at one row per athlete. Both halves are required: the order
    // without the limit returns a whole history, and the limit without the order
    // returns an arbitrary row from it.
    .order(CHECK_IN_DATE_COLUMN, {
      referencedTable: CHECK_IN_RELATION,
      ascending: false,
    })
    .limit(MAX_EMBEDDED_CHECK_INS, { referencedTable: CHECK_IN_RELATION });

  if (profileResult.error) {
    throw coachReviewErrorFrom("load", profileResult.error);
  }

  return composeOrThrow({ teams, pairs, profileRows: profileResult.data });
}

function composeOrThrow(args: {
  readonly teams: Parameters<typeof composeCoachReview>[0]["teams"];
  readonly pairs: Parameters<typeof composeCoachReview>[0]["pairs"];
  readonly profileRows: unknown;
}): readonly CoachReviewTeam[] {
  const composed = composeCoachReview(args);

  if (!composed.ok) {
    // Fail closed. Rendering the valid subset would show an athlete as "not
    // checked in" when the truth is that their row was the malformed one.
    throw rejection(composed.reason);
  }

  return composed.value;
}
