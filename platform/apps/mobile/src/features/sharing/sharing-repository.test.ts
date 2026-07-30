import { describe, expect, it } from "vitest";

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

import {
  resolveSharingTarget,
  type SharingTarget,
  type TeamSharingState,
} from "./domain";
import { probeFailure } from "./failure-probe";
import {
  grantCheckInSharing,
  loadCheckInSharing,
  revokeCheckInSharing,
} from "./sharing-repository";

/**
 * Repository behaviour against a hand-written client double. No network, no local
 * database, no new dependency.
 *
 * **Failure-output safety.** Sharing metadata is not a health measurement, but it
 * is sensitive authorization data and a failing assertion must not print a team id,
 * a user id, an RPC argument, a whole row, or a raw server error.
 *
 * - The double records **names only**. A filter is recorded as `profile_id`, never
 *   `profile_id=<value>`; an RPC is recorded as its function name and its argument
 *   *keys*. Expected values are compared privately inside `filtersMatch` and
 *   `rpcArgsMatch`, which return booleans.
 * - Team ids are reduced to the fixed case labels `A`, `B`, or `unknown` before any
 *   assertion.
 * - Rejections go through `probeFailure`, which never rethrows and never passes a
 *   captured value to `expect`. `.rejects.toThrow` is deliberately not used
 *   anywhere in this file: it prints the received error on a mismatch.
 * - Sets of cases are asserted as lists of **case names**.
 *
 * All identifiers and names are synthetic.
 */

const USER_ID = "00000000-0000-4000-9000-000000000014";
const OTHER_USER_ID = "00000000-0000-4000-9000-0000000000ff";
const TEAM_A = "00000000-0000-4000-8000-00000000000a";
const TEAM_B = "00000000-0000-4000-8000-00000000000b";
const TEAM_C = "00000000-0000-4000-8000-00000000000c";
const GRANT_ID = "11111111-1111-4111-9111-111111111111";
const OTHER_GRANT_ID = "22222222-2222-4222-9222-222222222222";

const NAME_A = "Alpha Runners";
const NAME_B = "Beta Runners";

const LABELS = new Map<string, string>([
  [TEAM_A, "A"],
  [TEAM_B, "B"],
  [TEAM_C, "C"],
]);

function label(teamId: unknown): string {
  return typeof teamId === "string"
    ? (LABELS.get(teamId) ?? "unknown")
    : "unknown";
}

/** The exact column lists the two reads are allowed to name. */
const MEMBERSHIP_COLUMNS = "team_id, role, status, teams(name)";
const GRANT_COLUMNS = "team_id, data_category";

/** The only filters either read is allowed to use, with their expected values. */
const MEMBERSHIP_FILTERS: readonly (readonly [string, unknown])[] = [
  ["profile_id", USER_ID],
  ["role", "athlete"],
  ["status", "active"],
];

const GRANT_FILTERS: readonly (readonly [string, unknown])[] = [
  ["athlete_profile_id", USER_ID],
  ["data_category", "check_in"],
  ["revoked_at", null],
];

const ALLOWED_FILTER_COLUMNS: readonly string[] = [
  ...MEMBERSHIP_FILTERS.map(([column]) => column),
  ...GRANT_FILTERS.map(([column]) => column),
];

type QueryResult = { data: unknown; error: unknown };

type Step =
  | { readonly kind: "result"; readonly result: QueryResult }
  | { readonly kind: "reject" }
  | { readonly kind: "throw" };

function rows(data: unknown): Step {
  return { kind: "result", result: { data, error: null } };
}

function failed(code: string): Step {
  return { kind: "result", result: { data: null, error: { code } } };
}

function returns(data: unknown): Step {
  return { kind: "result", result: { data, error: null } };
}

const NO_ROWS: Step = rows([]);

function membershipRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    team_id: TEAM_A,
    role: "athlete",
    status: "active",
    teams: { name: NAME_A },
    ...overrides,
  };
}

function grantRow(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return { team_id: TEAM_A, data_category: "check_in", ...overrides };
}

