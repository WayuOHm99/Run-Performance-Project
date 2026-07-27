import { describe, expect, it } from "vitest";

import {
  ROUTES,
  canEditProfile,
  canEnterRoleArea,
  needsRoleChoice,
  resolveAuthGate,
  resolveLandingRoute,
  roleRoute,
  type AuthGate,
  type AuthGateInput,
  type MembershipRecord,
} from "./gate";

const IDENTITY = { userId: "00000000-0000-4000-9000-000000000001" };

function membership(role: string, status = "active"): MembershipRecord {
  return { team_id: "team-1", role, status };
}

function input(overrides: Partial<AuthGateInput> = {}): AuthGateInput {
  return {
    sessionRestored: true,
    identity: IDENTITY,
    awaitingEmailConfirmation: false,
    account: {
      kind: "loaded",
      displayName: "athlete-a",
      memberships: [membership("athlete")],
    },
    ...overrides,
  };
}

describe("resolveAuthGate: restoration", () => {
  it("reports restoring before the stored session has been read", () => {
    expect(resolveAuthGate(input({ sessionRestored: false }))).toEqual({
      status: "restoring",
    });
  });

  it("reports restoring even when an identity is already present", () => {
    // Nothing may be trusted before restoration completes, otherwise a
    // protected shell can flash during startup.
    expect(
      resolveAuthGate(input({ sessionRestored: false, identity: IDENTITY })),
    ).toEqual({ status: "restoring" });
  });

  it("reports restoring rather than signed-out for a missing identity", () => {
    expect(
      resolveAuthGate(input({ sessionRestored: false, identity: null })),
    ).toEqual({ status: "restoring" });
  });
});

describe("resolveAuthGate: unauthenticated", () => {
  it("reports signed-out once restoration found no session", () => {
    expect(resolveAuthGate(input({ identity: null }))).toEqual({
      status: "signed-out",
    });
  });

  it("reports check-email after a sign-up that returned no session", () => {
    expect(
      resolveAuthGate(
        input({ identity: null, awaitingEmailConfirmation: true }),
      ),
    ).toEqual({ status: "check-email" });
  });

  it("ignores the confirmation flag once a session exists", () => {
    const gate = resolveAuthGate(input({ awaitingEmailConfirmation: true }));

    expect(gate.status).toBe("ready");
  });
});

describe("resolveAuthGate: account loading", () => {
  it("reports loading while the account query is in flight", () => {
    expect(resolveAuthGate(input({ account: { kind: "loading" } }))).toEqual({
      status: "loading-account",
      userId: IDENTITY.userId,
    });
  });

  it("reports a recoverable error state when the load fails", () => {
    expect(
      resolveAuthGate(
        input({ account: { kind: "error", message: "โหลดไม่สำเร็จ" } }),
      ),
    ).toEqual({
      status: "account-error",
      userId: IDENTITY.userId,
      message: "โหลดไม่สำเร็จ",
    });
  });

  it("never reports no-active-team for a failed load", () => {
    // The regression this guards: an error and "no membership" both produce
    // zero usable rows, and collapsing them would tell a coach they had been
    // removed from their team because the network dropped.
    const gate = resolveAuthGate(
      input({ account: { kind: "error", message: "โหลดไม่สำเร็จ" } }),
    );

    expect(gate.status).not.toBe("no-active-team");
    expect(gate.status).toBe("account-error");
  });

  it("never reports onboarding for a failed load", () => {
    const gate = resolveAuthGate(
      input({ account: { kind: "error", message: "โหลดไม่สำเร็จ" } }),
    );

    expect(gate.status).not.toBe("onboarding");
  });

  it("never reports ready for a failed load", () => {
    const gate = resolveAuthGate(
      input({ account: { kind: "error", message: "โหลดไม่สำเร็จ" } }),
    );

    expect(gate.status).not.toBe("ready");
  });
});

describe("resolveAuthGate: onboarding", () => {
  it("requires onboarding when the profile has no name", () => {
    expect(
      resolveAuthGate(
        input({
          account: { kind: "loaded", displayName: null, memberships: [] },
        }),
      ),
    ).toEqual({ status: "onboarding", userId: IDENTITY.userId });
  });

  it("requires onboarding for a blank name", () => {
    expect(
      resolveAuthGate(
        input({
          account: {
            kind: "loaded",
            displayName: "   ",
            memberships: [membership("athlete")],
          },
        }),
      ).status,
    ).toBe("onboarding");
  });

  it("requires onboarding before role routing, even with an active role", () => {
    // Onboarding is checked ahead of membership on purpose: a nameless user
    // must not land in a role area.
    expect(
      resolveAuthGate(
        input({
          account: {
            kind: "loaded",
            displayName: null,
            memberships: [membership("coach")],
          },
        }),
      ).status,
    ).toBe("onboarding");
  });
});

