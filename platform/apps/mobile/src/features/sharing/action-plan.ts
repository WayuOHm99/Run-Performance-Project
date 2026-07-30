/**
 * What a press on a team's sharing control does.
 *
 * Pure and tested directly, which is what keeps `sharing-section.tsx` to wiring
 * only. Two decisions live here:
 *
 * 1. **A press while an action is in flight is refused.** The controls are already
 *    unpressable, but that is a visual guard; this is the one that makes a
 *    duplicate press a no-op rather than a second consent operation. It refuses a
 *    second press on the *same* team and on any *other* team, so one in-flight
 *    action cannot be interleaved with a cross-team one.
 *
 * 2. **The direction comes from server-loaded state, not from the press.** The
 *    caller supplies only which team was pressed; whether that means grant or
 *    revoke is read from the loaded list. A control rendered from stale state
 *    therefore cannot send "grant" for a team that is already sharing, and a team
 *    the server did not return produces no variables at all.
 *
 * Nothing here performs I/O, reads an identity, or holds a health value.
 */

import type { TeamSharingState } from "./domain";
import type { SharingActionVariables } from "./query-options";

export type SharingActionPlan =
  | { readonly accepted: false; readonly reason: "busy" | "unknown-team" }
  | { readonly accepted: true; readonly variables: SharingActionVariables };

const BUSY: SharingActionPlan = { accepted: false, reason: "busy" };
const UNKNOWN_TEAM: SharingActionPlan = {
  accepted: false,
  reason: "unknown-team",
};

export function planSharingAction(args: {
  /** True while any sharing action is in flight. */
  readonly busy: boolean;
  /** The currently loaded, server-confirmed list. */
  readonly teams: readonly TeamSharingState[];
  readonly teamId: string;
}): SharingActionPlan {
  if (args.busy) {
    return BUSY;
  }

  const team = args.teams.find((candidate) => candidate.teamId === args.teamId);

  if (team === undefined) {
    return UNKNOWN_TEAM;
  }

  return {
    accepted: true,
    variables: {
      teamId: team.teamId,
      action: team.sharing ? "revoke" : "grant",
    },
  };
}
