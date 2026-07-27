import { describe, expect, it } from "vitest";

import {
  INITIAL_AUTH_STATE,
  authIdentity,
  authReducer,
  canApplyValidation,
  isAuthSettled,
  isVerificationPending,
  type AuthEvent,
  type AuthState,
} from "./auth-state";
import { canEnterRoleArea, resolveAuthGate } from "./gate";
import type { AuthenticatedIdentity, SessionCandidate } from "./session";

const USER_A: AuthenticatedIdentity = { userId: "user-a" };
const USER_B: AuthenticatedIdentity = { userId: "user-b" };

function candidate(userId: string): SessionCandidate {
  return { unverifiedUserId: userId };
}

function run(
  events: readonly AuthEvent[],
  from = INITIAL_AUTH_STATE,
): AuthState {
  return events.reduce(authReducer, from);
}

/** Observe a signal and let its validation settle, in one step. */
function settledAs(
  token: number,
  identity: AuthenticatedIdentity | null,
  from = INITIAL_AUTH_STATE,
): AuthState {
  return run(
    [
      {
        type: "signal-observed",
        token,
        candidate: identity === null ? null : candidate(identity.userId),
      },
      { type: "validation-settled", token, identity },
    ],
    from,
  );
}

describe("initial state", () => {
  it("starts restoring, with no identity and nothing settled", () => {
    expect(authIdentity(INITIAL_AUTH_STATE)).toBeNull();
    expect(isAuthSettled(INITIAL_AUTH_STATE)).toBe(false);
    expect(isVerificationPending(INITIAL_AUTH_STATE)).toBe(false);
  });
});

describe("a newer signal invalidates the current identity immediately", () => {
  it("clears a verified identity as soon as a newer signal is observed", () => {
    const verified = settledAs(1, USER_A);

    expect(authIdentity(verified)).toEqual(USER_A);

    const pending = authReducer(verified, {
      type: "signal-observed",
      token: 2,
      candidate: candidate("user-a"),
    });

    // Not after validation finishes. Now.
    expect(authIdentity(pending)).toBeNull();
    expect(isAuthSettled(pending)).toBe(false);
    expect(isVerificationPending(pending)).toBe(true);
  });

  it("produces a non-authorized gate state while validation is pending", () => {
    const pending = authReducer(settledAs(1, USER_A), {
      type: "signal-observed",
      token: 2,
      candidate: candidate("user-a"),
    });

    const gate = resolveAuthGate({
      sessionRestored: isAuthSettled(pending),
      identity: authIdentity(pending),
      awaitingEmailConfirmation: false,
      account: {
        kind: "loaded",
        displayName: "athlete-a",
        memberships: [{ team_id: "team-1", role: "athlete", status: "active" }],
      },
    });

    // The gate reports restoring, so no athlete, coach, chooser, or profile
    // route can render on the previous user's identity.
    expect(gate.status).toBe("restoring");
    expect(canEnterRoleArea(gate, "athlete")).toBe(false);
    expect(canEnterRoleArea(gate, "coach")).toBe(false);
  });

  it("blocks protected routing on a sign-out signal without waiting", () => {
    const signedOut = authReducer(settledAs(1, USER_A), {
      type: "signal-observed",
      token: 2,
      candidate: null,
    });

    expect(authIdentity(signedOut)).toBeNull();
    expect(isAuthSettled(signedOut)).toBe(false);
  });

  it("ignores an out-of-order observation", () => {
    // A slow restore resolving after a newer event must not reopen an older
    // signal.
    const state = run([
      { type: "signal-observed", token: 2, candidate: candidate("user-b") },
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
    ]);

    expect(state.latestToken).toBe(2);
    expect(state.candidate).toEqual(candidate("user-b"));
  });

  it("ignores a repeated observation of the same token", () => {
    const first = authReducer(INITIAL_AUTH_STATE, {
      type: "signal-observed",
      token: 1,
      candidate: candidate("user-a"),
    });
    const repeated = authReducer(first, {
      type: "signal-observed",
      token: 1,
      candidate: candidate("user-b"),
    });

    expect(repeated).toBe(first);
  });
});

