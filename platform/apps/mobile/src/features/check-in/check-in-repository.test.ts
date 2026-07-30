import { describe, expect, it } from "vitest";

import type { AppSupabaseClient } from "../../lib/supabase/app-client";

import { loadDailyCheckIn, saveDailyCheckIn } from "./check-in-repository";
import type { DailyCheckIn } from "./domain";
import { probeFailure } from "./failure-probe";

/**
 * Repository behaviour against a hand-written client double. No network, no local
 * database, no new dependency.
 *
 * **Failure-output safety.** Health literals here are synthetic, but a failing
 * assertion must still not print one, and neither must a raw server error.
 *
 * - The double records **column names only**. A filter is recorded as
 *   `athlete_profile_id`, never `athlete_profile_id=<value>`, so a regression that
 *   filtered on a health column could not print that column's value. Expected
 *   filter values are compared privately inside `filtersMatch`, which returns a
 *   boolean.
 * - Health-bearing write payloads are held privately and compared only inside
 *   `payloadMatches`, which returns a boolean.
 * - Rejections go through `probeFailure`, which never rethrows and never passes a
 *   captured value to `expect`. `.rejects.toThrow` is deliberately not used
 *   anywhere in this file: it prints the received error on a mismatch.
 * - Sets of cases are asserted as lists of **case names**.
 */

const USER_ID = "00000000-0000-4000-9000-000000000013";
const OTHER_USER_ID = "00000000-0000-4000-9000-0000000000ff";
const LOCAL_DATE = "2026-07-30";

const VALID_INPUT: DailyCheckIn = {
  rpe: 6,
  overallFeeling: 3,
  painStatus: "none",
};

const UPDATE_COLUMNS = {
  rpe: VALID_INPUT.rpe,
  overall_feeling: VALID_INPUT.overallFeeling,
  pain_status: VALID_INPUT.painStatus,
};

const INSERT_COLUMNS = {
  athlete_profile_id: USER_ID,
  check_in_date: LOCAL_DATE,
  ...UPDATE_COLUMNS,
};

/** The only filters any statement in this feature is allowed to use. */
const SCOPE_FILTERS: readonly [string, unknown][] = [
  ["athlete_profile_id", USER_ID],
  ["check_in_date", LOCAL_DATE],
];

type QueryResult = { data: unknown; error: unknown };

/** A queued outcome: resolve with a PostgREST result, or fail. */
type Step =
  | { readonly kind: "result"; readonly result: QueryResult }
  | { readonly kind: "reject" }
  | { readonly kind: "throw" };

const NO_ROW: Step = { kind: "result", result: { data: null, error: null } };
const MATCHED_ROW: Step = {
  kind: "result",
  result: { data: { id: "11111111-1111-4111-9111-111111111111" }, error: null },
};
const INSERT_OK: Step = { kind: "result", result: { data: null, error: null } };
const UNIQUE_VIOLATION: Step = {
  kind: "result",
  result: { data: null, error: { code: "23505" } },
};

function failed(code: string): Step {
  return { kind: "result", result: { data: null, error: { code } } };
}

function columnNames(values: unknown): string {
  return typeof values === "object" && values !== null
    ? Object.keys(values).sort().join(",")
    : "";
}

/**
 * A raw server error of the kind that must never reach the athlete or a log.
 *
 * Used only as an input to the code under test; it is never asserted on and never
 * returned by the probe.
 */
function rawServerError(): Error {
  const error = new Error(
    'permission denied for table "daily_check_ins": Failing row contains (...)',
  );

  return Object.assign(error, {
    code: "42501",
    details: "Failing row contains (...)",
    hint: "daily_check_ins_update_own",
  });
}

/**
 * A minimal stand-in for the PostgREST builder.
 *
 * Every method returns `this` and the object is thenable, so an awaited chain and
 * a `.maybeSingle()` chain both resolve to the queued step. There is deliberately
 * **no `upsert` method**: if the repository ever reached for one, these tests
 * would fail rather than quietly exercise a prohibited write.
 */
class FakeQuery implements PromiseLike<QueryResult> {
  constructor(
    private readonly step: Step,
    private readonly record: (
      op: string,
      detail: string,
      payload?: unknown,
    ) => void,
  ) {}

