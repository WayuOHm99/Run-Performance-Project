import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { EXPECTED_BASELINE } from "./accounts.mjs";
import {
  BASELINE_DEADLINE_MS,
  BASELINE_MAX_ATTEMPTS,
  BASELINE_QUICK_ATTEMPTS,
  BASELINE_RETRY_DELAY_MS,
  BASELINE_SQL,
  CANARY_SQL,
  cliQueryPathLooksHealthy,
  compareBaseline,
  DemoBaselineError,
  formatBaseline,
  parseBaselineRow,
  readBaseline,
} from "./baseline.mjs";

function statusRow(overrides = {}) {
  return JSON.stringify({
    boundary: "synthetic-boundary",
    warning: "synthetic warning text",
    rows: [{ ...EXPECTED_BASELINE, ...overrides }],
  });
}

describe("BASELINE_SQL", () => {
  // The guarantee that verifying the baseline cannot become a way to read
  // protected health data or identifiers.
  it("selects only count aggregates", () => {
    // Line-oriented rather than paren-matched: `count(*)` contains a closing
    // paren, so a `\([^)]*\)` pattern would stop inside the aggregate and
    // silently pass on any subquery.
    const subqueryLines = BASELINE_SQL.split("\n").filter((line) =>
      line.includes("(select"),
    );

    assert.ok(subqueryLines.length > 0);

    for (const line of subqueryLines) {
      assert.match(line.trim(), /^\(select count\(\*\) from /);
    }
  });

  it("names no health column", () => {
    for (const column of [
      "rpe",
      "overall_feeling",
      "pain_status",
      "check_in_date",
    ]) {
      assert.ok(
        !BASELINE_SQL.includes(column),
        `the baseline query must not name ${column}`,
      );
    }
  });

  it("names no identifier column that would return a person", () => {
    for (const column of ["athlete_profile_id", "profile_id", "user_id"]) {
      assert.ok(!BASELINE_SQL.includes(column));
    }
  });

  it("counts the check-in table without reading inside it", () => {
    assert.ok(BASELINE_SQL.includes("count(*) from public.daily_check_ins"));
  });

  it("covers every expected baseline key", () => {
    for (const key of Object.keys(EXPECTED_BASELINE)) {
      assert.ok(BASELINE_SQL.includes(`as ${key}`), `missing count: ${key}`);
    }
  });
});

describe("EXPECTED_BASELINE", () => {
  // Decisions 8 and 9, asserted rather than merely documented.
  it("is decision 8 and decision 9 exactly", () => {
    assert.deepEqual(EXPECTED_BASELINE, {
      auth_users: 2,
      example_test_users: 2,
      profiles: 2,
      named_profiles: 2,
      teams: 1,
      active_memberships: 2,
      active_athlete_memberships: 1,
      active_coach_memberships: 1,
      sharing_grants: 0,
      daily_check_ins: 0,
    });
  });

  it("requires zero consent and zero health rows", () => {
    assert.equal(EXPECTED_BASELINE.sharing_grants, 0);
    assert.equal(EXPECTED_BASELINE.daily_check_ins, 0);
  });
});

describe("parseBaselineRow", () => {
  it("reads the expected counts", () => {
    assert.deepEqual({ ...parseBaselineRow(statusRow()) }, EXPECTED_BASELINE);
  });

  it("copies only the expected keys, never extra columns", () => {
    const withExtra = JSON.stringify({
      rows: [
        { ...EXPECTED_BASELINE, athlete_email: "leak@example.test", rpe: 9 },
      ],
    });

    const counts = parseBaselineRow(withExtra);

    assert.deepEqual(
      Object.keys(counts).sort(),
      Object.keys(EXPECTED_BASELINE).sort(),
    );
    assert.ok(!JSON.stringify(counts).includes("leak@example.test"));
    assert.ok(!("rpe" in counts));
  });

  it("rejects a malformed document without quoting it", () => {
    try {
      parseBaselineRow('{ "rows": [ broken');
      assert.fail("expected a rejection");
    } catch (error) {
      assert.ok(error instanceof DemoBaselineError);
      assert.ok(!error.message.includes("broken"));
    }
  });

  it("rejects a result that is not exactly one row", () => {
    assert.throws(
      () => parseBaselineRow(JSON.stringify({ rows: [] })),
      DemoBaselineError,
    );
    assert.throws(
      () =>
        parseBaselineRow(
          JSON.stringify({ rows: [EXPECTED_BASELINE, EXPECTED_BASELINE] }),
        ),
      DemoBaselineError,
    );
  });

  // Round 8. Both structural shapes are retryable — the Product Owner hit the
  // no-row-set one three times running and it cleared on its own — but they
  // keep distinct messages so an exhaustion still says which occurred.
  describe("classification of a wrong row set", () => {
    for (const [label, rows] of [
      ["empty", []],
      ["two rows", [EXPECTED_BASELINE, EXPECTED_BASELINE]],
    ]) {
      it(`marks an array of the wrong length retryable (${label})`, () => {
        try {
          parseBaselineRow(JSON.stringify({ rows }));
          assert.fail("expected a rejection");
        } catch (error) {
          assert.equal(
            error.message,
            "The baseline query did not return exactly one row.",
          );
          assert.equal(error.retryable, true);
        }
      });
    }

    for (const [label, document] of [
      ["empty object", {}],
      ["null rows", { rows: null }],
      ["object rows", { rows: {} }],
      ["string rows", { rows: "1" }],
      ["numeric rows", { rows: 1 }],
      ["envelope without rows", { boundary: "b", warning: "w" }],
      ["document that is not an object", 5],
      ["null document", null],
    ]) {
      it(`marks a missing or non-array row set retryable (${label})`, () => {
        try {
          parseBaselineRow(JSON.stringify(document));
          assert.fail("expected a rejection");
        } catch (error) {
          assert.ok(error instanceof DemoBaselineError);
          assert.equal(
            error.message,
            "The baseline query returned no row set.",
          );
          assert.equal(error.retryable, true);
        }
      });
    }

    // The two retryable shapes must stay distinguishable. If these ever
    // collapse into one message, an exhaustion stops saying which branch fired.
    it("keeps the two structural messages distinct", () => {
      const noRowSet = (() => {
        try {
          parseBaselineRow(JSON.stringify({}));
        } catch (error) {
          return error.message;
        }
      })();
      const wrongLength = (() => {
        try {
          parseBaselineRow(JSON.stringify({ rows: [] }));
        } catch (error) {
          return error.message;
        }
      })();

      assert.notEqual(noRowSet, wrongLength);
      assert.equal(noRowSet, "The baseline query returned no row set.");
      assert.equal(
        wrongLength,
        "The baseline query did not return exactly one row.",
      );
    });
  });

  // Round 9: a row set is a row set whether or not it arrives wrapped. This is
  // defensive against contract drift, not a fix for an observed shape — the
  // pinned CLI emitted the envelope in every one of round 9's structural probes.
  it("accepts a bare array as well as the boundary envelope", () => {
    const bare = JSON.stringify([EXPECTED_BASELINE]);

    assert.deepEqual({ ...parseBaselineRow(bare) }, EXPECTED_BASELINE);
  });

  it("still requires exactly one row in a bare array", () => {
    assert.throws(
      () => parseBaselineRow(JSON.stringify([])),
      (error) => {
        assert.equal(
          error.message,
          "The baseline query did not return exactly one row.",
        );
        assert.equal(error.retryable, true);

        return true;
      },
    );
  });

  it("rejects a non-integer count", () => {
    assert.throws(
      () => parseBaselineRow(statusRow({ profiles: "2" })),
      DemoBaselineError,
    );
    assert.throws(
      () => parseBaselineRow(statusRow({ profiles: null })),
      DemoBaselineError,
    );
  });
});

describe("compareBaseline", () => {
  it("reports nothing when the baseline matches", () => {
    assert.deepEqual(compareBaseline(EXPECTED_BASELINE), []);
  });

  it("reports every mismatch at once", () => {
    const mismatches = compareBaseline({
      ...EXPECTED_BASELINE,
      profiles: 3,
      sharing_grants: 1,
    });

    assert.deepEqual(mismatches.map((mismatch) => mismatch.key).sort(), [
      "profiles",
      "sharing_grants",
    ]);
  });

  // Seeded consent is the failure this whole task exists to prevent.
  it("fails a baseline carrying a seeded grant or check-in", () => {
    assert.equal(
      compareBaseline({ ...EXPECTED_BASELINE, sharing_grants: 1 }).length,
      1,
    );
    assert.equal(
      compareBaseline({ ...EXPECTED_BASELINE, daily_check_ins: 1 }).length,
      1,
    );
  });

  it("treats a missing count as a mismatch rather than a pass", () => {
    assert.equal(
      compareBaseline({}).length,
      Object.keys(EXPECTED_BASELINE).length,
    );
  });
});

// Every test here injects both the query and the wait, so nothing sleeps and
// nothing depends on a real clock, a real CLI, or a real database.
describe("readBaseline", () => {
  // A recognisable value that only ever exists inside the fake CLI's response.
  // If it turns up in a message, a stack, or a property, something copied the
  // response into the error.
  const SENTINEL = "SENTINEL-cli-response-must-not-escape";

  // The three structural shapes, all carrying the sentinel so any leak shows.
  const noRowSet = JSON.stringify({ boundary: SENTINEL, warning: SENTINEL });
  const nonArrayRows = JSON.stringify({ rows: SENTINEL, warning: SENTINEL });
  const wrongCardinality = JSON.stringify({
    boundary: SENTINEL,
    warning: SENTINEL,
    rows: [],
  });

  const HEALTHY_CANARY = JSON.stringify({ rows: [{ ok: 1 }] });
  const BROKEN_CANARY = JSON.stringify({ warning: SENTINEL });

  // Routes by SQL, so baseline reads and canary probes are counted separately
  // and the clock only moves when the code under test actually waits.
  function harness({ baseline = [], canary = BROKEN_CANARY } = {}) {
    const baselineCalls = [];
    const canaryCalls = [];
    const waits = [];
    let clock = 0;

    const query = async (sql) => {
      if (sql === CANARY_SQL) {
        canaryCalls.push(sql);

        if (canary === "throw") {
          throw new Error(`canary transport failed ${SENTINEL}`);
        }

        return typeof canary === "function"
          ? canary(canaryCalls.length)
          : canary;
      }

      baselineCalls.push(sql);

      const response = baseline[baselineCalls.length - 1];

      if (response === undefined) {
        throw new Error(
          "the baseline query was called more times than scripted",
        );
      }

      return response;
    };

    return {
      query,
      baselineCalls,
      canaryCalls,
      waits,
      wait: async (ms) => {
        waits.push(ms);
        clock += ms;
      },
      now: () => clock,
    };
  }

  const notReady = wrongCardinality;

  it("recovers when a structural failure is followed by one valid row", async () => {
    const h = harness({ baseline: [notReady, statusRow()] });

    const counts = await readBaseline(h);

    assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
    assert.equal(h.baselineCalls.length, 2);
    assert.deepEqual(h.waits, [BASELINE_RETRY_DELAY_MS]);
    // Inside the quick allowance, so no diagnosis was needed.
    assert.equal(h.canaryCalls.length, 0);
  });

  it("passes the count-only SQL on every baseline attempt", async () => {
    const h = harness({ baseline: [notReady, statusRow()] });

    await readBaseline(h);

    assert.deepEqual(h.baselineCalls, [BASELINE_SQL, BASELINE_SQL]);
  });

  // Round 9's production bound, pinned so it cannot drift silently.
  it("holds the round 9 production bound", () => {
    assert.equal(BASELINE_QUICK_ATTEMPTS, 3);
    assert.equal(BASELINE_MAX_ATTEMPTS, 30);
    assert.equal(BASELINE_RETRY_DELAY_MS, 1000);
    assert.equal(BASELINE_DEADLINE_MS, 60_000);

    // The deadline is the binding constraint in practice: 30 attempts at a
    // second of waiting plus a ~1.5s query each would run well past 60s.
    assert.ok(
      BASELINE_MAX_ATTEMPTS * BASELINE_RETRY_DELAY_MS >
        BASELINE_DEADLINE_MS / 3,
    );
  });

  // The failure boundary: each structural shape, repeated past the quick
  // allowance, recovers as long as the canary shows the path is unhealthy.
  for (const [label, transient] of [
    ["missing rows", noRowSet],
    ["non-array rows", nonArrayRows],
    ["object rows", JSON.stringify({ rows: { leaked: SENTINEL } })],
    ["wrong cardinality", wrongCardinality],
  ]) {
    it(`recovers when ${label} repeats well past the quick allowance`, async () => {
      const h = harness({
        baseline: [...Array.from({ length: 8 }, () => transient), statusRow()],
        canary: BROKEN_CANARY,
      });

      const counts = await readBaseline(h);

      assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
      assert.equal(h.baselineCalls.length, 9);
      assert.equal(h.waits.length, 8);
      // Consulted once per retry beyond the quick allowance.
      assert.equal(h.canaryCalls.length, 8 - BASELINE_QUICK_ATTEMPTS + 1);
    });

    it(`recovers on the very last attempt when ${label} persists`, async () => {
      const h = harness({
        baseline: [
          ...Array.from({ length: BASELINE_MAX_ATTEMPTS - 1 }, () => transient),
          statusRow(),
        ],
        canary: BROKEN_CANARY,
      });

      const counts = await readBaseline(h);

      assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
      assert.equal(h.baselineCalls.length, BASELINE_MAX_ATTEMPTS);
      assert.equal(h.waits.length, BASELINE_MAX_ATTEMPTS - 1);
    });
  }

  // Evidence-based termination: a healthy canary proves the transport is fine,
  // so the structural failure will not clear and waiting is pointless.
  for (const [label, response, message] of [
    ["missing rows", noRowSet, "The baseline query returned no row set."],
    ["non-array rows", nonArrayRows, "The baseline query returned no row set."],
    [
      "wrong cardinality",
      wrongCardinality,
      "The baseline query did not return exactly one row.",
    ],
  ]) {
    it(`stops at the quick allowance for ${label} when the canary is healthy`, async () => {
      const h = harness({
        baseline: Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => response),
        canary: HEALTHY_CANARY,
      });

      await assert.rejects(
        () => readBaseline(h),
        (error) => {
          assert.ok(error instanceof DemoBaselineError);
          assert.equal(error.message, message);

          return true;
        },
      );

      // Exactly the quick allowance, one canary, and no wait after the stop.
      assert.equal(h.baselineCalls.length, BASELINE_QUICK_ATTEMPTS);
      assert.equal(h.canaryCalls.length, 1);
      assert.equal(h.waits.length, BASELINE_QUICK_ATTEMPTS - 1);
    });

    it(`exhausts the attempt ceiling for persistent ${label} when the canary stays broken`, async () => {
      const h = harness({
        baseline: Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => response),
        canary: BROKEN_CANARY,
      });

      await assert.rejects(
        () => readBaseline(h),
        (error) => {
          assert.ok(error instanceof DemoBaselineError);
          assert.equal(error.message, message);

          return true;
        },
      );

      assert.equal(h.baselineCalls.length, BASELINE_MAX_ATTEMPTS);
      assert.equal(h.waits.length, BASELINE_MAX_ATTEMPTS - 1);

      for (const ms of h.waits) {
        assert.equal(ms, BASELINE_RETRY_DELAY_MS);
      }
    });
  }

  // A canary whose transport throws is evidence of an unhealthy path, not a
  // reason to give up.
  it("keeps waiting when the canary itself fails to run", async () => {
    const h = harness({
      baseline: [noRowSet, noRowSet, noRowSet, noRowSet, statusRow()],
      canary: "throw",
    });

    const counts = await readBaseline(h);

    assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
    assert.equal(h.baselineCalls.length, 5);
  });

  // The wall clock is the outer bound, and it binds before the attempt ceiling
  // when each wait is long enough.
  it("stops at the deadline even while the canary stays broken", async () => {
    const h = harness({
      baseline: Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => noRowSet),
      canary: BROKEN_CANARY,
    });

    await assert.rejects(
      () => readBaseline({ ...h, deadlineMs: 5000 }),
      DemoBaselineError,
    );

    // Waits advance the injected clock, so the deadline is reached after five
    // of them and the loop stops well short of the 30-attempt ceiling.
    assert.equal(h.waits.length, 5);
    assert.equal(h.baselineCalls.length, 6);
    assert.ok(h.baselineCalls.length < BASELINE_MAX_ATTEMPTS);
  });

  // The seams exist for these tests; they must not be a way to exceed or remove
  // the production bound. A zero or NaN budget would otherwise skip the loop and
  // leave no error to throw at all.
  it("falls back to the production ceiling when the attempts seam is out of bounds", async () => {
    for (const maxAttempts of [
      0,
      -1,
      2.5,
      Number.NaN,
      Number.POSITIVE_INFINITY,
      // Above the production ceiling: must not be honoured.
      31,
      1000,
    ]) {
      const h = harness({
        baseline: Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => notReady),
        canary: BROKEN_CANARY,
      });

      await assert.rejects(
        () => readBaseline({ ...h, maxAttempts }),
        DemoBaselineError,
      );
      assert.equal(
        h.baselineCalls.length,
        BASELINE_MAX_ATTEMPTS,
        `maxAttempts=${maxAttempts} escaped the ceiling`,
      );
    }
  });

  it("never waits longer than the production delay", async () => {
    for (const delayMs of [
      Number.NaN,
      Number.POSITIVE_INFINITY,
      -1,
      60_000,
      1001,
      "1000",
    ]) {
      const h = harness({
        baseline: Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => notReady),
        canary: BROKEN_CANARY,
      });

      await assert.rejects(
        () => readBaseline({ ...h, delayMs }),
        DemoBaselineError,
      );

      for (const ms of h.waits) {
        assert.equal(ms, BASELINE_RETRY_DELAY_MS, `delayMs=${delayMs} escaped`);
      }
    }
  });

  it("never waits past the production deadline when the seam asks for more", async () => {
    const h = harness({
      baseline: Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => notReady),
      canary: BROKEN_CANARY,
    });

    await assert.rejects(
      () => readBaseline({ ...h, deadlineMs: 10 * BASELINE_DEADLINE_MS }),
      DemoBaselineError,
    );

    // The oversized deadline fell back to the production one, so the clock
    // never advanced past it.
    assert.ok(h.waits.length * BASELINE_RETRY_DELAY_MS <= BASELINE_DEADLINE_MS);
  });

  // A seam may still make a test fast by asking for less.
  it("honours a smaller budget from the seams", async () => {
    const h = harness({
      baseline: [notReady, notReady],
      canary: BROKEN_CANARY,
    });

    await assert.rejects(
      () => readBaseline({ ...h, maxAttempts: 2, delayMs: 7 }),
      DemoBaselineError,
    );

    assert.equal(h.baselineCalls.length, 2);
    assert.deepEqual(h.waits, [7]);
  });

  // A real read of a wrong database. Retrying it would turn a visible, correct
  // answer into more of the same, and hiding it would defeat the whole baseline
  // guarantee.
  it("does not retry or hide a count mismatch", async () => {
    const seeded = statusRow({ sharing_grants: 1, daily_check_ins: 4 });
    const h = harness({ baseline: [seeded] });

    const counts = await readBaseline(h);

    assert.equal(
      h.baselineCalls.length,
      1,
      "a mismatching baseline must not be re-read",
    );
    assert.deepEqual(h.waits, []);
    assert.equal(h.canaryCalls.length, 0);

    // Returned as-is, so the caller's comparison still sees the real state.
    assert.equal(counts.sharing_grants, 1);
    assert.equal(counts.daily_check_ins, 4);
    assert.deepEqual(
      compareBaseline(counts)
        .map((mismatch) => mismatch.key)
        .sort(),
      ["daily_check_ins", "sharing_grants"],
    );
  });

  // A count mismatch must stay visible even while the transport is sick — the
  // canary must never be able to turn a real mismatch into a retry.
  it("returns a count mismatch unaltered even when the canary is broken", async () => {
    const seeded = statusRow({ sharing_grants: 9 });
    const h = harness({ baseline: [seeded], canary: BROKEN_CANARY });

    const counts = await readBaseline(h);

    assert.equal(h.baselineCalls.length, 1);
    assert.equal(h.canaryCalls.length, 0);
    assert.equal(counts.sharing_grants, 9);
    assert.deepEqual(
      compareBaseline(counts).map((m) => m.key),
      ["sharing_grants"],
    );
  });

  // Still not retried: neither has ever been observed clearing on its own, and
  // retrying a broken contract only delays a failure that should be immediate.
  for (const [label, response] of [
    ["malformed JSON", `not json at all ${SENTINEL}`],
    [
      "a non-integer count",
      JSON.stringify({ rows: [{ ...EXPECTED_BASELINE, profiles: SENTINEL }] }),
    ],
  ]) {
    it(`queries exactly once for ${label}`, async () => {
      const h = harness({ baseline: [response] });

      await assert.rejects(() => readBaseline(h), DemoBaselineError);
      assert.equal(h.baselineCalls.length, 1);
      assert.deepEqual(h.waits, []);
      assert.equal(h.canaryCalls.length, 0);
    });
  }

  // A transport failure is not this function's condition either.
  it("queries exactly once for a subprocess failure", async () => {
    let calls = 0;
    const h = harness({ baseline: [] });
    const query = async () => {
      calls += 1;
      throw new Error(`local scalar query failed ${SENTINEL}`);
    };

    await assert.rejects(() => readBaseline({ ...h, query }));
    assert.equal(calls, 1);
    assert.deepEqual(h.waits, []);
  });

  it("leaks no response content into the error it throws", async () => {
    const exhaust = (response) =>
      Array.from({ length: BASELINE_MAX_ATTEMPTS }, () => response);

    const responses = [
      // Both retryable branches, driven to exhaustion so the error that
      // escapes is the one a real failure would produce.
      exhaust(notReady),
      exhaust(JSON.stringify({ boundary: SENTINEL, rows: SENTINEL })),
      exhaust(JSON.stringify({ warning: SENTINEL })),
      exhaust(JSON.stringify({ rows: { leaked: SENTINEL } })),
      exhaust(JSON.stringify({ rows: [] })),
      // The non-retryable branches, which fail on the first attempt.
      [`not json at all ${SENTINEL}`],
      [JSON.stringify({ rows: [{ profiles: SENTINEL }] })],
      [JSON.stringify({ boundary: SENTINEL, rows: [{ leak: SENTINEL }] })],
    ];

    for (const scripted of responses) {
      // The canary carries the sentinel too, so a leak through the diagnosis
      // path would be caught here as well.
      const h = harness({ baseline: scripted, canary: BROKEN_CANARY });

      try {
        await readBaseline(h);
        assert.fail("expected a rejection");
      } catch (error) {
        assert.ok(error instanceof DemoBaselineError);

        const surfaces = [
          error.message,
          String(error),
          error.stack ?? "",
          // `cause` is never set by this module, but an edit that started
          // chaining the underlying failure would carry the response with it.
          String(error.cause ?? ""),
          JSON.stringify(error.cause ?? null),
          // Own properties, enumerable or not, including anything a future
          // edit attaches for debugging.
          JSON.stringify(
            Object.fromEntries(
              Object.getOwnPropertyNames(error).map((key) => [
                key,
                String(error[key]),
              ]),
            ),
          ),
        ];

        for (const surface of surfaces) {
          assert.ok(
            !surface.includes(SENTINEL),
            `response content escaped into: ${surface.slice(0, 120)}`,
          );
        }

        // The fixed sanitized set, and nothing else.
        assert.ok(
          [
            "The baseline query did not return exactly one row.",
            "The baseline query returned no row set.",
            "Could not read the baseline query result.",
            "The baseline query returned a non-integer count.",
          ].includes(error.message),
          `unexpected message: ${error.message}`,
        );

        // `retryable` is a boolean decided at the throw site, never a value
        // copied out of the response.
        assert.equal(typeof error.retryable, "boolean");

        // Nothing is chained, so nothing can be carried along by a chain.
        assert.equal(error.cause, undefined);
      }
    }
  });
});