describe("only the latest signal's result may apply", () => {
  /**
   * The exact interleaving from the review.
   *
   * The previous guard was `resultToken > lastAppliedToken`, which passes here
   * (2 > 1) and reapplied user A after a sign-out had already been observed.
   */
  it("rejects token 2 when token 3 was observed first and token 2 resolves late", () => {
    const state = run([
      // 1. User A verified; applied token = 1.
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "validation-settled", token: 1, identity: USER_A },
      // 2. Validation for signal token 2 starts.
      { type: "signal-observed", token: 2, candidate: candidate("user-a") },
      // 3. A sign-out signal token 3 is observed. 4. It has not settled yet.
      { type: "signal-observed", token: 3, candidate: null },
      // 5. Token 2 resolves, before token 3.
      { type: "validation-settled", token: 2, identity: USER_A },
    ]);

    // 6. It must be rejected, and no old identity may become active.
    expect(authIdentity(state)).toBeNull();
    expect(isAuthSettled(state)).toBe(false);
    expect(state.appliedToken).toBe(1);
    expect(state.latestToken).toBe(3);
  });

  it("keeps the gate closed after the stale result was rejected", () => {
    const state = run([
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "validation-settled", token: 1, identity: USER_A },
      { type: "signal-observed", token: 2, candidate: candidate("user-a") },
      { type: "signal-observed", token: 3, candidate: null },
      { type: "validation-settled", token: 2, identity: USER_A },
    ]);

    const gate = resolveAuthGate({
      sessionRestored: isAuthSettled(state),
      identity: authIdentity(state),
      awaitingEmailConfirmation: false,
      account: { kind: "loading" },
    });

    expect(gate.status).toBe("restoring");
    expect(canEnterRoleArea(gate, "athlete")).toBe(false);
    expect(canEnterRoleArea(gate, "coach")).toBe(false);
  });

  it("settles signed out once token 3 resolves", () => {
    const state = run([
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "validation-settled", token: 1, identity: USER_A },
      { type: "signal-observed", token: 2, candidate: candidate("user-a") },
      { type: "signal-observed", token: 3, candidate: null },
      { type: "validation-settled", token: 2, identity: USER_A },
      { type: "validation-settled", token: 3, identity: null },
    ]);

    expect(authIdentity(state)).toBeNull();
    expect(isAuthSettled(state)).toBe(true);
    expect(state.appliedToken).toBe(3);
  });

  it("never reapplies user A after a user-B event was observed", () => {
    const state = run([
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "validation-settled", token: 1, identity: USER_A },
      // User B signs in on the same device.
      { type: "signal-observed", token: 2, candidate: candidate("user-b") },
      // User A's in-flight validation resolves late.
      { type: "validation-settled", token: 1, identity: USER_A },
    ]);

    expect(authIdentity(state)).toBeNull();

    const settled = authReducer(state, {
      type: "validation-settled",
      token: 2,
      identity: USER_B,
    });

    expect(authIdentity(settled)).toEqual(USER_B);
  });

  it("does not expose user A at any point after the user-B signal", () => {
    const events: AuthEvent[] = [
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "validation-settled", token: 1, identity: USER_A },
      { type: "signal-observed", token: 2, candidate: candidate("user-b") },
      { type: "validation-settled", token: 1, identity: USER_A },
      { type: "validation-settled", token: 2, identity: USER_B },
    ];

    let state = INITIAL_AUTH_STATE;
    const exposed: (string | null)[] = [];

    for (const event of events) {
      state = authReducer(state, event);
      exposed.push(authIdentity(state)?.userId ?? null);
    }

    // After the user-B signal at index 2, user A never reappears.
    expect(exposed).toEqual([null, "user-a", null, null, "user-b"]);
    expect(exposed.slice(2)).not.toContain("user-a");
  });

  it("rejects a result older than the latest observed signal", () => {
    const state = run([
      { type: "signal-observed", token: 3, candidate: candidate("user-a") },
      { type: "validation-settled", token: 2, identity: USER_A },
    ]);

    expect(authIdentity(state)).toBeNull();
    expect(isAuthSettled(state)).toBe(false);
  });

  it("rejects a result newer than the latest observed signal", () => {
    const state = run([
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "validation-settled", token: 5, identity: USER_A },
    ]);

    expect(authIdentity(state)).toBeNull();
  });

  it("rejects a repeated result for the token already applied", () => {
    const settled = settledAs(1, USER_A);
    const repeated = authReducer(settled, {
      type: "validation-settled",
      token: 1,
      identity: USER_B,
    });

    expect(repeated).toBe(settled);
    expect(authIdentity(repeated)).toEqual(USER_A);
  });

  it("applies results in order when several resolve out of order", () => {
    const state = run([
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "signal-observed", token: 2, candidate: candidate("user-a") },
      { type: "signal-observed", token: 3, candidate: candidate("user-b") },
      { type: "validation-settled", token: 2, identity: USER_A },
      { type: "validation-settled", token: 1, identity: USER_A },
      { type: "validation-settled", token: 3, identity: USER_B },
    ]);

    expect(authIdentity(state)).toEqual(USER_B);
    expect(state.appliedToken).toBe(3);
  });
});

