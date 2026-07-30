import { describe, expect, it } from "vitest";

import type { AppSupabaseClient } from "../../lib/supabase/app-client";
import { captureError } from "../../test-support/capture-error";

import { loadDailyCheckIn, saveDailyCheckIn } from "./check-in-repository";
import type { DailyCheckIn } from "./domain";
import { CheckInDataError } from "./errors";

/**
 * Repository behaviour against a hand-written client double. No network, no local
 * database, no new dependency.
 *
 * **Failure-output safety.** Health literals here are synthetic, but a failing
 * assertion must still not print one. The double therefore records only
 * non-health diagnostics — an operation name, a sorted column-name list, and a
 * `column=value` filter description for the user id and the date — while the
 * health-bearing payloads are kept private and only ever compared *inside* a
 * helper that returns a boolean. Nothing in this file compares or snapshots a
 * whole request or response object, and no captured error or payload is passed
 * as an assertion message.
 */

const USER_ID = "00000000-0000-4000-9000-000000000013";
const OTHER_USER_ID = "00000000-0000-4000-9000-0000000000ff";
const LOCAL_DATE = "2026-07-30";

const VALID_INPUT: DailyCheckIn = {
  rpe: 6,
  overallFeeling: 3,
  painStatus: "none",
};

type QueryResult = { data: unknown; error: unknown };

/** Only non-health text ever lands in a recorded call. */
type Recorded = { readonly op: string; readonly detail: string };

const NO_ROW: QueryResult = { data: null, error: null };
const MATCHED_ROW: QueryResult = {
  data: { id: "11111111-1111-4111-9111-111111111111" },
  error: null,
};
const INSERT_OK: QueryResult = { data: null, error: null };
const UNIQUE_VIOLATION: QueryResult = { data: null, error: { code: "23505" } };

function columnNames(values: unknown): string {
  return typeof values === "object" && values !== null
    ? Object.keys(values).sort().join(",")
    : "";
}

/**
 * A minimal stand-in for the PostgREST builder.
 *
 * Every method returns `this` and the object is thenable, so an awaited chain and
 * a `.maybeSingle()` chain both resolve to the queued result. There is
 * deliberately **no `upsert` method**: if the repository ever reached for one,
 * these tests would fail rather than quietly exercise a prohibited write.
 */
