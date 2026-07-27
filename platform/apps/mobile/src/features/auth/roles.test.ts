import { describe, expect, it } from "vitest";

import {
  hasAnyRole,
  isAuthorizedForRole,
  resolveAuthorizedRoles,
  type MembershipRecord,
} from "./roles";

function membership(
  role: string,
  status: string,
  teamId = "team-1",
): MembershipRecord {
  return { team_id: teamId, role, status };
}

describe("resolveAuthorizedRoles", () => {
  it("returns nothing for a user with no membership rows", () => {
    expect(resolveAuthorizedRoles([])).toEqual([]);
  });

  it("returns nothing for null or undefined", () => {
    expect(resolveAuthorizedRoles(null)).toEqual([]);
    expect(resolveAuthorizedRoles(undefined)).toEqual([]);
  });

  it("grants the athlete role for an active athlete membership", () => {
    expect(resolveAuthorizedRoles([membership("athlete", "active")])).toEqual([
      "athlete",
    ]);
  });

  it("grants the coach role for an active coach membership", () => {
    expect(resolveAuthorizedRoles([membership("coach", "active")])).toEqual([
      "coach",
    ]);
  });

  it("grants both roles to a genuinely dual-role user", () => {
    expect(
      resolveAuthorizedRoles([
        membership("coach", "active", "team-a"),
        membership("athlete", "active", "team-b"),
      ]),
    ).toEqual(["athlete", "coach"]);
  });

  it("ignores a revoked membership", () => {
    expect(resolveAuthorizedRoles([membership("coach", "revoked")])).toEqual(
      [],
    );
  });

  it("drops a revoked role while keeping the remaining active one", () => {
    expect(
      resolveAuthorizedRoles([
        membership("coach", "revoked", "team-a"),
        membership("athlete", "active", "team-b"),
      ]),
    ).toEqual(["athlete"]);
  });

  it("returns nothing once every membership is revoked", () => {
    expect(
      resolveAuthorizedRoles([
        membership("coach", "revoked", "team-a"),
        membership("athlete", "revoked", "team-b"),
      ]),
    ).toEqual([]);
  });

  it("ignores an unrecognised role value rather than trusting it", () => {
    expect(
      resolveAuthorizedRoles([
        membership("admin", "active"),
        membership("superuser", "active"),
      ]),
    ).toEqual([]);
  });

  it("ignores an unrecognised status value", () => {
    expect(resolveAuthorizedRoles([membership("coach", "pending")])).toEqual(
      [],
    );
  });

  it("treats status as case sensitive, matching the database constraint", () => {
    expect(resolveAuthorizedRoles([membership("coach", "ACTIVE")])).toEqual([]);
  });

  it("deduplicates the same role held in several teams", () => {
    expect(
      resolveAuthorizedRoles([
        membership("athlete", "active", "team-a"),
        membership("athlete", "active", "team-b"),
        membership("athlete", "active", "team-c"),
      ]),
    ).toEqual(["athlete"]);
  });

  it("returns a stable order regardless of row order", () => {
    const coachFirst = resolveAuthorizedRoles([
      membership("coach", "active", "team-a"),
      membership("athlete", "active", "team-b"),
    ]);
    const athleteFirst = resolveAuthorizedRoles([
      membership("athlete", "active", "team-b"),
      membership("coach", "active", "team-a"),
    ]);

    expect(coachFirst).toEqual(athleteFirst);
  });
});

describe("isAuthorizedForRole", () => {
  it("denies a role the user does not hold", () => {
    const roles = resolveAuthorizedRoles([membership("athlete", "active")]);

    expect(isAuthorizedForRole(roles, "athlete")).toBe(true);
    expect(isAuthorizedForRole(roles, "coach")).toBe(false);
  });

  it("denies every role when nothing is authorized", () => {
    expect(isAuthorizedForRole([], "athlete")).toBe(false);
    expect(isAuthorizedForRole([], "coach")).toBe(false);
  });
});

describe("hasAnyRole", () => {
  it("distinguishes a pending user from an authorized one", () => {
    expect(hasAnyRole([])).toBe(false);
    expect(hasAnyRole(["athlete"])).toBe(true);
  });
});
