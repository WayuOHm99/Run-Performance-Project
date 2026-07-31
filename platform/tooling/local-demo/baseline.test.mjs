import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { EXPECTED_BASELINE } from "./accounts.mjs";
import {
  BASELINE_SQL,
  compareBaseline,
  DemoBaselineError,
  formatBaseline,
  parseBaselineRow,
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

describe("formatBaseline", () => {
  it("prints key names and integers only", () => {
    for (const line of formatBaseline(EXPECTED_BASELINE).split("\n")) {
      assert.match(line, /^ {2}[a-z_]+ +\d+$/);
    }
  });
});