  select(columns: string): this {
    this.record("select", columns);
    return this;
  }

  update(values: unknown): this {
    this.record("update", columnNames(values), values);
    return this;
  }

  insert(values: unknown): this {
    this.record("insert", columnNames(values), values);
    return this;
  }

  /** Records the column name only. The value is kept privately. */
  eq(column: string, value: unknown): this {
    this.record("eq", column, undefined);
    this.recordFilter(column, value);
    return this;
  }

  private recordFilter(column: string, value: unknown): void {
    this.record("filter", column, { column, value });
  }

  maybeSingle(): Promise<QueryResult> {
    return this.settle();
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

/** Steps are consumed in `from()` order, one per statement. */
function createClientDouble(
  steps: readonly Step[],
  options: { readonly throwFromClient?: boolean } = {},
) {
  const calls: { op: string; detail: string }[] = [];
  const tables: string[] = [];
  // Health-bearing or value-bearing. Never returned, never asserted directly.
  const payloads: { op: string; value: unknown }[] = [];
  const filters: { column: string; value: unknown }[] = [];
  let index = 0;

  const client = {
    from(table: string) {
      if (options.throwFromClient === true) {
        // The client itself failing before any builder exists.
        throw rawServerError();
      }

      const step = steps[index] ?? NO_ROW;
      index += 1;
      tables.push(table);

      return new FakeQuery(step, (op, detail, payload) => {
        if (op === "filter") {
          const entry = payload as { column: string; value: unknown };
          filters.push(entry);
          return;
        }

        calls.push({ op, detail });

        if (payload !== undefined) {
          payloads.push({ op, value: payload });
        }
      });
    },
  } as unknown as AppSupabaseClient;

  return {
    client,

    tables: () => [...new Set(tables)],

    count: (op: string) => calls.filter((call) => call.op === op).length,

    /** Safe: operation names in order. */
    ops: () => calls.map((call) => call.op),

    /** Safe: the column names a statement filtered on, in order. */
    filterColumns: () => filters.map((entry) => entry.column),

    /** Safe: filter columns outside the allowed scope set, by name only. */
    unexpectedFilterColumns: () =>
      filters
        .map((entry) => entry.column)
        .filter(
          (column) => !SCOPE_FILTERS.some(([allowed]) => allowed === column),
        ),

    /** Safe: the non-health column lists a statement named, in order. */
    details: (op: string) =>
      calls.filter((call) => call.op === op).map((call) => call.detail),

    /**
     * Whether the nth statement's filters are exactly the expected pairs.
     *
     * Compared here so only a boolean escapes: a mismatch cannot print either
     * side's values.
     */
    filtersMatch: (
      offset: number,
      expected: readonly [string, unknown][],
    ): boolean => {
      const slice = filters.slice(offset, offset + expected.length);

      return (
        slice.length === expected.length &&
        expected.every(([column, value], position) => {
          const found = slice[position];

          return found?.column === column && found.value === value;
        })
      );
    },

    filterCount: () => filters.length,

    /**
     * Whether the nth payload of one kind is exactly the expected object.
     *
     * Compared here so a mismatch cannot print the health values on either side.
     */
    payloadMatches: (op: string, occurrence: number, expected: unknown) => {
      const found = payloads.filter((entry) => entry.op === op)[occurrence];

      return (
        found !== undefined &&
        JSON.stringify(found.value) === JSON.stringify(expected)
      );
    },

    payloadCount: (op: string) =>
      payloads.filter((entry) => entry.op === op).length,
  };
}

describe("loadDailyCheckIn", () => {
  it("returns null when there is no row for the date", async () => {
    const double = createClientDouble([NO_ROW]);

    await expect(
      loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE),
    ).resolves.toBeNull();
  });

  it("returns a validated value when a row exists", async () => {
    const double = createClientDouble([
      {
        kind: "result",
        result: {
          data: { rpe: 6, overall_feeling: 3, pain_status: "none" },
          error: null,
        },
      },
    ]);

    const loaded = await loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE);

    // Reduced to a boolean, so a mismatch prints `false`, not the values.
    expect(
      loaded !== null &&
        loaded.rpe === VALID_INPUT.rpe &&
        loaded.overallFeeling === VALID_INPUT.overallFeeling &&
        loaded.painStatus === VALID_INPUT.painStatus,
    ).toBe(true);
  });

  it("raises rather than returning null when the read fails", async () => {
    // The distinction the whole module preserves: a refused read must never be
    // indistinguishable from "no check-in today".
    const probe = await probeFailure(
      loadDailyCheckIn(
        createClientDouble([failed("42501")]).client,
        USER_ID,
        LOCAL_DATE,
      ),
    );

    expect(probe.outcome).toBe("sanitized-error");
    expect(probe.intent).toBe("load");
    expect(probe.messageIsFixed).toBe(true);
  });

  it("classifies a refused read as denied and a transport failure as offline", async () => {
    const denied = await probeFailure(
      loadDailyCheckIn(
        createClientDouble([failed("42501")]).client,
        USER_ID,
        LOCAL_DATE,
      ),
    );
    const offline = await probeFailure(
      loadDailyCheckIn(
        createClientDouble([
          {
            kind: "result",
            result: {
              data: null,
              error: new TypeError("Network request failed"),
            },
          },
        ]).client,
        USER_ID,
        LOCAL_DATE,
      ),
    );

    expect(denied.failure).toBe("denied");
    expect(offline.failure).toBe("offline");
  });

  it("fails closed on an invalid row instead of returning it", async () => {
    const invalidRows: readonly [string, unknown][] = [
      [
        "rpe out of range",
        { rpe: 11, overall_feeling: 3, pain_status: "none" },
      ],
      ["fractional rpe", { rpe: 6.5, overall_feeling: 3, pain_status: "none" }],
      ["null feeling", { rpe: 6, overall_feeling: null, pain_status: "none" }],
      ["missing pain status", { rpe: 6, overall_feeling: 3 }],
      [
        "unknown pain status",
        { rpe: 6, overall_feeling: 3, pain_status: "moderate" },
      ],
      ["empty row", {}],
    ];

    const notFailedClosed: string[] = [];

    for (const [name, data] of invalidRows) {
      const double = createClientDouble([
        { kind: "result", result: { data, error: null } },
      ]);
      const probe = await probeFailure(
        loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE),
      );

      if (probe.outcome !== "sanitized-error") {
        notFailedClosed.push(name);
      }
    }

    // Case names only.
    expect(notFailedClosed).toEqual([]);
  });