describe("resolveAuthGate: membership", () => {
  it("reports no-active-team for a successful load with no memberships", () => {
    expect(
      resolveAuthGate(
        input({
          account: {
            kind: "loaded",
            displayName: "athlete-a",
            memberships: [],
          },
        }),
      ),
    ).toEqual({ status: "no-active-team", userId: IDENTITY.userId });
  });

  it("reports no-active-team for a revoked user", () => {
    expect(
      resolveAuthGate(
        input({
          account: {
            kind: "loaded",
            displayName: "athlete-a",
            memberships: [membership("athlete", "revoked")],
          },
        }),
      ).status,
    ).toBe("no-active-team");
  });

  it("reports ready with the athlete role only", () => {
    expect(resolveAuthGate(input())).toEqual({
      status: "ready",
      userId: IDENTITY.userId,
      authorizedRoles: ["athlete"],
    });
  });

  it("reports ready with the coach role only", () => {
    expect(
      resolveAuthGate(
        input({
          account: {
            kind: "loaded",
            displayName: "coach-a",
            memberships: [membership("coach")],
          },
        }),
      ),
    ).toEqual({
      status: "ready",
      userId: IDENTITY.userId,
      authorizedRoles: ["coach"],
    });
  });

  it("reports both roles for a dual-role user", () => {
    const gate = resolveAuthGate(
      input({
        account: {
          kind: "loaded",
          displayName: "coach-dual",
          memberships: [membership("coach"), membership("athlete")],
        },
      }),
    );

    expect(gate.status).toBe("ready");
    expect(gate.status === "ready" ? gate.authorizedRoles : []).toEqual([
      "athlete",
      "coach",
    ]);
  });

  it("drops a role as soon as a refreshed load reports it revoked", () => {
    const before = resolveAuthGate(
      input({
        account: {
          kind: "loaded",
          displayName: "coach-dual",
          memberships: [membership("coach"), membership("athlete")],
        },
      }),
    );
    const after = resolveAuthGate(
      input({
        account: {
          kind: "loaded",
          displayName: "coach-dual",
          memberships: [membership("coach", "revoked"), membership("athlete")],
        },
      }),
    );

    expect(canEnterRoleArea(before, "coach")).toBe(true);
    expect(canEnterRoleArea(after, "coach")).toBe(false);
    expect(canEnterRoleArea(after, "athlete")).toBe(true);
  });
});

describe("canEnterRoleArea", () => {
  const nonReady: AuthGate[] = [
    { status: "restoring" },
    { status: "signed-out" },
    { status: "check-email" },
    { status: "loading-account", userId: IDENTITY.userId },
    { status: "account-error", userId: IDENTITY.userId, message: "x" },
    { status: "onboarding", userId: IDENTITY.userId },
    { status: "no-active-team", userId: IDENTITY.userId },
  ];

  it("denies every role area in every non-ready state", () => {
    // This is the fail-closed guarantee for direct navigation to /athlete and
    // /coach. Every state that is not `ready` denies without its own rule.
    for (const gate of nonReady) {
      expect(canEnterRoleArea(gate, "athlete")).toBe(false);
      expect(canEnterRoleArea(gate, "coach")).toBe(false);
    }
  });

  it("denies the coach area to an athlete-only user", () => {
    const gate = resolveAuthGate(input());

    expect(canEnterRoleArea(gate, "athlete")).toBe(true);
    expect(canEnterRoleArea(gate, "coach")).toBe(false);
  });

  it("denies the athlete area to a coach-only user", () => {
    const gate = resolveAuthGate(
      input({
        account: {
          kind: "loaded",
          displayName: "coach-a",
          memberships: [membership("coach")],
        },
      }),
    );

    expect(canEnterRoleArea(gate, "coach")).toBe(true);
    expect(canEnterRoleArea(gate, "athlete")).toBe(false);
  });

  it("allows both areas to a dual-role user", () => {
    const gate = resolveAuthGate(
      input({
        account: {
          kind: "loaded",
          displayName: "coach-dual",
          memberships: [membership("coach"), membership("athlete")],
        },
      }),
    );

    expect(canEnterRoleArea(gate, "athlete")).toBe(true);
    expect(canEnterRoleArea(gate, "coach")).toBe(true);
  });

  it("denies a ready gate that somehow carries no role", () => {
    expect(
      canEnterRoleArea(
        { status: "ready", userId: IDENTITY.userId, authorizedRoles: [] },
        "athlete",
      ),
    ).toBe(false);
  });
});