/**
 * A raw server error of the kind that must never reach the athlete or a log.
 *
 * Used only as an input to the code under test. It is never asserted on and never
 * returned by the probe.
 */
function rawServerError(): Error {
  const error = new Error(
    "permission denied for function grant_team_data_sharing: p_team_id=00000000-0000-4000-8000-00000000000a",
  );

  return Object.assign(error, {
    code: "42501",
    details: "active athlete membership required",
    hint: "sharing_grants_select_own_history",
    cause: { p_team_id: TEAM_A, p_data_category: "check_in" },
  });
}

/**
 * A minimal stand-in for the PostgREST builder.
 *
 * Every method returns `this` and the object is thenable, so an awaited chain
 * resolves to the queued step. There is deliberately **no `insert`, `update`,
 * `upsert`, or `delete` method**: `authenticated` holds no write privilege on
 * `sharing_grants`, and if this repository ever reached for a direct write these
 * tests would fail rather than quietly exercise a prohibited path.
 */
class FakeQuery implements PromiseLike<QueryResult> {
  constructor(
    private readonly step: Step,
    private readonly record: (
      op: string,
      detail: string,
      filter?: { column: string; value: unknown },
    ) => void,
  ) {}

  select(columns: string): this {
    this.record("select", columns);
    return this;
  }

  /** Records the column name only. The value is kept privately. */
  eq(column: string, value: unknown): this {
    this.record("filter", column, { column, value });
    return this;
  }

  is(column: string, value: unknown): this {
    this.record("filter", column, { column, value });
    return this;
  }

