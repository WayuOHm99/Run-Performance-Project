import { describe, expect, it } from "vitest";

import {
  OVERALL_FEELING_VALUES,
  PAIN_STATUSES,
  RPE_VALUES,
  parseCheckInInput,
  parseCheckInRow,
  toWriteColumns,
  type CheckInParse,
  type DailyCheckIn,
} from "./domain";

/**
 * Health literals below are synthetic and belong to nobody.
 *
 * Every assertion is reduced to a boolean, a count, or a list of **case names**
 * before it reaches `expect`, so a failure prints "which case" and never "which
 * values". No whole row, payload, or parse result is ever compared directly.
 */

const VALID_ROW = { rpe: 7, overall_feeling: 4, pain_status: "none" };

const VALID_DOMAIN: DailyCheckIn = {
  rpe: 7,
  overallFeeling: 4,
  painStatus: "none",
};

/** Collapses a parse to a boolean so no health value can be printed. */
function parsedMatches(parse: CheckInParse, expected: DailyCheckIn): boolean {
  return (
    parse.ok &&
    parse.value.rpe === expected.rpe &&
    parse.value.overallFeeling === expected.overallFeeling &&
    parse.value.painStatus === expected.painStatus
  );
}

/** Case name paired with the row it describes. Only the name is ever asserted. */
type Case = readonly [name: string, row: unknown];

const REJECTED_ROWS: readonly Case[] = [
  ["null row", null],
  ["undefined row", undefined],
  ["empty object", {}],
  ["a bare number instead of a row", 3],
  ["a string instead of a row", "rpe"],
  ["an array instead of a row", []],
  ["rpe missing", { overall_feeling: 4, pain_status: "none" }],
  ["overall_feeling missing", { rpe: 7, pain_status: "none" }],
  ["pain_status missing", { rpe: 7, overall_feeling: 4 }],
  ["rpe null", { rpe: null, overall_feeling: 4, pain_status: "none" }],
  [
    "overall_feeling null",
    { rpe: 7, overall_feeling: null, pain_status: "none" },
  ],
  ["pain_status null", { rpe: 7, overall_feeling: 4, pain_status: null }],
  [
    "rpe below the minimum",
    { rpe: -1, overall_feeling: 4, pain_status: "none" },
  ],
  [
    "rpe above the maximum",
    { rpe: 11, overall_feeling: 4, pain_status: "none" },
  ],
  ["rpe fractional", { rpe: 7.5, overall_feeling: 4, pain_status: "none" }],
  ["rpe NaN", { rpe: Number.NaN, overall_feeling: 4, pain_status: "none" }],
  [
    "rpe infinite",
    { rpe: Number.POSITIVE_INFINITY, overall_feeling: 4, pain_status: "none" },
  ],
  [
    "rpe as a numeric string",
    { rpe: "7", overall_feeling: 4, pain_status: "none" },
  ],
  ["rpe boolean", { rpe: true, overall_feeling: 4, pain_status: "none" }],
  [
    "overall_feeling below the minimum",
    { rpe: 7, overall_feeling: 0, pain_status: "none" },
  ],
  [
    "overall_feeling above the maximum",
    { rpe: 7, overall_feeling: 6, pain_status: "none" },
  ],
  [
    "overall_feeling fractional",
    { rpe: 7, overall_feeling: 3.5, pain_status: "none" },
  ],
  [
    "overall_feeling as a numeric string",
    { rpe: 7, overall_feeling: "4", pain_status: "none" },
  ],
  [
    "pain_status an unapproved word",
    { rpe: 7, overall_feeling: 4, pain_status: "mild" },
  ],
  ["pain_status empty", { rpe: 7, overall_feeling: 4, pain_status: "" }],
  [
    "pain_status wrong case",
    { rpe: 7, overall_feeling: 4, pain_status: "None" },
  ],
  ["pain_status padded", { rpe: 7, overall_feeling: 4, pain_status: " none" }],
  ["pain_status numeric", { rpe: 7, overall_feeling: 4, pain_status: 0 }],
  [
    "domain naming used on the row parser",
    { rpe: 7, overallFeeling: 4, painStatus: "none" },
  ],
];

