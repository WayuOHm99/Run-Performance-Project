import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { EXPECTED_BASELINE } from "./accounts.mjs";
import {
  BASELINE_ATTEMPTS,
  BASELINE_RETRY_DELAY_MS,
  BASELINE_SQL,
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

  function scriptedQuery(responses) {
    const calls = [];

    return {
      calls,
      query: async (sql) => {
        calls.push(sql);

        const response = responses[calls.length - 1];

        if (response === undefined) {
          throw new Error("the query was called more times than scripted");
        }

        return response;
      },
    };
  }

  function recordingWait() {
    const waits = [];

    return { waits, wait: async (ms) => void waits.push(ms) };
  }

  // The observed cold-start failure: a well-formed envelope carrying the wrong
  // number of rows, immediately followed by a good read.
  const notReady = JSON.stringify({
    boundary: SENTINEL,
    warning: SENTINEL,
    rows: [],
  });

  it("recovers when a structural failure is followed by one valid row", async () => {
    const { calls, query } = scriptedQuery([notReady, statusRow()]);
    const { waits, wait } = recordingWait();

    const counts = await readBaseline({ query, wait, delayMs: 7 });

    assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
    assert.equal(calls.length, 2);
    assert.deepEqual(waits, [7]);
  });

  it("passes the count-only SQL on every attempt", async () => {
    const { calls, query } = scriptedQuery([notReady, statusRow()]);
    const { wait } = recordingWait();

    await readBaseline({ query, wait });

    assert.deepEqual(calls, [BASELINE_SQL, BASELINE_SQL]);
  });

  // Round 8's production bound, pinned so it cannot drift silently.
  it("holds the round 8 production bound", () => {
    assert.equal(BASELINE_ATTEMPTS, 10);
    assert.equal(BASELINE_RETRY_DELAY_MS, 1000);

    // Nine waits, not ten: no wait follows the final attempt.
    const maxWaitBudgetMs = (BASELINE_ATTEMPTS - 1) * BASELINE_RETRY_DELAY_MS;

    assert.equal(maxWaitBudgetMs, 9000);
  });

  // Both structural shapes recover, and both are driven all the way to the
  // last attempt so the full budget is exercised rather than assumed.
  for (const [label, transient] of [
    ["missing rows", JSON.stringify({ boundary: SENTINEL, warning: SENTINEL })],
    ["non-array rows", JSON.stringify({ rows: null, warning: SENTINEL })],
    ["object rows", JSON.stringify({ rows: { leaked: SENTINEL } })],
    ["wrong cardinality", notReady],
  ]) {
    it(`recovers when ${label} repeats and is then followed by one valid row`, async () => {
      const { calls, query } = scriptedQuery([
        transient,
        transient,
        transient,
        statusRow(),
      ]);
      const { waits, wait } = recordingWait();

      const counts = await readBaseline({ query, wait });

      assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
      assert.equal(calls.length, 4);
      assert.deepEqual(waits, [
        BASELINE_RETRY_DELAY_MS,
        BASELINE_RETRY_DELAY_MS,
        BASELINE_RETRY_DELAY_MS,
      ]);
    });

    it(`recovers on the very last attempt when ${label} persists`, async () => {
      const { calls, query } = scriptedQuery([
        ...Array.from({ length: BASELINE_ATTEMPTS - 1 }, () => transient),
        statusRow(),
      ]);
      const { waits, wait } = recordingWait();

      const counts = await readBaseline({ query, wait });

      assert.deepEqual({ ...counts }, EXPECTED_BASELINE);
      assert.equal(calls.length, 10);
      assert.equal(waits.length, 9);
    });
  }

  // Exhaustion, per structural shape, with the message that identifies it.
  for (const [label, response, message] of [
    [
      "missing rows",
      JSON.stringify({ boundary: SENTINEL }),
      "The baseline query returned no row set.",
    ],
    [
      "non-array rows",
      JSON.stringify({ rows: SENTINEL }),
      "The baseline query returned no row set.",
    ],
    [
      "wrong cardinality",
      notReady,
      "The baseline query did not return exactly one row.",
    ],
  ]) {
    it(`exhausts exactly 10 attempts on persistent ${label}, then fails closed`, async () => {
      const { calls, query } = scriptedQuery(
        Array.from({ length: BASELINE_ATTEMPTS }, () => response),
      );
      const { waits, wait } = recordingWait();

      await assert.rejects(
        () => readBaseline({ query, wait }),
        (error) => {
          assert.ok(error instanceof DemoBaselineError);
          // The distinct fixed sanitized message for this branch.
          assert.equal(error.message, message);

          return true;
        },
      );

      // Exact counts, and exactly one bounded wait between each pair of
      // attempts — never one after the last.
      assert.equal(calls.length, 10);
      assert.equal(waits.length, 9);
      assert.deepEqual(
        waits,
        Array.from({ length: 9 }, () => 1000),
      );
    });
  }

  // The seams exist for these tests; they must not be a way to exceed or remove
  // the production bound. A zero or NaN budget would otherwise skip the loop and
  // leave no error to throw at all.
  it("falls back to the production budget when the attempts seam is out of bounds", async () => {
    for (const attempts of [
      0,
      -1,
      2.5,
      Number.NaN,
      Number.POSITIVE_INFINITY,
      // Above the production bound: must not be honoured.
      11,
      1000,
    ]) {
      const { calls, query } = scriptedQuery(
        Array.from({ length: BASELINE_ATTEMPTS }, () => notReady),
      );

      await assert.rejects(
        () => readBaseline({ query, wait: async () => {}, attempts }),
        DemoBaselineError,
      );
      assert.equal(
        calls.length,
        BASELINE_ATTEMPTS,
        `attempts=${attempts} escaped the bound`,
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
      const { query } = scriptedQuery(
        Array.from({ length: BASELINE_ATTEMPTS }, () => notReady),
      );
      const { waits, wait } = recordingWait();

      await assert.rejects(
        () => readBaseline({ query, wait, delayMs }),
        DemoBaselineError,
      );

      assert.equal(waits.length, 9);

      for (const ms of waits) {
        assert.equal(ms, BASELINE_RETRY_DELAY_MS, `delayMs=${delayMs} escaped`);
      }
    }
  });

  // A seam may still make a test fast by asking for less.
  it("honours a smaller budget from the seams", async () => {
    const { calls, query } = scriptedQuery([notReady, notReady]);
    const { waits, wait } = recordingWait();

    await assert.rejects(
      () => readBaseline({ query, wait, attempts: 2, delayMs: 7 }),
      DemoBaselineError,
    );

    assert.equal(calls.length, 2);
    assert.deepEqual(waits, [7]);
  });

  // A real read of a wrong database. Retrying it would turn a visible, correct
  // answer into three more of the same, and hiding it would defeat the whole
  // baseline guarantee.
  it("does not retry or hide a count mismatch", async () => {
    const seeded = statusRow({ sharing_grants: 1, daily_check_ins: 4 });
    const { calls, query } = scriptedQuery([seeded]);
    const { waits, wait } = recordingWait();

    const counts = await readBaseline({ query, wait });

    assert.equal(calls.length, 1, "a mismatching baseline must not be re-read");
    assert.deepEqual(waits, []);

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
      const { calls, query } = scriptedQuery([response]);
      const { waits, wait } = recordingWait();

      await assert.rejects(
        () => readBaseline({ query, wait }),
        DemoBaselineError,
      );
      assert.equal(calls.length, 1);
      assert.deepEqual(waits, []);
    });
  }

  // A transport failure is not this function's condition either.
  it("queries exactly once for a subprocess failure", async () => {
    let calls = 0;
    const { waits, wait } = recordingWait();
    const query = async () => {
      calls += 1;
      throw new Error(`local scalar query failed ${SENTINEL}`);
    };

    await assert.rejects(() => readBaseline({ query, wait }));
    assert.equal(calls, 1);
    assert.deepEqual(waits, []);
  });

  it("leaks no response content into the error it throws", async () => {
    const exhaust = (response) =>
      Array.from({ length: BASELINE_ATTEMPTS }, () => response);

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
      const { query } = scriptedQuery(scripted);

      try {
        await readBaseline({ query, wait: async () => {}, delayMs: 0 });
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

describe("formatBaseline", () => {
  it("prints key names and integers only", () => {
    for (const line of formatBaseline(EXPECTED_BASELINE).split("\n")) {
      assert.match(line, /^ {2}[a-z_]+ +\d+$/);
    }
  });
});