class FakeQuery implements PromiseLike<QueryResult> {
  constructor(
    private readonly result: QueryResult,
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

  eq(column: string, value: unknown): this {
    this.record("eq", `${column}=${String(value)}`);
    return this;
  }

  async maybeSingle(): Promise<QueryResult> {
    return this.result;
  }

  then<TResult1 = QueryResult, TResult2 = never>(
    onfulfilled?:
      ((value: QueryResult) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): PromiseLike<TResult1 | TResult2> {
    return Promise.resolve(this.result).then(onfulfilled, onrejected);
  }
}

/** Results are consumed in `from()` order, one per statement. */
function createClientDouble(results: readonly QueryResult[]) {
  const calls: Recorded[] = [];
  const tables: string[] = [];
  // Health-bearing. Never returned, never asserted on directly.
  const payloads: { op: string; value: unknown }[] = [];
  let index = 0;

  const client = {
    from(table: string) {
      const result = results[index] ?? NO_ROW;
      index += 1;
      tables.push(table);

      return new FakeQuery(result, (op, detail, payload) => {
        calls.push({ op, detail });

        if (payload !== undefined) {
          payloads.push({ op, value: payload });
        }
      });
    },
  } as unknown as AppSupabaseClient;

  return {
    client,

    /** Distinct tables touched. */
    tables: () => [...new Set(tables)],

    /** How many statements of one kind ran. */
    count: (op: string) => calls.filter((call) => call.op === op).length,

    /** The non-health detail strings for one operation, in order. */
    details: (op: string) =>
      calls.filter((call) => call.op === op).map((call) => call.detail),

    /** Every operation name, in order. */
    ops: () => calls.map((call) => call.op),

    /**
     * Whether the nth payload of one kind is exactly the expected object.
     *
     * The comparison happens here and only a boolean escapes, so a mismatch
     * cannot print the health values on either side.
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
        data: { rpe: 6, overall_feeling: 3, pain_status: "none" },
        error: null,
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
    const double = createClientDouble([
      { data: null, error: { code: "42501" } },
    ]);

    // The distinction the whole module preserves: a refused read must never be
    // indistinguishable from "no check-in today".
    await expect(
      loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE),
    ).rejects.toThrow(CheckInDataError);
  });

  it("classifies a refused read as denied and a transport failure as offline", async () => {
    const denied = await captureError(
      loadDailyCheckIn(
        createClientDouble([{ data: null, error: { code: "42501" } }]).client,
        USER_ID,
        LOCAL_DATE,
      ),
      CheckInDataError,
    );
    const offline = await captureError(
      loadDailyCheckIn(
        createClientDouble([
          { data: null, error: new TypeError("Network request failed") },
        ]).client,
        USER_ID,
        LOCAL_DATE,
      ),
      CheckInDataError,
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

    const accepted: string[] = [];

    for (const [name, data] of invalidRows) {
      const double = createClientDouble([{ data, error: null }]);

      try {
        await loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE);
        accepted.push(name);
      } catch {
        // Expected. The captured error is deliberately not inspected here.
      }
    }

    // Case names only.
    expect(accepted).toEqual([]);
  });

  it("scopes the read to the exact user and the exact date", async () => {
    const double = createClientDouble([NO_ROW]);

    await loadDailyCheckIn(double.client, USER_ID, LOCAL_DATE);

    expect(double.details("eq")).toEqual([
      `athlete_profile_id=${USER_ID}`,
      `check_in_date=${LOCAL_DATE}`,
    ]);
    expect(double.tables()).toEqual(["daily_check_ins"]);
  });

  it("produces a different filter for a different user or date", async () => {
    const other = createClientDouble([NO_ROW]);
    await loadDailyCheckIn(other.client, OTHER_USER_ID, LOCAL_DATE);

    const otherDate = createClientDouble([NO_ROW]);
    await loadDailyCheckIn(otherDate.client, USER_ID, "2026-07-31");

    expect(other.details("eq")[0]).toBe(`athlete_profile_id=${OTHER_USER_ID}`);
    expect(otherDate.details("eq")[1]).toBe("check_in_date=2026-07-31");
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
    ];

    const contacted: string[] = [];

    for (const [name, userId, date] of cases) {
      const double = createClientDouble([NO_ROW]);

      await expect(
        loadDailyCheckIn(double.client, userId, date),
      ).rejects.toThrow(CheckInDataError);

      if (double.ops().length > 0 || double.tables().length > 0) {
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
    expect(
      double.payloadMatches("update", 0, {
        rpe: VALID_INPUT.rpe,
        overall_feeling: VALID_INPUT.overallFeeling,
        pain_status: VALID_INPUT.painStatus,
      }),
    ).toBe(true);
  });

  it("inserts only the five approved columns", async () => {
    const double = createClientDouble([NO_ROW, INSERT_OK]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.details("insert")).toEqual([
      "athlete_profile_id,check_in_date,overall_feeling,pain_status,rpe",
    ]);
    expect(
      double.payloadMatches("insert", 0, {
        athlete_profile_id: USER_ID,
        check_in_date: LOCAL_DATE,
        rpe: VALID_INPUT.rpe,
        overall_feeling: VALID_INPUT.overallFeeling,
        pain_status: VALID_INPUT.painStatus,
      }),
    ).toBe(true);
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

    expect(
      double.payloadMatches("insert", 0, {
        athlete_profile_id: USER_ID,
        check_in_date: LOCAL_DATE,
        rpe: VALID_INPUT.rpe,
        overall_feeling: VALID_INPUT.overallFeeling,
        pain_status: VALID_INPUT.painStatus,
      }),
    ).toBe(true);
  });

  it("scopes every write to the exact user and the exact date", async () => {
    const double = createClientDouble([NO_ROW, INSERT_OK]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.details("eq")).toEqual([
      `athlete_profile_id=${USER_ID}`,
      `check_in_date=${LOCAL_DATE}`,
    ]);
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

  it("sends the same scoped payload on the retry", async () => {
    const double = createClientDouble([NO_ROW, UNIQUE_VIOLATION, MATCHED_ROW]);

    await saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT);

    expect(double.payloadCount("update")).toBe(2);
    expect(
      double.payloadMatches("update", 1, {
        rpe: VALID_INPUT.rpe,
        overall_feeling: VALID_INPUT.overallFeeling,
        pain_status: VALID_INPUT.painStatus,
      }),
    ).toBe(true);
    // Four filters in total: two for the first update, two for the retry.
    expect(double.details("eq").slice(2)).toEqual([
      `athlete_profile_id=${USER_ID}`,
      `check_in_date=${LOCAL_DATE}`,
    ]);
  });

  it("does not retry when the insert fails with any other code", async () => {
    const otherFailures: readonly [string, unknown][] = [
      ["insufficient privilege", { code: "42501" }],
      ["rejected jwt", { code: "PGRST301" }],
      ["sanitized check violation", { code: "22023" }],
      ["foreign key violation", { code: "23503" }],
      ["no code at all", { message: "something went wrong" }],
      ["transport failure", new TypeError("Network request failed")],
    ];

    const retried: string[] = [];

    for (const [name, error] of otherFailures) {
      const double = createClientDouble([NO_ROW, { data: null, error }]);

      await expect(
        saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
      ).rejects.toThrow(CheckInDataError);

      if (double.count("update") !== 1 || double.count("insert") !== 1) {
        retried.push(name);
      }
    }

    expect(retried).toEqual([]);
  });

  it("raises a sanitized error when the retry update matches nothing", async () => {
    const double = createClientDouble([NO_ROW, UNIQUE_VIOLATION, NO_ROW]);

    const error = await captureError(
      saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
      CheckInDataError,
    );

    // The constraint says the row exists but the scoped update reached nothing,
    // so the answers were not stored and this must not read as success.
    expect(error.intent).toBe("save");
    expect(double.count("update")).toBe(2);
  });

  it("raises when the first update itself fails", async () => {
    const double = createClientDouble([
      { data: null, error: { code: "42501" } },
    ]);

    const error = await captureError(
      saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
      CheckInDataError,
    );

    expect(error.failure).toBe("denied");
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

      await expect(
        saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, input),
      ).rejects.toThrow(CheckInDataError);

      if (double.ops().length > 0) {
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
    ];

    const contacted: string[] = [];

    for (const [name, userId, date] of cases) {
      const double = createClientDouble([MATCHED_ROW]);

      await expect(
        saveDailyCheckIn(double.client, userId, date, VALID_INPUT),
      ).rejects.toThrow(CheckInDataError);

      if (double.ops().length > 0) {
        contacted.push(name);
      }
    }

    expect(contacted).toEqual([]);
  });

  it("never exposes a raw database message, code, detail, or hint", async () => {
    const double = createClientDouble([
      {
        data: null,
        error: {
          code: "42501",
          message:
            'new row violates row-level security policy for table "daily_check_ins"',
          details: "Failing row contains (rpe, overall_feeling, pain_status)",
          hint: "check daily_check_ins_update_own",
        },
      },
    ]);

    const error = await captureError(
      saveDailyCheckIn(double.client, USER_ID, LOCAL_DATE, VALID_INPUT),
      CheckInDataError,
    );

    // The message is a fixed application string, so printing it here is safe.
    const leaks = [
      "row-level security",
      "daily_check_ins",
      "Failing row",
      "42501",
      "rpe",
      "overall_feeling",
      "pain_status",
      "hint",
    ].filter((fragment) => error.message.includes(fragment));

    expect(leaks).toEqual([]);
  });
});
