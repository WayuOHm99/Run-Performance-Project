/**
 * Loading the caller's check-in sharing state, and the two write RPCs.
 *
 * The client is injected, so every path below is unit-tested against a
 * hand-written double with no network and no local database.
 *
 * Five rules this module exists to hold:
 *
 * 1. **A failure is not an empty list and not "sharing off".** "You hold no
 *    active athlete membership" and "the read was refused" both produce zero
 *    usable rows, but the first is the empty state and the second must be a
 *    retry. An empty array is returned only for a genuine absence; every failure
 *    raises `SharingDataError`.
 *
 * 2. **The athlete id is never taken from the UI.** `loadCheckInSharing` requires
 *    the verified authenticated user id from the auth provider and filters both
 *    reads to it. The RLS policies `team_memberships_select_own_or_coached` and
 *    `sharing_grants_select_own_history` are the actual boundary, but a query
 *    written as if it were unscoped must not rely on a policy to scope it. The
 *    two write paths take **no** athlete id at all: `grant_team_data_sharing` and
 *    `revoke_team_data_sharing` derive the athlete from `auth.uid()`, which is why
 *    no forged owner is expressible here.
 *
 * 3. **The category is a constant.** Both RPCs are called with
 *    `CHECK_IN_CATEGORY` and nothing else, and the grant read filters on it, so
 *    this feature can neither ask for nor observe `workout_summary` or
 *    `sleep_summary` consent.
 *
 * 4. **Only a server-loaded team id can be written.** Both write functions take a
 *    branded `SharingTarget`, which `resolveSharingTarget` produces only from a
 *    successfully loaded list.
 *
 * 5. **Nothing raw escapes, and nothing logs.** Resolved `{ error }` responses,
 *    synchronous throws, rejected builders and thenables, and unexpected internal
 *    failures are all collapsed to a `SharingDataError` carrying a fixed string.
 */

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

import {
  CHECK_IN_CATEGORY,
  REQUIRED_ROLE,
  REQUIRED_STATUS,
  parseCheckInSharingList,
  targetTeamId,
  type SharingTarget,
  type TeamSharingState,
} from "./domain";
import {
  SharingDataError,
  sharingErrorFrom,
  type SharingIntent,
} from "./errors";

export type { AppSupabaseClient };

const MEMBERSHIP_TABLE = "team_memberships";
const GRANT_TABLE = "sharing_grants";

/**
 * The only membership fields read.
 *
 * `teams(name)` is the team label, resolved through `teams_select_active_member`
 * rather than displayed from the id. No profile, timestamp, or membership id is
 * selected, because none is needed to decide a control's state.
 */
const MEMBERSHIP_COLUMNS = "team_id, role, status, teams(name)";

/**
 * The only grant fields read.
 *
 * `revoked_at` is filtered on but not selected: the UI must never receive revoked
 * history, and the category is re-validated so a mislabelled row cannot be read as
 * check-in consent.
 */
const GRANT_COLUMNS = "team_id, data_category";

const GRANT_RPC = "grant_team_data_sharing";
const REVOKE_RPC = "revoke_team_data_sharing";

/**
 * The shape of the non-health sentinel both RPCs return.
 *
 * `grant_team_data_sharing` returns the id of the caller's active grant row, and
 * a grant counts as successful only when that arrives. It is a row identifier, not
 * a measurement, and it is discarded immediately — it is never returned to the
 * caller, cached, or displayed. Matching the shape rather than merely "some
 * string" is what stops a proxy or a stubbed transport from resolving `""`,
 * `"ok"`, or an error object and having it read as consent.
 */
const SENTINEL_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isGrantSentinel(value: unknown): boolean {
  return typeof value === "string" && SENTINEL_PATTERN.test(value);
}

function isVerifiedUserId(userId: unknown): userId is string {
  return typeof userId === "string" && userId.length > 0;
}

/**
 * Collapses anything thrown inside this module into a sanitized error.
 *
 * `{ error }` in a resolved PostgREST response is the *expected* failure shape but
 * not the only one: a client method can throw synchronously, a builder can reject,
 * a thenable can settle with a rejection, and a bug in this module can raise a
 * `TypeError`. Any of those escaping unsanitized would put a raw server object —
 * with its message, `details`, `hint`, and possibly the RPC arguments — into
 * TanStack Query's error state, from which the section would read it.
 *
 * An already-sanitized `SharingDataError` passes through unchanged so its `intent`
 * and `failure` survive. Everything else is classified from its
 * `code`/`status`/constructor name only; nothing from it is retained.
 */