  it("scopes the read to the exact user and the exact date", async () => {
    const double = createClientDouble([NO_ROW]);

    await loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE);

    expect(double.filterColumns()).toEqual([
      "athlete_profile_id",
      "check_in_date",
    ]);
    expect(double.filtersMatch(0, SCOPE_FILTERS)).toBe(true);
    expect(double.unexpectedFilterColumns()).toEqual([]);
    expect(double.tables()).toEqual(["daily_check_ins"]);
  });

  it("filters on a different user or date when asked to", async () => {
    const other = createClientDouble([NO_ROW]);
    await loadDailyCheckIn(other.client, OTHER_USER_ID, LOCAL_DATE);

    const otherDate = createClientDouble([NO_ROW]);
    await loadDailyCheckIn(otherDate.client, USER_ID, "2026-07-31");

    expect(
      other.filtersMatch(0, [
        ["athlete_profile_id", OTHER_USER_ID],
        ["check_in_date", LOCAL_DATE],
      ]),
    ).toBe(true);
    expect(
      otherDate.filtersMatch(0, [
        ["athlete_profile_id", USER_ID],
        ["check_in_date", "2026-07-31"],
      ]),
    ).toBe(true);
  });

  it("selects only the three health columns", async () => {
    const double = createClientDouble([NO_ROW]);

    await loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE);

    expect(double.details("select")).toEqual([
      "rpe, overall_feeling, pain_status",
    ]);
  });

  it("refuses a malformed date or user id without contacting the database", async () => {
    const cases: readonly [string, string, string][] = [
      ["empty user id", "", LOCAL_DATE],
      ["timestamp as the date", USER_ID, "2026-07-30T00:00:00.000Z"],
      ["empty date", USER_ID, ""],
      ["unpadded date", USER_ID, "2026-7-30"],
      ["impossible day", USER_ID, "2026-02-31"],
    ];

    const contacted: string[] = [];

    for (const [name, userId, date] of cases) {
      const double = createClientDouble([NO_ROW]);
      const probe = await probeFailure(
        loadDailyCheckIn(double.client, userId, date),
      );

      if (
        probe.outcome !== "sanitized-error" ||
        double.ops().length > 0 ||
        double.tables().length > 0 ||
        double.filterCount() > 0
      ) {
        contacted.push(name);
      }
    }

    expect(contacted).toEqual([]);
  });
});

