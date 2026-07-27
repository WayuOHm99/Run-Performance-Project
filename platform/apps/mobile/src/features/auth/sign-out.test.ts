/**
 * Integration-oriented tests for sign-out.
 *
 * These drive the **real** reducer (`authReducer`) and the **real** gate
 * (`resolveAuthGate` / `canEnterRoleArea`) rather than asserting on ports, so
 * what is proved is the property that matters: after a sign-out is initiated,
 * `/athlete` and `/coach` are closed and stay closed, whatever the storage
 * layer or the network does afterwards.
 *
 * The scenario throughout is the one Codex reported: TASK-010's encrypted
 * storage adapter throws when a backend removal fails, Supabase therefore never
 * emits `SIGNED_OUT`, and the old implementation waited for that event before
 * clearing anything.
 *
 * All fixtures are synthetic.
 */

import { describe, expect, it, vi } from "vitest";

import { AuthActionError } from "./auth-repository";
import {
  INITIAL_AUTH_STATE,
  authIdentity,
  authReducer,
  isAuthSettled,
  type AuthEvent,
  type AuthState,
} from "./auth-state";
import { canEnterRoleArea, resolveAuthGate } from "./gate";
import type { MembershipRecord } from "./roles";
import { INITIAL_SEQUENCE_TOKEN, nextSequenceToken } from "./sequence";
import type { AuthenticatedIdentity } from "./session";
import { performSignOut } from "./sign-out";

const USER_A: AuthenticatedIdentity = {
  userId: "00000000-0000-4000-8000-00000000000a",
};
const USER_B: AuthenticatedIdentity = {
  userId: "00000000-0000-4000-8000-00000000000b",
};

/** Dual-role, so both protected areas are open before the sign-out. */
const DUAL_ROLE_MEMBERSHIPS: readonly MembershipRecord[] = [
  { team_id: "team-1", role: "athlete", status: "active" },
  { team_id: "team-2", role: "coach", status: "active" },
];

/**
 * A synthetic failure carrying markers that must never reach the user.
 *
 * Shaped like something the storage layer could realistically surface, so the
 * sanitization assertion is meaningful.
 */
const SENSITIVE_MARKERS = [
  "SYNTHETIC-ACCESS-TOKEN-MARKER",
  "SYNTHETIC-KEY-MATERIAL-MARKER",
  "athlete-a@example.test",
  "00000000-0000-4000-8000-00000000000a",
] as const;

function sensitiveFailure(): Error {
  const error = new Error(
    `native keychain failure: token=${SENSITIVE_MARKERS[0]} key=${SENSITIVE_MARKERS[1]} user=${SENSITIVE_MARKERS[3]} email=${SENSITIVE_MARKERS[2]}`,
  );
  error.name = "SessionStorageError";

  return error;
}

type Harness = {
  readonly ports: Parameters<typeof performSignOut>[0];
  state: () => AuthState;
  cacheClears: () => number;
  /** Dispatches an event exactly as the provider's listener would. */
  observe: (event: AuthEvent) => void;
  claimToken: () => number;
};

function createHarness(
  options: { signOutGlobally?: () => Promise<void> } = {},
): Harness {
  let state = INITIAL_AUTH_STATE;
  let issued = INITIAL_SEQUENCE_TOKEN;
  let cacheClears = 0;

  const claimToken = () => {
    issued = nextSequenceToken(issued);

    return issued;
  };

  const dispatch = (event: AuthEvent) => {
    state = authReducer(state, event);
  };

  return {
    ports: {
      claimToken,
      dispatch,
      clearAuthScopedCache: () => {
        cacheClears += 1;
      },
      signOutGlobally: options.signOutGlobally ?? (() => Promise.resolve()),
    },
    state: () => state,
    cacheClears: () => cacheClears,
    observe: dispatch,
    claimToken,
  };
}

/** Drives the harness into a fully signed-in, dual-role state. */
function signIn(harness: Harness, identity: AuthenticatedIdentity): void {
  const token = harness.claimToken();

  harness.observe({
    type: "signal-observed",
    token,
    candidate: { unverifiedUserId: identity.userId },
  });
  harness.observe({ type: "validation-settled", token, identity });
}