describe("canApplyValidation", () => {
  const verifying: AuthState = {
    phase: "verifying",
    latestToken: 3,
    appliedToken: 1,
    identity: null,
    candidate: candidate("user-a"),
  };

  it("requires equality with the latest observed token", () => {
    expect(canApplyValidation(3, verifying)).toBe(true);
    // Newer than the applied token, but no longer the latest signal. This is
    // precisely the case the old guard let through.
    expect(canApplyValidation(2, verifying)).toBe(false);
  });

  it("rejects a token older than the applied one", () => {
    expect(canApplyValidation(1, verifying)).toBe(false);
    expect(canApplyValidation(0, verifying)).toBe(false);
  });

  it("rejects a token newer than the latest observed signal", () => {
    expect(canApplyValidation(4, verifying)).toBe(false);
  });

  it("rejects re-applying the token already applied", () => {
    const settled: AuthState = {
      phase: "settled",
      latestToken: 2,
      appliedToken: 2,
      identity: USER_A,
      candidate: candidate("user-a"),
    };

    expect(canApplyValidation(2, settled)).toBe(false);
  });
});

describe("cancelled and unmounted results", () => {
  it("ignores a result dispatched for a superseded token", () => {
    // The provider also drops these via its `active` flag; the reducer is the
    // second line of defence, so a missed cleanup cannot corrupt the state.
    const state = run([
      { type: "signal-observed", token: 1, candidate: candidate("user-a") },
      { type: "signal-observed", token: 2, candidate: null },
      { type: "validation-settled", token: 1, identity: USER_A },
    ]);

    expect(authIdentity(state)).toBeNull();
    expect(state.appliedToken).toBe(0);
  });

  it("leaves state untouched for every rejected event", () => {
    const before = run([
      { type: "signal-observed", token: 2, candidate: candidate("user-a") },
    ]);

    const rejected: AuthEvent[] = [
      { type: "signal-observed", token: 1, candidate: candidate("user-b") },
      { type: "signal-observed", token: 2, candidate: null },
      { type: "validation-settled", token: 1, identity: USER_B },
      { type: "validation-settled", token: 3, identity: USER_B },
    ];

    for (const event of rejected) {
      // Reference equality: a rejected event must not even allocate a new
      // state, so it cannot trigger a re-render or an effect re-run.
      expect(authReducer(before, event)).toBe(before);
    }
  });
});

describe("sign-out-initiated", () => {
  it("settles immediately as signed out rather than waiting to verify", () => {
    const signedIn = settledAs(1, USER_A);

    const after = authReducer(signedIn, {
      type: "sign-out-initiated",
      token: 2,
    });

    expect(after.identity).toBeNull();
    expect(after.candidate).toBeNull();
    // Settled, so the gate reports signed-out instead of stranding the user on
    // the loading screen when Supabase never emits SIGNED_OUT.
    expect(isAuthSettled(after)).toBe(true);
    expect(isVerificationPending(after)).toBe(false);
  });

  it("advances appliedToken so an in-flight validation cannot reapply", () => {
    const signedIn = settledAs(1, USER_A);

    const after = authReducer(signedIn, {
      type: "sign-out-initiated",
      token: 3,
    });

    expect(after.latestToken).toBe(3);
    expect(after.appliedToken).toBe(3);
    // Token 2's validation was in flight across the sign-out.
    expect(canApplyValidation(2, after)).toBe(false);
    // And the sign-out's own token cannot be reused to apply an identity.
    expect(canApplyValidation(3, after)).toBe(false);
  });

  it("is ignored when a newer signal has already been observed", () => {
    const newer = run([
      { type: "signal-observed", token: 5, candidate: candidate("user-b") },
    ]);

    // A stale sign-out must not outrank a newer observation.
    expect(authReducer(newer, { type: "sign-out-initiated", token: 4 })).toBe(
      newer,
    );
  });

  it("keeps both role areas closed afterwards", () => {
    const after = authReducer(settledAs(1, USER_A), {
      type: "sign-out-initiated",
      token: 2,
    });

    const gate = resolveAuthGate({
      sessionRestored: isAuthSettled(after),
      identity: authIdentity(after),
      awaitingEmailConfirmation: false,
      account: {
        kind: "loaded",
        displayName: "Athlete A",
        memberships: [
          { team_id: "t1", role: "athlete", status: "active" },
          { team_id: "t2", role: "coach", status: "active" },
        ],
      },
    });

    expect(gate.status).toBe("signed-out");
    expect(canEnterRoleArea(gate, "athlete")).toBe(false);
    expect(canEnterRoleArea(gate, "coach")).toBe(false);
  });
});

describe("identity exposure is guarded by the phase", () => {
  it("never exposes an identity while restoring", () => {
    expect(
      authIdentity({ ...INITIAL_AUTH_STATE, identity: USER_A }),
    ).toBeNull();
  });

  it("never exposes an identity while verifying", () => {
    const verifying: AuthState = {
      phase: "verifying",
      latestToken: 2,
      appliedToken: 1,
      identity: USER_A,
      candidate: candidate("user-a"),
    };

    // Defence in depth: the reducer already clears the field on every new
    // signal, and the selector refuses to read it in this phase regardless.
    expect(authIdentity(verifying)).toBeNull();
  });
});