function sanitize(intent: SharingIntent, error: unknown): SharingDataError {
  return error instanceof SharingDataError
    ? error
    : sharingErrorFrom(intent, error);
}

/**
 * Loads every active athlete team with its current check-in sharing state.
 *
 * An empty array means "no active athlete membership" and is a real answer. Any
 * failure, including a malformed or inconsistent response, raises
 * `SharingDataError`.
 */
export async function loadCheckInSharing(
  client: AppSupabaseClient,
  userId: string,
): Promise<readonly TeamSharingState[]> {
  try {
    return await performLoad(client, userId);
  } catch (error) {
    throw sanitize("load", error);
  }
}

async function performLoad(
  client: AppSupabaseClient,
  userId: string,
): Promise<readonly TeamSharingState[]> {
  if (!isVerifiedUserId(userId)) {
    // Refused before any client call, so a missing or malformed identity is never
    // sent as a filter and no query is issued for a placeholder owner.
    throw new SharingDataError("load", "unknown");
  }

  // Memberships first, deliberately. Reading grants first would leave a window in
  // which a membership activated between the two reads produced a grant with no
  // matching membership, which `parseCheckInSharingList` refuses.
  const membershipResult = await client
    .from(MEMBERSHIP_TABLE)
    .select(MEMBERSHIP_COLUMNS)
    .eq("profile_id", userId)
    .eq("role", REQUIRED_ROLE)
    .eq("status", REQUIRED_STATUS);

  if (membershipResult.error) {
    throw sharingErrorFrom("load", membershipResult.error);
  }

  const grantResult = await client
    .from(GRANT_TABLE)
    .select(GRANT_COLUMNS)
    .eq("athlete_profile_id", userId)
    .eq("data_category", CHECK_IN_CATEGORY)
    .is("revoked_at", null);

  if (grantResult.error) {
    throw sharingErrorFrom("load", grantResult.error);
  }

  const parsed = parseCheckInSharingList({
    membershipRows: membershipResult.data,
    grantRows: grantResult.data,
  });

  if (!parsed.ok) {
    // Fail closed. Rendering the valid subset would show "not sharing" for a team
    // whose grant row was the malformed one.
    throw new SharingDataError("load", "unknown");
  }

  return parsed.value;
}

/**
 * Grants the selected team read access to the caller's check-in data.
 *
 * Resolves to `void` on a server-confirmed grant. The RPC is idempotent by
 * TASK-011 decision, so a duplicate call returns the existing active row's id and
 * leaves exactly one active grant.
 */
export async function grantCheckInSharing(
  client: AppSupabaseClient,
  target: SharingTarget,
): Promise<void> {
  try {
    const { data, error } = await client.rpc(GRANT_RPC, {
      p_team_id: targetTeamId(target),
      p_data_category: CHECK_IN_CATEGORY,
    });

    if (error) {
      throw sharingErrorFrom("grant", error);
    }

    // Read through `unknown` on purpose: the generated signature describes what
    // the database promises, not what actually arrived over the wire.
    const sentinel: unknown = data;

    if (!isGrantSentinel(sentinel)) {
      // No sentinel means no proof the grant exists, so it must not read as
      // success. The value itself is discarded here and never travels further.
      throw new SharingDataError("grant", "unknown");
    }
  } catch (error) {
    throw sanitize("grant", error);
  }
}

/**
 * Revokes the selected team's access to the caller's check-in data.
 *
 * Resolves to `void`. `revoke_team_data_sharing` returns the revoked row's id, or
 * `null` when there was no active grant — a repeat revoke, or a revoke racing the
 * membership trigger. Both are success: the server-confirmed state afterwards is
 * "not sharing" either way, which is precisely what the athlete asked for.
 */
export async function revokeCheckInSharing(
  client: AppSupabaseClient,
  target: SharingTarget,
): Promise<void> {
  try {
    const { data, error } = await client.rpc(REVOKE_RPC, {
      p_team_id: targetTeamId(target),
      p_data_category: CHECK_IN_CATEGORY,
    });

    if (error) {
      throw sharingErrorFrom("revoke", error);
    }

    const sentinel: unknown = data;

    if (sentinel !== null && !isGrantSentinel(sentinel)) {
      // Neither "revoked this row" nor "there was nothing to revoke", so the
      // response is not one this feature understands.
      throw new SharingDataError("revoke", "unknown");
    }
  } catch (error) {
    throw sanitize("revoke", error);
  }
}