function gateFor(state: AuthState) {
  return resolveAuthGate({
    sessionRestored: isAuthSettled(state),
    identity: authIdentity(state),
    awaitingEmailConfirmation: false,
    account: {
      kind: "loaded",
      displayName: "Athlete A",
      memberships: DUAL_ROLE_MEMBERSHIPS,
    },
  });
}

function bothAreasOpen(state: AuthState): boolean {
  const gate = gateFor(state);

  return canEnterRoleArea(gate, "athlete") && canEnterRoleArea(gate, "coach");
}

function bothAreasClosed(state: AuthState): boolean {
  const gate = gateFor(state);

  return !canEnterRoleArea(gate, "athlete") && !canEnterRoleArea(gate, "coach");
}

describe("sign-out closes local access", () => {
  it("opens both areas first, so the closures below mean something", () => {
    const harness = createHarness();
    signIn(harness, USER_A);

    expect(bothAreasOpen(harness.state())).toBe(true);
    expect(gateFor(harness.state()).status).toBe("ready");
  });

  it("closes the identity and clears the cache on a successful sign-out", async () => {
    const harness = createHarness();
    signIn(harness, USER_A);

    await performSignOut(harness.ports);

    expect(authIdentity(harness.state())).toBeNull();
    expect(harness.cacheClears()).toBe(1);
    expect(bothAreasClosed(harness.state())).toBe(true);
    // Settled, not stuck restoring, so the user lands on sign-in.
    expect(gateFor(harness.state()).status).toBe("signed-out");
  });

  it("closes athlete and coach routing when sign-out throws and no SIGNED_OUT arrives", async () => {
    const harness = createHarness({
      signOutGlobally: () => Promise.reject(sensitiveFailure()),
    });
    signIn(harness, USER_A);

    await expect(performSignOut(harness.ports)).rejects.toBeInstanceOf(
      AuthActionError,
    );

    // The whole point of the finding: no SIGNED_OUT was ever observed.
    expect(authIdentity(harness.state())).toBeNull();
    expect(bothAreasClosed(harness.state())).toBe(true);
    expect(gateFor(harness.state()).status).toBe("signed-out");
  });

  it("does not reuse the old identity after a partial storage removal", async () => {
    // One backend removed, the other threw: exactly what the adapter reports.
    const harness = createHarness({
      signOutGlobally: () =>
        Promise.reject(
          Object.assign(new Error("one side removed, one side failed"), {
            name: "SessionStorageError",
          }),
        ),
    });
    signIn(harness, USER_A);

    await expect(performSignOut(harness.ports)).rejects.toBeInstanceOf(
      AuthActionError,
    );

    expect(authIdentity(harness.state())).toBeNull();
    expect(bothAreasClosed(harness.state())).toBe(true);
    // The cache was dropped before the failure, not after it.
    expect(harness.cacheClears()).toBe(1);
  });

  it("clears the cache before awaiting the remote call, not after", async () => {
    const order: string[] = [];
    let resolveRemote = () => undefined as void;
    const remote = new Promise<void>((resolve) => {
      resolveRemote = () => {
        resolve();
      };
    });

    const harness = createHarness({
      signOutGlobally: () => {
        order.push("remote-started");

        return remote;
      },
    });
    signIn(harness, USER_A);

    const clearCache = harness.ports.clearAuthScopedCache;
    const pending = performSignOut({
      ...harness.ports,
      clearAuthScopedCache: () => {
        order.push("cache-cleared");
        clearCache();
      },
    });

    // Before the remote call has even settled, access is already closed.
    expect(bothAreasClosed(harness.state())).toBe(true);
    expect(order).toEqual(["cache-cleared", "remote-started"]);

    resolveRemote();
    await pending;
  });
});