describe("parseCheckInRow", () => {
  it("accepts a complete valid row", () => {
    expect(parsedMatches(parseCheckInRow(VALID_ROW), VALID_DOMAIN)).toBe(true);
  });

  it("accepts every value at every boundary", () => {
    const accepted = RPE_VALUES.flatMap((rpe) =>
      OVERALL_FEELING_VALUES.flatMap((overall_feeling) =>
        PAIN_STATUSES.map(
          (pain_status) =>
            parseCheckInRow({ rpe, overall_feeling, pain_status }).ok,
        ),
      ),
    ).filter(Boolean).length;

    // Counts only: 11 x 5 x 2.
    expect(accepted).toBe(
      RPE_VALUES.length * OVERALL_FEELING_VALUES.length * PAIN_STATUSES.length,
    );
  });

  it("rejects every malformed, missing, out-of-range, or unknown row", () => {
    const wronglyAccepted = REJECTED_ROWS.filter(
      ([, row]) => parseCheckInRow(row).ok,
    ).map(([name]) => name);

    // Failure output is a list of case names, never a health payload.
    expect(wronglyAccepted).toEqual([]);
  });

  it("covers a rejection case for each of the required behaviours", () => {
    expect(REJECTED_ROWS.length).toBeGreaterThanOrEqual(25);
  });

  it("rejects a partially valid row outright rather than salvaging it", () => {
    // Two good fields and one bad one must yield no value at all, so nothing
    // partially valid can be displayed or cached.
    const parse = parseCheckInRow({
      rpe: 7,
      overall_feeling: 4,
      pain_status: "severe",
    });

    expect(parse.ok).toBe(false);
  });

  it("does not coerce a value it could have rounded or trimmed", () => {
    const coercible: readonly Case[] = [
      [
        "fractional rpe that rounds into range",
        { rpe: 9.6, overall_feeling: 4, pain_status: "none" },
      ],
      [
        "numeric string feeling",
        { rpe: 7, overall_feeling: "4", pain_status: "none" },
      ],
      [
        "trimmable pain status",
        { rpe: 7, overall_feeling: 4, pain_status: "none " },
      ],
    ];

    const coerced = coercible
      .filter(([, row]) => parseCheckInRow(row).ok)
      .map(([name]) => name);

    expect(coerced).toEqual([]);
  });
});

describe("parseCheckInInput", () => {
  it("accepts a complete valid input in domain naming", () => {
    expect(parsedMatches(parseCheckInInput(VALID_DOMAIN), VALID_DOMAIN)).toBe(
      true,
    );
  });

  it("rejects an input with any answer still unchosen", () => {
    const incomplete: readonly Case[] = [
      ["nothing chosen", { rpe: null, overallFeeling: null, painStatus: null }],
      ["rpe unchosen", { rpe: null, overallFeeling: 4, painStatus: "none" }],
      [
        "feeling unchosen",
        { rpe: 7, overallFeeling: null, painStatus: "none" },
      ],
      ["pain unchosen", { rpe: 7, overallFeeling: 4, painStatus: null }],
    ];

    const wronglyAccepted = incomplete
      .filter(([, input]) => parseCheckInInput(input).ok)
      .map(([name]) => name);

    expect(wronglyAccepted).toEqual([]);
  });

  it("rejects column naming, so a row cannot be mistaken for an input", () => {
    expect(parseCheckInInput(VALID_ROW).ok).toBe(false);
  });
});

describe("toWriteColumns", () => {
  it("produces exactly the three mutable health columns", () => {
    // Field names only. The values are asserted separately as a boolean.
    expect(Object.keys(toWriteColumns(VALID_DOMAIN)).sort()).toEqual([
      "overall_feeling",
      "pain_status",
      "rpe",
    ]);
  });

  it("carries the domain values across unchanged", () => {
    const columns = toWriteColumns(VALID_DOMAIN);

    expect(
      columns.rpe === VALID_DOMAIN.rpe &&
        columns.overall_feeling === VALID_DOMAIN.overallFeeling &&
        columns.pain_status === VALID_DOMAIN.painStatus,
    ).toBe(true);
  });
});

describe("the selectable value sets", () => {
  it("offers eleven RPE values from 0 through 10", () => {
    expect(RPE_VALUES.length).toBe(11);
    expect(RPE_VALUES[0]).toBe(0);
    expect(RPE_VALUES[RPE_VALUES.length - 1]).toBe(10);
  });

  it("offers five overall-feeling values from 1 through 5, higher is better", () => {
    expect(OVERALL_FEELING_VALUES.length).toBe(5);
    expect(OVERALL_FEELING_VALUES[0]).toBe(1);
    expect(OVERALL_FEELING_VALUES[OVERALL_FEELING_VALUES.length - 1]).toBe(5);
  });

  it("offers exactly two pain statuses", () => {
    expect([...PAIN_STATUSES]).toEqual(["none", "present"]);
  });
});