describe("saveDailyCheckIn", () => {
  it("updates the existing row and issues no insert", async () => {
    const double = createClientDouble([MATCHED_ROW]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.count("update")).toBe(1);
    expect(double.count("insert")).toBe(0);
  });

  it("inserts after the update matches nothing", async () => {
    const double = createClientDouble([NO_ROW, INSERT_OK]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    // Update first, then insert. The order is the algorithm.
    expect(
      double.ops().filter((op) => op === "update" || op === "insert"),
    ).toEqual(["update", "insert"]);
  });

  it("updates only the three mutable health columns", async () => {
    const double = createClientDouble([MATCHED_ROW]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    // Column names only. Naming a fourth column would be refused by the
    // column-level grant with 42501.
    expect(double.details("update")).toEqual([
      "overall_feeling,pain_status,rpe",
    ]);
    expect(double.payloadMatches("update", 0, UPDATE_COLUMNS)).toBe(true);
  });

  it("inserts only the five approved columns", async () => {
    const double = createClientDouble([NO_ROW, INSERT_OK]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.details("insert")).toEqual([
      "athlete_profile_id,check_in_date,overall_feeling,pain_status,rpe",
    ]);
    expect(double.payloadMatches("insert", 0, INSERT_COLUMNS)).toBe(true);
  });

  it("takes the owner from the verified id, never from the input", async () => {
    const double = createClientDouble([NO_ROW, INSERT_OK]);

    // A caller trying to smuggle another athlete's id through the input object.
    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, {
      ...VALID_INPUT,
      athlete_profile_id: OTHER_USER_ID,
      athleteProfileId: OTHER_USER_ID,
      check_in_date: "2026-01-01",
    });

    expect(double.payloadMatches("insert", 0, INSERT_COLUMNS)).toBe(true);
  });

  it("scopes every write to the exact user and the exact date", async () => {
    const double = createClientDouble([NO_ROW, INSERT_OK]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.filterColumns()).toEqual([
      "athlete_profile_id",
      "check_in_date",
    ]);
    expect(double.filtersMatch(0, SCOPE_FILTERS)).toBe(true);
    expect(double.unexpectedFilterColumns()).toEqual([]);
    expect(double.tables()).toEqual(["daily_check_ins"]);
  });

  it("returns only a non-health sentinel from the update", async () => {
    const double = createClientDouble([MATCHED_ROW]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    // `id` and nothing else. The insert requests no representation at all.
    expect(double.details("select")).toEqual(["id"]);
  });

  it("resolves without returning any write response", async () => {
    const double = createClientDouble([MATCHED_ROW]);

    const returned = await saveDailyCheckIn(
      double.client,
      USER_ID,
      LOCAL_DATE,
      VALID_INPUT,
    );

    expect(returned).toBeUndefined();
  });

  it("retries the scoped update exactly once after a 23505 insert race", async () => {
    const double = createClientDouble([NO_ROW, UNIQUE_VIOLATION, MATCHED_ROW]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.count("update")).toBe(2);
    expect(double.count("insert")).toBe(1);
    expect(
      double.ops().filter((op) => op === "update" || op === "insert"),
    ).toEqual(["update", "insert", "update"]);
  });

  it("sends the same scoped payload and filters on the retry", async () => {
    const double = createClientDouble([NO_ROW, UNIQUE_VIOLATION, MATCHED_ROW]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.payloadCount("update")).toBe(2);
    expect(double.payloadMatches("update", 1, UPDATE_COLUMNS)).toBe(true);
    // Four filters in total: two for the first update, two for the retry.
    expect(double.filterCount()).toBe(4);
    expect(double.filtersMatch(2, SCOPE_FILTERS)).toBe(true);
    expect(double.unexpectedFilterColumns()).toEqual([]);
  });

  it("does not retry when the insert fails with any other code", async () => {
    const otherFailures: readonly [string, Step][] = [
      ["insufficient privilege", failed("42501")],
      ["rejected jwt", failed("PGRST301")],
      ["sanitized check violation", failed("22023")],
      ["foreign key violation", failed("23503")],
      [
        "no code at all",
        {
          kind: "result",
          result: { data: null, error: { message: "something went wrong" } },
        },
      ],
      [
        "transport failure",
        {
          kind: "result",
          result: {
            data: null,
            error: new TypeError("Network request failed"),
          },
        },
      ],
    ];

    const retried: string[] = [];

    for (const [name, step] of otherFailures) {
      const double = createClientDouble([NO_ROW, step]);
      const probe = await probeFailure(
        saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
      );

      if (
        probe.outcome !== "sanitized-error" ||
        double.count("update") !== 1 ||
        double.count("insert") !== 1
      ) {
        retried.push(name);
      }
    }

    expect(retried).toEqual([]);
  });

  it("raises a sanitized error when the retry update matches nothing", async () => {
    const double = createClientDouble([NO_ROW, UNIQUE_VIOLATION, NO_ROW]);

    const probe = await probeFailure(
      saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
    );

    // The constraint says the row exists but the scoped update reached nothing,
    // so the answers were not stored and this must not read as success.
    expect(probe.outcome).toBe("sanitized-error");
    expect(probe.intent).toBe("save");
    expect(double.count("update")).toBe(2);
  });

  it("raises when the first update itself fails", async () => {
    const double = createClientDouble([failed("42501")]);

    const probe = await probeFailure(
      saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
    );

    expect(probe.failure).toBe("denied");
    expect(double.count("insert")).toBe(0);
  });

  it("validates the input before issuing any statement", async () => {
    const invalidInputs: readonly [string, unknown][] = [
      ["null input", null],
      ["empty input", {}],
      ["nothing chosen", { rpe: null, overallFeeling: null, painStatus: null }],
      ["rpe unchosen", { overallFeeling: 3, painStatus: "none" }],
      ["rpe above the maximum", { ...VALID_INPUT, rpe: 11 }],
      ["rpe below the minimum", { ...VALID_INPUT, rpe: -1 }],
      ["fractional rpe", { ...VALID_INPUT, rpe: 6.5 }],
      ["feeling above the maximum", { ...VALID_INPUT, overallFeeling: 6 }],
      ["feeling below the minimum", { ...VALID_INPUT, overallFeeling: 0 }],
      ["unknown pain status", { ...VALID_INPUT, painStatus: "mild" }],
      ["column naming", { rpe: 6, overall_feeling: 3, pain_status: "none" }],
    ];

    const contacted: string[] = [];

    for (const [name, input] of invalidInputs) {
      const double = createClientDouble([MATCHED_ROW]);
      const probe = await probeFailure(
        saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, input),
      );

      if (probe.outcome !== "sanitized-error" || double.ops().length > 0) {
        contacted.push(name);
      }
    }

    expect(contacted).toEqual([]);
  });

  it("refuses a malformed date or user id without issuing any statement", async () => {
    const cases: readonly [string, string, string][] = [
      ["empty user id", "", LOCAL_DATE],
      ["timestamp as the date", USER_ID, "2026-07-30T00:00:00.000Z"],
      ["slashed date", USER_ID, "2026/07/30"],
      ["NaN date", USER_ID, "NaN-NaN-NaN"],
      ["impossible day", USER_ID, "2026-04-31"],
    ];

    const contacted: string[] = [];

    for (const [name, userId, date] of cases) {
      const double = createClientDouble([MATCHED_ROW]);
      const probe = await probeFailure(
        saveDailyCheckIn(double.client, userId, date, VALID_INPUT),
      );

      if (probe.outcome !== "sanitized-error" || double.ops().length > 0) {
        contacted.push(name);
      }
    }

    expect(contacted).toEqual([]);
  });

  it("never exposes a raw database message, code, detail, or hint", async () => {
    const double = createClientDouble([
      {
        kind: "result",
        result: {
          data: null,
          error: {
            code: "42501",
            message:
              'new row violates row-level security policy for table "daily_check_ins"',
            details: "Failing row contains (rpe, overall_feeling, pain_status)",
            hint: "check daily_check_ins_update_own",
          },
        },
      },
    ]);

    const probe = await probeFailure(
      saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
    );

    expect(probe.outcome).toBe("sanitized-error");
    // The message is one of the fixed application strings, and the error carries
    // no cause and only its three enum-ish fields.
    expect(probe.messageIsFixed).toBe(true);
    expect(probe.withoutCause).toBe(true);
    expect(probe.fields).toEqual(["failure", "intent", "name"]);
  });
});

describe("unexpected throws and rejections are sanitized", () => {
  /**
   * Each case makes the client fail in a way that is not a resolved
   * `{ error }` — the shape the repository was originally written around.
   * `probeFailure` reports only whether the escape was sanitized.
   */
  const cases: readonly [string, () => Promise<unknown>, "load" | "save"][] = [
    [
      "synchronous throw from client.from on load",
      () =>
        loadDailyCheckIn(
          createClientDouble([], { throwFromClient: true }).client,
          USER_ID,
          LOCAL_DATE,
        ),
      "load",
    ],
    [
      "synchronous throw from client.from on save",
      () =>
        saveDailyCheckIn(
          createClientDouble([], { throwFromClient: true }).client,
          USER_ID,
          LOCAL_DATE,
          VALID_INPUT,
        ),
      "save",
    ],
    [
      "rejected load query",
      () =>
        loadDailyCheckIn(
          createClientDouble([{ kind: "reject" }]).client,
          USER_ID,
          LOCAL_DATE,
        ),
      "load",
    ],
    [
      "thrown load query",
      () =>
        loadDailyCheckIn(
          createClientDouble([{ kind: "throw" }]).client,
          USER_ID,
          LOCAL_DATE,
        ),
      "load",
    ],
    [
      "rejected update",
      () =>
        saveDailyCheckIn(
          createClientDouble([{ kind: "reject" }]).client,
          USER_ID,
          LOCAL_DATE,
          VALID_INPUT,
        ),
      "save",
    ],
    [
      "rejected insert",
      () =>
        saveDailyCheckIn(
          createClientDouble([NO_ROW, { kind: "reject" }]).client,
          USER_ID,
          LOCAL_DATE,
          VALID_INPUT,
        ),
      "save",
    ],
    [
      "thrown insert",
      () =>
        saveDailyCheckIn(
          createClientDouble([NO_ROW, { kind: "throw" }]).client,
          USER_ID,
          LOCAL_DATE,
          VALID_INPUT,
        ),
      "save",
    ],
    [
      "rejected race-retry update",
      () =>
        saveDailyCheckIn(
          createClientDouble([NO_ROW, UNIQUE_VIOLATION, { kind: "reject" }])
            .client,
          USER_ID,
          LOCAL_DATE,
          VALID_INPUT,
        ),
      "save",
    ],
    [
      "thrown race-retry update",
      () =>
        saveDailyCheckIn(
          createClientDouble([NO_ROW, UNIQUE_VIOLATION, { kind: "throw" }])
            .client,
          USER_ID,
          LOCAL_DATE,
          VALID_INPUT,
        ),
      "save",
    ],
  ];

  it("converts every unexpected failure into a sanitized error", async () => {
    const escaped: string[] = [];

    for (const [name, run] of cases) {
      const probe = await probeFailure(run());

      if (probe.outcome !== "sanitized-error") {
        // Only the case name. The raw error never leaves `probeFailure`.
        escaped.push(name);
      }
    }

    expect(escaped).toEqual([]);
  });

  it("keeps the right intent on every unexpected failure", async () => {
    const wrongIntent: string[] = [];

    for (const [name, run, intent] of cases) {
      const probe = await probeFailure(run());

      if (probe.intent !== intent) {
        wrongIntent.push(name);
      }
    }

    expect(wrongIntent).toEqual([]);
  });

  it("retains nothing from the raw failure", async () => {
    const leaked: string[] = [];

    for (const [name, run] of cases) {
      const probe = await probeFailure(run());

      if (
        !probe.messageIsFixed ||
        !probe.withoutCause ||
        probe.fields.join(",") !== "failure,intent,name"
      ) {
        leaked.push(name);
      }
    }

    expect(leaked).toEqual([]);
  });

  it("covers every required escape route", () => {
    expect(cases.length).toBeGreaterThanOrEqual(9);
  });
});