describe("nothing can reopen access after sign-out", () => {
  it("ignores a delayed stale validation for the previous user", async () => {
    const harness = createHarness();
    signIn(harness, USER_A);

    // A validation for user A is in flight, holding the token issued at
    // sign-in, when the user signs out.
    const staleToken = harness.state().appliedToken;

    await performSignOut(harness.ports);
    expect(bothAreasClosed(harness.state())).toBe(true);

    // It resolves afterwards and tries to reapply user A.
    harness.observe({
      type: "validation-settled",
      token: staleToken,
      identity: USER_A,
    });

    expect(authIdentity(harness.state())).toBeNull();
    expect(bothAreasClosed(harness.state())).toBe(true);
  });

  it("ignores a delayed stale auth event observed before the sign-out", async () => {
    const harness = createHarness();
    signIn(harness, USER_A);

    // An event claimed a token, then the sign-out claimed a newer one before
    // the event was dispatched — the reordering the sequence exists to catch.
    const staleToken = harness.claimToken();

    await performSignOut(harness.ports);

    harness.observe({
      type: "signal-observed",
      token: staleToken,
      candidate: { unverifiedUserId: USER_A.userId },
    });

    expect(authIdentity(harness.state())).toBeNull();
    expect(bothAreasClosed(harness.state())).toBe(true);
  });

  it("never exposes user A again once a sign-out has been initiated", async () => {
    const harness = createHarness({
      signOutGlobally: () => Promise.reject(sensitiveFailure()),
    });
    signIn(harness, USER_A);

    const staleToken = harness.state().appliedToken;
    const exposure: (string | null)[] = [];
    const record = () => {
      exposure.push(authIdentity(harness.state())?.userId ?? null);
    };

    record();
    await performSignOut(harness.ports).catch(() => undefined);
    record();

    harness.observe({
      type: "validation-settled",
      token: staleToken,
      identity: USER_A,
    });
    record();

    harness.observe({
      type: "signal-observed",
      token: staleToken,
      candidate: { unverifiedUserId: USER_A.userId },
    });
    record();

    expect(exposure).toEqual([USER_A.userId, null, null, null]);
  });

  it("still allows a genuine later sign-in", async () => {
    const harness = createHarness();
    signIn(harness, USER_A);

    await performSignOut(harness.ports);
    expect(bothAreasClosed(harness.state())).toBe(true);

    // Sign-out must fail closed, not latch closed forever.
    signIn(harness, USER_B);

    expect(authIdentity(harness.state())).toEqual(USER_B);
    expect(bothAreasOpen(harness.state())).toBe(true);
  });

  it("is idempotent across repeated sign-outs", async () => {
    const harness = createHarness();
    signIn(harness, USER_A);

    await performSignOut(harness.ports);
    await performSignOut(harness.ports);

    expect(authIdentity(harness.state())).toBeNull();
    expect(bothAreasClosed(harness.state())).toBe(true);
    expect(harness.cacheClears()).toBe(2);
  });
});

describe("the reported error is sanitized", () => {
  it("carries no token, key, email, user id, or native error text", async () => {
    const harness = createHarness({
      signOutGlobally: () => Promise.reject(sensitiveFailure()),
    });
    signIn(harness, USER_A);

    let thrown: unknown;

    try {
      await performSignOut(harness.ports);
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(AuthActionError);

    const error = thrown as AuthActionError;
    const serialized = `${error.name}|${error.message}|${error.failure}|${error.stack ?? ""}`;

    // No raw error is carried along for a caller to render or log.
    expect(error.cause).toBeUndefined();
    expect(serialized).not.toContain("native keychain failure");

    for (const marker of SENSITIVE_MARKERS) {
      expect(serialized).not.toContain(marker);
    }

    // A fixed message from the closed set, not a passthrough.
    expect(error.message.length).toBeGreaterThan(0);
  });

  it("logs nothing on either the success or the failure path", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map(
      (level) => vi.spyOn(console, level).mockImplementation(() => undefined),
    );

    const ok = createHarness();
    signIn(ok, USER_A);
    await performSignOut(ok.ports);

    const failing = createHarness({
      signOutGlobally: () => Promise.reject(sensitiveFailure()),
    });
    signIn(failing, USER_A);
    await performSignOut(failing.ports).catch(() => undefined);

    for (const spy of spies) {
      expect(spy).not.toHaveBeenCalled();
    }

    vi.restoreAllMocks();
  });
});
