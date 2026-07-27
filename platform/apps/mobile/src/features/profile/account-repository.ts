/**
 * Profile and membership reads, and the display-name write.
 *
 * The client is injected, so these functions are unit-tested against a
 * hand-written double with no network.
 *
 * The distinction this module exists to preserve: **a failure is not an empty
 * result.** A user with no active membership and a user whose membership query
 * failed both end up with zero usable rows, but the first should see the
 * pending screen and the second must see a retry. Every failure path therefore
 * raises `AccountDataError` instead of returning an empty list.
 */

import { validateDisplayName } from "../auth/display-name";
import {
  classifyDataError,
  dataErrorMessage,
  type DataFailure,
} from "../auth/errors";
import type { MembershipRecord } from "../auth/roles";
import type { AppSupabaseClient } from "../../lib/supabase/app-client";

export type { AppSupabaseClient };

export type AccountSnapshot = {
  readonly userId: string;
  readonly displayName: string | null;
  readonly memberships: readonly MembershipRecord[];
};

export class AccountDataError extends Error {
  override readonly name = "AccountDataError";
  readonly failure: DataFailure;

  constructor(failure: DataFailure, message: string) {
    super(message);
    this.failure = failure;
  }
}

function toAccountDataError(error: unknown): AccountDataError {
  return new AccountDataError(
    classifyDataError(error),
    dataErrorMessage(error),
  );
}

/**
 * Loads only the caller's own profile and membership rows.
 *
 * Both queries are filtered to `userId` as well as being covered by RLS. The
 * filter is not the security control -- the policies are -- but it keeps the
 * intent legible and avoids relying on a policy to scope a query that was
 * written as if it were unscoped.
 */
export async function loadAccount(
  client: AppSupabaseClient,
  userId: string,
): Promise<AccountSnapshot> {
  const profileResult = await client
    .from("profiles")
    .select("id, display_name")
    .eq("id", userId)
    .maybeSingle();

  if (profileResult.error) {
    throw toAccountDataError(profileResult.error);
  }

  if (profileResult.data === null) {
    // The signup trigger guarantees a row, so its absence means the read was
    // refused or the account is gone. Either way it is a recoverable error
    // state, never "this user simply has no name yet".
    throw new AccountDataError("denied", dataErrorMessage({ code: "42501" }));
  }

  const membershipResult = await client
    .from("team_memberships")
    .select("team_id, role, status")
    .eq("profile_id", userId);

  if (membershipResult.error) {
    throw toAccountDataError(membershipResult.error);
  }

  return {
    userId,
    displayName: profileResult.data.display_name,
    // An empty array here is a real answer: this user holds no membership.
    memberships: membershipResult.data ?? [],
  };
}

/**
 * Writes the caller's own display name.
 *
 * Validated client-side first so an obviously bad value is not sent, then
 * written through the `profiles_update_self` policy, which is the actual
 * enforcement. The update touches `display_name` alone; adding any other column
 * would be refused by the column-level grant.
 */
export async function saveDisplayName(
  client: AppSupabaseClient,
  userId: string,
  rawDisplayName: string,
): Promise<string> {
  const validated = validateDisplayName(rawDisplayName);

  if (!validated.ok) {
    throw new AccountDataError("unknown", dataErrorMessage(null));
  }

  const { data, error } = await client
    .from("profiles")
    .update({ display_name: validated.value })
    .eq("id", userId)
    .select("display_name")
    .maybeSingle();

  if (error) {
    throw toAccountDataError(error);
  }

  if (data === null) {
    // Zero rows means the policy filtered the row out rather than raising,
    // which is what a mismatched user id looks like.
    throw new AccountDataError("denied", dataErrorMessage({ code: "42501" }));
  }

  return data.display_name ?? validated.value;
}