  then<TResult1 = QueryResult, TResult2 = never>(
    onfulfilled?:
      ((value: QueryResult) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): PromiseLike<TResult1 | TResult2> {
    return this.settle().then(onfulfilled, onrejected);
  }

  private settle(): Promise<QueryResult> {
    if (this.step.kind === "throw") {
      // A synchronous throw from inside the builder chain.
      throw rawServerError();
    }

    if (this.step.kind === "reject") {
      return Promise.reject(rawServerError());
    }

    return Promise.resolve(this.step.result);
  }
}

type DoubleOptions = {
  readonly throwFromFrom?: boolean;
  readonly throwFromRpc?: boolean;
};

/** Read steps are consumed in `from()` order; RPC steps in `rpc()` order. */
function createClientDouble(
  steps: readonly Step[],
  rpcSteps: readonly Step[] = [],
  options: DoubleOptions = {},
) {
  const calls: { op: string; detail: string }[] = [];
  const tables: string[] = [];
  const rpcNames: string[] = [];
  // Value-bearing. Never returned, never asserted directly.
  const filters: { column: string; value: unknown }[] = [];
  const rpcArgs: Record<string, unknown>[] = [];
  let readIndex = 0;
  let rpcIndex = 0;

  const client = {
    from(table: string) {
      if (options.throwFromFrom === true) {
        throw rawServerError();
      }

      const step = steps[readIndex] ?? NO_ROWS;
      readIndex += 1;
      tables.push(table);

      return new FakeQuery(step, (op, detail, filter) => {
        if (filter !== undefined) {
          filters.push(filter);
          return;
        }

        calls.push({ op, detail });
      });
    },

    rpc(name: string, args: Record<string, unknown>) {
      if (options.throwFromRpc === true) {
        throw rawServerError();
      }

      const step = rpcSteps[rpcIndex] ?? returns(null);
      rpcIndex += 1;
      rpcNames.push(name);
      rpcArgs.push(args);
      // Argument *keys* only. The values stay in `rpcArgs`.
      calls.push({
        op: "rpc-args",
        detail: Object.keys(args).sort().join(","),
      });

      return new FakeQuery(step, () => undefined);
    },
  } as unknown as AppSupabaseClient;

  return {
    client,

    /** Safe: table names, in order. */
    tables: () => [...tables],

    /** Safe: RPC function names, in order. */
    rpcNames: () => [...rpcNames],

    /** Safe: how many RPCs were attempted. */
    rpcCount: () => rpcNames.length,

    /** Safe: the non-value detail of each call of one kind, in order. */
    details: (op: string) =>
      calls.filter((call) => call.op === op).map((call) => call.detail),

    /** Safe: the column names filtered on, in order. */
    filterColumns: () => filters.map((entry) => entry.column),

    /** Safe: filter columns outside the allowed set, by name only. */
    unexpectedFilterColumns: () =>
      filters
        .map((entry) => entry.column)
        .filter((column) => !ALLOWED_FILTER_COLUMNS.includes(column)),

    /**
     * Whether the filters from `offset` are exactly the expected pairs.
     *
     * Compared here so only a boolean escapes: a mismatch cannot print either
     * side's values.
     */
    filtersMatch: (
      offset: number,
      expected: readonly (readonly [string, unknown])[],
    ): boolean => {
      const slice = filters.slice(offset, offset + expected.length);

      return (
        slice.length === expected.length &&
        expected.every(([column, value], position) => {
          const found = slice[position];

          return (
            found !== undefined &&
            found.column === column &&
            found.value === value
          );
        })
      );
    },

    filterCount: () => filters.length,

    /** Whether the nth RPC's arguments are exactly the expected object. */
    rpcArgsMatch: (occurrence: number, expected: Record<string, unknown>) => {
      const found = rpcArgs[occurrence];

      if (found === undefined) {
        return false;
      }

      const expectedKeys = Object.keys(expected).sort();
      const foundKeys = Object.keys(found).sort();

      return (
        expectedKeys.join(",") === foundKeys.join(",") &&
        expectedKeys.every((key) => found[key] === expected[key])
      );
    },

    /** Safe: the case label of each RPC's team argument, in order. */
    rpcTeamLabels: () => rpcArgs.map((args) => label(args.p_team_id)),

    /** Safe: the category each RPC was called with. A fixed vocabulary. */
    rpcCategories: () =>
      rpcArgs.map((args) =>
        args.p_data_category === "check_in"
          ? "check_in"
          : "unexpected-category",
      ),

    /** Safe: every argument key any RPC received, deduplicated and sorted. */
    rpcArgKeys: () =>
      [...new Set(rpcArgs.flatMap((args) => Object.keys(args)))].sort(),
  };
}

const LOADED_TEAMS: readonly TeamSharingState[] = [
  { teamId: TEAM_A, teamName: NAME_A, sharing: false },
  { teamId: TEAM_B, teamName: NAME_B, sharing: true },
];

/** Non-null by construction: both ids are in `LOADED_TEAMS`. */
function target(teamId: string): SharingTarget {
  const resolved = resolveSharingTarget(teamId, LOADED_TEAMS);

  if (resolved === null) {
    throw new Error("test fixture: team is not in the loaded list");
  }

  return resolved;
}

/** Safe: case labels and on/off only. */
function summarize(teams: readonly TeamSharingState[]): readonly string[] {
  return teams.map(
    (team) => `${label(team.teamId)}:${team.sharing ? "on" : "off"}`,
  );
}

describe("loadCheckInSharing, the happy path", () => {
  it("reads memberships first, then grants, and nothing else", () => {
    const double = createClientDouble([rows([membershipRow()]), rows([])]);

    return loadCheckInSharing(double.client, USER_ID).then(() => {
      expect(double.tables()).toEqual(["team_memberships", "sharing_grants"]);
      expect(double.rpcCount()).toBe(0);
    });
  });

  it("selects only the fields needed to decide a control", () => {
    const double = createClientDouble([rows([membershipRow()]), rows([])]);

    return loadCheckInSharing(double.client, USER_ID).then(() => {
      // Column names only. The team label comes from an embedded teams(name),
      // never from the id, and revoked_at is filtered but not selected.
      expect(double.details("select")).toEqual([
        MEMBERSHIP_COLUMNS,
        GRANT_COLUMNS,
      ]);
    });
  });

  it("scopes both reads to the verified caller, the athlete role, and check_in", () => {
    const double = createClientDouble([rows([membershipRow()]), rows([])]);

    return loadCheckInSharing(double.client, USER_ID).then(() => {
      expect(double.filterColumns()).toEqual([
        "profile_id",
        "role",
        "status",
        "athlete_profile_id",
        "data_category",
        "revoked_at",
      ]);
      // Values compared privately.
      expect(double.filtersMatch(0, MEMBERSHIP_FILTERS)).toBe(true);
      expect(double.filtersMatch(3, GRANT_FILTERS)).toBe(true);
      expect(double.unexpectedFilterColumns()).toEqual([]);
      expect(double.filterCount()).toBe(6);
    });
  });

  it("reports a team with no grant as not sharing", async () => {
    const double = createClientDouble([rows([membershipRow()]), rows([])]);

    expect(summarize(await loadCheckInSharing(double.client, USER_ID))).toEqual(
      ["A:off"],
    );
  });

  it("reports a team with an active grant as sharing", async () => {
    const double = createClientDouble([
      rows([membershipRow()]),
      rows([grantRow()]),
    ]);

    expect(summarize(await loadCheckInSharing(double.client, USER_ID))).toEqual(
      ["A:on"],
    );
  });

  it("keeps two teams independent", async () => {
    const double = createClientDouble([
      rows([
        membershipRow(),
        membershipRow({ team_id: TEAM_B, teams: { name: NAME_B } }),
      ]),
      rows([grantRow({ team_id: TEAM_B })]),
    ]);

    expect(summarize(await loadCheckInSharing(double.client, USER_ID))).toEqual(
      ["A:off", "B:on"],
    );
  });

  it("returns a real empty list for a caller with no active athlete membership", async () => {
    // The coach-only, pending, and revoked-membership case. An empty list is the
    // honest answer and must not be confused with a failure.
    const double = createClientDouble([rows([]), rows([])]);

    expect(await loadCheckInSharing(double.client, USER_ID)).toEqual([]);
  });

  it("drops a membership that stopped being returned", async () => {
    // Team B's membership was revoked, so the next successful load has no control
    // for it and its grant is already revoked by the TASK-011 trigger.
    const double = createClientDouble([rows([membershipRow()]), rows([])]);

    expect(summarize(await loadCheckInSharing(double.client, USER_ID))).toEqual(
      ["A:off"],
    );
  });
});

describe("loadCheckInSharing, failures are never an empty list", () => {
  const CASES: readonly (readonly [
    name: string,
    steps: readonly Step[],
    options: DoubleOptions,
  ])[] = [
    ["membership-denied", [failed("42501")], {}],
    ["membership-rejected", [{ kind: "reject" }], {}],
    ["membership-throws", [{ kind: "throw" }], {}],
    ["grant-denied", [rows([membershipRow()]), failed("42501")], {}],
    ["grant-jwt-rejected", [rows([membershipRow()]), failed("PGRST301")], {}],
    ["grant-rejected", [rows([membershipRow()]), { kind: "reject" }], {}],
    ["grant-throws", [rows([membershipRow()]), { kind: "throw" }], {}],
    ["client-throws", [], { throwFromFrom: true }],
    ["membership-data-null", [rows(null), rows([])], {}],
    ["grant-data-null", [rows([membershipRow()]), rows(null)], {}],
    [
      "malformed-membership",
      [rows([membershipRow({ teams: null })]), rows([])],
      {},
    ],
    [
      "malformed-grant",
      [
        rows([membershipRow()]),
        rows([grantRow({ data_category: "sleep_summary" })]),
      ],
      {},
    ],
    [
      "grant-for-unowned-team",
      [rows([membershipRow()]), rows([grantRow({ team_id: TEAM_C })])],
      {},
    ],
    [
      "duplicate-membership",
      [rows([membershipRow(), membershipRow()]), rows([])],
      {},
    ],
    [
      "duplicate-grant",
      [rows([membershipRow()]), rows([grantRow(), grantRow()])],
      {},
    ],
    [
      "coach-row-returned",
      [rows([membershipRow({ role: "coach" })]), rows([])],
      {},
    ],
    [
      "revoked-row-returned",
      [rows([membershipRow({ status: "revoked" })]), rows([])],
      {},
    ],
  ];

  it("raises a sanitized load error for every failure", async () => {
    const wrong: string[] = [];

    for (const [name, steps, options] of CASES) {
      const double = createClientDouble(steps, [], options);
      const probe = await probeFailure(
        loadCheckInSharing(double.client, USER_ID),
      );

      if (
        probe.outcome !== "sanitized-error" ||
        probe.intent !== "load" ||
        !probe.messageIsFixed ||
        !probe.withoutCause
      ) {
        wrong.push(name);
      }
    }

    // Case names only.
    expect(wrong).toEqual([]);
  });

  it("attempts no write on any failure path", async () => {
    const wrote: string[] = [];

    for (const [name, steps, options] of CASES) {
      const double = createClientDouble(steps, [], options);

      await probeFailure(loadCheckInSharing(double.client, USER_ID));

      if (double.rpcCount() !== 0) {
        wrote.push(name);
      }
    }

    expect(wrote).toEqual([]);
  });

  it("covers the whole failure surface", () => {
    expect(CASES.length).toBeGreaterThan(15);
  });

  it("keeps nothing from a raw Supabase error", async () => {
    const double = createClientDouble([{ kind: "reject" }]);

    const probe = await probeFailure(
      loadCheckInSharing(double.client, USER_ID),
    );

    // The rejected value carries a message naming the RPC and a team id, plus
    // details, hint, and cause. None of it may survive.
    expect(probe.outcome).toBe("sanitized-error");
    expect(probe.messageIsFixed).toBe(true);
    expect(probe.withoutCause).toBe(true);
    // Safe field names only.
    expect(probe.fields).toEqual(["failure", "intent", "name"]);
  });

  it("classifies a refusal as denied and a transport failure as offline", async () => {
    const denied = await probeFailure(
      loadCheckInSharing(createClientDouble([failed("42501")]).client, USER_ID),
    );

    expect(denied.failure).toBe("denied");

    const offlineDouble = createClientDouble([
      {
        kind: "result",
        result: {
          data: null,
          error: Object.assign(new Error("x"), { name: "TypeError" }),
        },
      },
    ]);
    const offline = await probeFailure(
      loadCheckInSharing(offlineDouble.client, USER_ID),
    );

    expect(offline.failure).toBe("offline");
  });
});

describe("loadCheckInSharing, identity", () => {
  it("refuses to query without a verified identity", async () => {
    const REFUSED: readonly (readonly [string, unknown])[] = [
      ["empty", ""],
      ["undefined", undefined],
      ["null", null],
      ["number", 7],
      ["object", { id: USER_ID }],
    ];

    const queried: string[] = [];

    for (const [name, candidate] of REFUSED) {
      const double = createClientDouble([rows([membershipRow()]), rows([])]);
      const probe = await probeFailure(
        loadCheckInSharing(double.client, candidate as string),
      );

      if (
        probe.outcome !== "sanitized-error" ||
        probe.intent !== "load" ||
        double.tables().length !== 0
      ) {
        queried.push(name);
      }
    }

    // Case names only. No query was issued for a placeholder owner.
    expect(queried).toEqual([]);
  });

  it("filters the grant read to the caller, so another athlete's grants cannot enter", async () => {
    const double = createClientDouble([rows([membershipRow()]), rows([])]);

    await loadCheckInSharing(double.client, USER_ID);

    // The value comparison is private; only the boolean escapes.
    expect(double.filtersMatch(3, [["athlete_profile_id", USER_ID]])).toBe(
      true,
    );
    expect(
      double.filtersMatch(3, [["athlete_profile_id", OTHER_USER_ID]]),
    ).toBe(false);
  });
});

describe("grantCheckInSharing", () => {
  it("calls exactly the approved RPC with the team and the constant category", async () => {
    const double = createClientDouble([], [returns(GRANT_ID)]);

    await grantCheckInSharing(double.client, target(TEAM_A));

    expect(double.rpcNames()).toEqual(["grant_team_data_sharing"]);
    expect(double.rpcTeamLabels()).toEqual(["A"]);
    expect(double.rpcCategories()).toEqual(["check_in"]);
    // Values compared privately.
    expect(
      double.rpcArgsMatch(0, {
        p_team_id: TEAM_A,
        p_data_category: "check_in",
      }),
    ).toBe(true);
  });

  it("passes no athlete identifier and no other argument", async () => {
    const double = createClientDouble([], [returns(GRANT_ID)]);

    await grantCheckInSharing(double.client, target(TEAM_A));

    // Argument key names only. The athlete is auth.uid() inside the function.
    expect(double.rpcArgKeys()).toEqual(["p_data_category", "p_team_id"]);
    expect(double.details("rpc-args")).toEqual(["p_data_category,p_team_id"]);
  });

  it("reads nothing and writes no table directly", async () => {
    const double = createClientDouble([], [returns(GRANT_ID)]);

    await grantCheckInSharing(double.client, target(TEAM_A));

    expect(double.tables()).toEqual([]);
  });

  it("leaves another team untouched", async () => {
    const double = createClientDouble([], [returns(GRANT_ID)]);

    await grantCheckInSharing(double.client, target(TEAM_A));

    // One call, naming Team A only. Nothing referenced Team B.
    expect(double.rpcCount()).toBe(1);
    expect(double.rpcTeamLabels()).toEqual(["A"]);
    expect(double.rpcTeamLabels().includes("B")).toBe(false);
  });

  it("keeps two teams' actions separate", async () => {
    const double = createClientDouble(
      [],
      [returns(GRANT_ID), returns(OTHER_GRANT_ID)],
    );

    await grantCheckInSharing(double.client, target(TEAM_A));
    await grantCheckInSharing(double.client, target(TEAM_B));

    expect(double.rpcTeamLabels()).toEqual(["A", "B"]);
    expect(double.rpcCategories()).toEqual(["check_in", "check_in"]);
  });

  it("is idempotent: a duplicate grant is one call each and the same scope", async () => {
    // TASK-011 makes the RPC return the existing active row's id on a repeat, so
    // two active rows can never exist. The repository must accept that as success.
    const double = createClientDouble(
      [],
      [returns(GRANT_ID), returns(GRANT_ID)],
    );

    await grantCheckInSharing(double.client, target(TEAM_A));
    await grantCheckInSharing(double.client, target(TEAM_A));

    expect(double.rpcCount()).toBe(2);
    expect(double.rpcTeamLabels()).toEqual(["A", "A"]);
    expect(
      double.rpcArgsMatch(1, {
        p_team_id: TEAM_A,
        p_data_category: "check_in",
      }),
    ).toBe(true);
  });

  it("succeeds only when the expected non-health sentinel arrives", async () => {
    const REJECTED: readonly (readonly [string, unknown])[] = [
      ["null", null],
      ["undefined", undefined],
      ["empty-string", ""],
      ["ok-string", "ok"],
      ["true", true],
      ["number", 1],
      ["object", { id: GRANT_ID }],
      ["array", [GRANT_ID]],
      ["short-uuid", "11111111-1111-4111-9111"],
      ["uuid-with-spaces", ` ${GRANT_ID} `],
      ["uuid-with-suffix", `${GRANT_ID}x`],
      ["not-hex", "gggggggg-1111-4111-9111-111111111111"],
    ];

    const accepted: string[] = [];

    for (const [name, data] of REJECTED) {
      const double = createClientDouble([], [returns(data)]);
      const probe = await probeFailure(
        grantCheckInSharing(double.client, target(TEAM_A)),
      );

      if (probe.outcome !== "sanitized-error" || probe.intent !== "grant") {
        accepted.push(name);
      }
    }

    // Case names only.
    expect(accepted).toEqual([]);
  });

  it("sanitizes every failure shape", async () => {
    const CASES: readonly (readonly [
      string,
      readonly Step[],
      DoubleOptions,
    ])[] = [
      ["denied", [failed("42501")], {}],
      ["invalid-category", [failed("22023")], {}],
      ["jwt-rejected", [failed("PGRST301")], {}],
      ["rejected", [{ kind: "reject" }], {}],
      ["throws-in-builder", [{ kind: "throw" }], {}],
      ["client-throws", [], { throwFromRpc: true }],
    ];

    const wrong: string[] = [];

    for (const [name, rpcSteps, options] of CASES) {
      const double = createClientDouble([], rpcSteps, options);
      const probe = await probeFailure(
        grantCheckInSharing(double.client, target(TEAM_A)),
      );

      if (
        probe.outcome !== "sanitized-error" ||
        probe.intent !== "grant" ||
        !probe.messageIsFixed ||
        !probe.withoutCause ||
        probe.fields.join(",") !== "failure,intent,name"
      ) {
        wrong.push(name);
      }
    }

    expect(wrong).toEqual([]);
  });
});

describe("revokeCheckInSharing", () => {
  it("calls exactly the approved RPC with the same restricted scope", async () => {
    const double = createClientDouble([], [returns(GRANT_ID)]);

    await revokeCheckInSharing(double.client, target(TEAM_B));

    expect(double.rpcNames()).toEqual(["revoke_team_data_sharing"]);
    expect(double.rpcTeamLabels()).toEqual(["B"]);
    expect(double.rpcCategories()).toEqual(["check_in"]);
    expect(double.rpcArgKeys()).toEqual(["p_data_category", "p_team_id"]);
    expect(
      double.rpcArgsMatch(0, {
        p_team_id: TEAM_B,
        p_data_category: "check_in",
      }),
    ).toBe(true);
  });

  it("treats a null return as the confirmed off state", async () => {
    // A repeat revoke, or a revoke that raced the membership trigger. Either way
    // the server-confirmed state afterwards is "not sharing".
    const double = createClientDouble([], [returns(null)]);

    await expect(
      revokeCheckInSharing(double.client, target(TEAM_A)),
    ).resolves.toBeUndefined();
  });

  it("is safe to repeat", async () => {
    const double = createClientDouble([], [returns(GRANT_ID), returns(null)]);

    await revokeCheckInSharing(double.client, target(TEAM_A));
    await revokeCheckInSharing(double.client, target(TEAM_A));

    expect(double.rpcCount()).toBe(2);
    expect(double.rpcNames()).toEqual([
      "revoke_team_data_sharing",
      "revoke_team_data_sharing",
    ]);
  });

  it("leaves another team untouched", async () => {
    const double = createClientDouble([], [returns(GRANT_ID)]);

    await revokeCheckInSharing(double.client, target(TEAM_A));

    expect(double.rpcTeamLabels()).toEqual(["A"]);
    expect(double.rpcTeamLabels().includes("B")).toBe(false);
  });

  it("refuses a response that is neither a row id nor null", async () => {
    const REJECTED: readonly (readonly [string, unknown])[] = [
      ["undefined", undefined],
      ["empty-string", ""],
      ["ok-string", "ok"],
      ["false", false],
      ["number", 0],
      ["object", {}],
    ];

    const accepted: string[] = [];

    for (const [name, data] of REJECTED) {
      const double = createClientDouble([], [returns(data)]);
      const probe = await probeFailure(
        revokeCheckInSharing(double.client, target(TEAM_A)),
      );

      if (probe.outcome !== "sanitized-error" || probe.intent !== "revoke") {
        accepted.push(name);
      }
    }

    expect(accepted).toEqual([]);
  });

  it("sanitizes every failure shape", async () => {
    const CASES: readonly (readonly [
      string,
      readonly Step[],
      DoubleOptions,
    ])[] = [
      ["denied", [failed("42501")], {}],
      ["invalid-category", [failed("22023")], {}],
      ["rejected", [{ kind: "reject" }], {}],
      ["throws-in-builder", [{ kind: "throw" }], {}],
      ["client-throws", [], { throwFromRpc: true }],
    ];

    const wrong: string[] = [];

    for (const [name, rpcSteps, options] of CASES) {
      const double = createClientDouble([], rpcSteps, options);
      const probe = await probeFailure(
        revokeCheckInSharing(double.client, target(TEAM_A)),
      );

      if (
        probe.outcome !== "sanitized-error" ||
        probe.intent !== "revoke" ||
        !probe.messageIsFixed ||
        !probe.withoutCause
      ) {
        wrong.push(name);
      }
    }

    expect(wrong).toEqual([]);
  });
});