describe("cliQueryPathLooksHealthy", () => {
  // The evidence the retry's termination condition rests on. It answers one
  // question with a boolean and never throws.
  it("reads nothing from the database", () => {
    assert.equal(CANARY_SQL, "select 1::int as ok");

    for (const forbidden of [
      "public.",
      "auth.",
      "profiles",
      "teams",
      "team_memberships",
      "sharing_grants",
      "daily_check_ins",
      "count(",
      "from",
    ]) {
      assert.ok(
        !CANARY_SQL.includes(forbidden),
        `the canary must not reference ${forbidden}`,
      );
    }
  });

  for (const [label, response] of [
    ["the boundary envelope", JSON.stringify({ rows: [{ ok: 1 }] })],
    ["a bare array", JSON.stringify([{ ok: 1 }])],
  ]) {
    it(`reports healthy for ${label}`, async () => {
      assert.equal(await cliQueryPathLooksHealthy(async () => response), true);
    });
  }

  for (const [label, respond] of [
    ["a missing row set", async () => JSON.stringify({ warning: "w" })],
    ["a non-array row set", async () => JSON.stringify({ rows: null })],
    ["an empty row set", async () => JSON.stringify({ rows: [] })],
    ["two rows", async () => JSON.stringify({ rows: [{ ok: 1 }, { ok: 1 }] })],
    ["malformed JSON", async () => "not json"],
    [
      "a transport failure",
      async () => {
        throw new Error("query failed");
      },
    ],
  ]) {
    it(`reports unhealthy for ${label}`, async () => {
      assert.equal(await cliQueryPathLooksHealthy(respond), false);
    });
  }

  it("asks only the canary question", async () => {
    const asked = [];

    await cliQueryPathLooksHealthy(async (sql) => {
      asked.push(sql);

      return JSON.stringify({ rows: [{ ok: 1 }] });
    });

    assert.deepEqual(asked, [CANARY_SQL]);
  });
});

describe("formatBaseline", () => {
  it("prints key names and integers only", () => {
    for (const line of formatBaseline(EXPECTED_BASELINE).split("\n")) {
      assert.match(line, /^ {2}[a-z_]+ +\d+$/);
    }
  });
});