describe("canEditProfile", () => {
  it("allows a revoked user to keep editing their own name", () => {
    expect(
      canEditProfile({ status: "no-active-team", userId: IDENTITY.userId }),
    ).toBe(true);
  });

  it("denies an unauthenticated caller", () => {
    expect(canEditProfile({ status: "signed-out" })).toBe(false);
    expect(canEditProfile({ status: "restoring" })).toBe(false);
    expect(canEditProfile({ status: "check-email" })).toBe(false);
  });
});

describe("needsRoleChoice", () => {
  it("is true only for a dual-role ready user", () => {
    expect(
      needsRoleChoice({
        status: "ready",
        userId: IDENTITY.userId,
        authorizedRoles: ["athlete", "coach"],
      }),
    ).toBe(true);
    expect(
      needsRoleChoice({
        status: "ready",
        userId: IDENTITY.userId,
        authorizedRoles: ["athlete"],
      }),
    ).toBe(false);
    expect(
      needsRoleChoice({ status: "no-active-team", userId: IDENTITY.userId }),
    ).toBe(false);
  });
});

describe("resolveLandingRoute", () => {
  it("sends a restoring app to the neutral loading route", () => {
    expect(resolveLandingRoute({ status: "restoring" })).toBe(ROUTES.loading);
  });

  it("sends a loading account to the neutral loading route", () => {
    expect(
      resolveLandingRoute({
        status: "loading-account",
        userId: IDENTITY.userId,
      }),
    ).toBe(ROUTES.loading);
  });

  it("sends a failed load to the loading route, which renders the retry", () => {
    expect(
      resolveLandingRoute({
        status: "account-error",
        userId: IDENTITY.userId,
        message: "x",
      }),
    ).toBe(ROUTES.loading);
  });

  it("sends a signed-out user to sign-in", () => {
    expect(resolveLandingRoute({ status: "signed-out" })).toBe(ROUTES.signIn);
  });

  it("sends an unconfirmed sign-up to check-email", () => {
    expect(resolveLandingRoute({ status: "check-email" })).toBe(
      ROUTES.checkEmail,
    );
  });

  it("sends a nameless user to onboarding", () => {
    expect(
      resolveLandingRoute({ status: "onboarding", userId: IDENTITY.userId }),
    ).toBe(ROUTES.onboarding);
  });

  it("sends a user with no active membership to pending", () => {
    expect(
      resolveLandingRoute({
        status: "no-active-team",
        userId: IDENTITY.userId,
      }),
    ).toBe(ROUTES.pending);
  });

  it("sends a single-role user straight into their shell", () => {
    expect(
      resolveLandingRoute({
        status: "ready",
        userId: IDENTITY.userId,
        authorizedRoles: ["athlete"],
      }),
    ).toBe(ROUTES.athlete);
    expect(
      resolveLandingRoute({
        status: "ready",
        userId: IDENTITY.userId,
        authorizedRoles: ["coach"],
      }),
    ).toBe(ROUTES.coach);
  });

  it("sends a dual-role user to the chooser", () => {
    expect(
      resolveLandingRoute({
        status: "ready",
        userId: IDENTITY.userId,
        authorizedRoles: ["athlete", "coach"],
      }),
    ).toBe(ROUTES.chooseRole);
  });

  it("falls back to pending for an impossible ready state with no role", () => {
    expect(
      resolveLandingRoute({
        status: "ready",
        userId: IDENTITY.userId,
        authorizedRoles: [],
      }),
    ).toBe(ROUTES.pending);
  });
});

describe("roleRoute", () => {
  it("maps each role to its shell", () => {
    expect(roleRoute("athlete")).toBe(ROUTES.athlete);
    expect(roleRoute("coach")).toBe(ROUTES.coach);
  });
});
