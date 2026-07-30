import { describe, expect, it } from "vitest";

import type { LocalDateStamp } from "./local-date";
import {
  EMPTY_DRAFT,
  draftFromCheckIn,
  isDraftComplete,
  planSubmission,
  type CheckInDraft,
} from "./submission";

/**
 * Health literals are synthetic. Every assertion is a boolean, a count, or a
 * plan `kind`/date, so a failure never prints an answer.
 */

const CAPTURED: LocalDateStamp = { date: "2026-07-30", offsetMinutes: -420 };

const COMPLETE_DRAFT: CheckInDraft = {
  rpe: 6,
  overallFeeling: 3,
  painStatus: "none",
};

describe("EMPTY_DRAFT", () => {
  it("preselects no health answer", () => {
    expect(
      EMPTY_DRAFT.rpe === null &&
        EMPTY_DRAFT.overallFeeling === null &&
        EMPTY_DRAFT.painStatus === null,
    ).toBe(true);
  });

  it("is not complete", () => {
    expect(isDraftComplete(EMPTY_DRAFT)).toBe(false);
  });
});

describe("draftFromCheckIn", () => {
  it("stays empty when there is no row for today", () => {
    expect(isDraftComplete(draftFromCheckIn(null))).toBe(false);
  });

  it("prefills every answer from an existing row", () => {
    const draft = draftFromCheckIn({
      rpe: 8,
      overallFeeling: 2,
      painStatus: "present",
    });

    expect(
      draft.rpe === 8 &&
        draft.overallFeeling === 2 &&
        draft.painStatus === "present",
    ).toBe(true);
    expect(isDraftComplete(draft)).toBe(true);
  });
});

describe("isDraftComplete", () => {
  it("requires all three answers", () => {
    const partial: readonly [string, CheckInDraft][] = [
      ["only rpe", { ...EMPTY_DRAFT, rpe: 6 }],
      ["only feeling", { ...EMPTY_DRAFT, overallFeeling: 3 }],
      ["only pain", { ...EMPTY_DRAFT, painStatus: "none" }],
      ["missing pain", { rpe: 6, overallFeeling: 3, painStatus: null }],
      ["missing feeling", { rpe: 6, overallFeeling: null, painStatus: "none" }],
      ["missing rpe", { rpe: null, overallFeeling: 3, painStatus: "none" }],
    ];

    const wronglyComplete = partial
      .filter(([, draft]) => isDraftComplete(draft))
      .map(([name]) => name);

    expect(wronglyComplete).toEqual([]);
  });

  it("accepts a fully answered draft", () => {
    expect(isDraftComplete(COMPLETE_DRAFT)).toBe(true);
  });

  it("treats rpe zero as an answer rather than as unanswered", () => {
    // 0 is a real answer meaning rest, so a falsiness check here would be a bug.
    expect(isDraftComplete({ ...COMPLETE_DRAFT, rpe: 0 })).toBe(true);
  });
});

describe("planSubmission", () => {
  it("submits the current local date when nothing moved", () => {
    const plan = planSubmission({
      captured: CAPTURED,
      current: { ...CAPTURED },
      draft: COMPLETE_DRAFT,
    });

    expect(plan.kind).toBe("submit");
    expect(plan.kind === "submit" ? plan.localDate : null).toBe("2026-07-30");
  });

  it("refuses to submit an incomplete draft", () => {
    expect(
      planSubmission({
        captured: CAPTURED,
        current: { ...CAPTURED },
        draft: { ...COMPLETE_DRAFT, painStatus: null },
      }).kind,
    ).toBe("incomplete");
  });

  it("refuses to submit a draft holding an out-of-range value", () => {
    // Reaches the plan only if some other layer failed; it still must not write.
    expect(
      planSubmission({
        captured: CAPTURED,
        current: { ...CAPTURED },
        draft: { ...COMPLETE_DRAFT, rpe: 11 },
      }).kind,
    ).toBe("incomplete");
  });

  it("blocks the write after the local date rolls over", () => {
    const plan = planSubmission({
      captured: CAPTURED,
      current: { ...CAPTURED, date: "2026-07-31" },
      draft: COMPLETE_DRAFT,
    });

    expect(plan.kind).toBe("rollover");
    // Never the captured date: the answers must not land on the stale day.
    expect(plan.kind === "rollover" ? plan.stamp.date : null).toBe(
      "2026-07-31",
    );
  });

  it("blocks the write after the timezone offset changes", () => {
    expect(
      planSubmission({
        captured: CAPTURED,
        current: { ...CAPTURED, offsetMinutes: 0 },
        draft: COMPLETE_DRAFT,
      }).kind,
    ).toBe("rollover");
  });

  it("reports the rollover even when the draft is incomplete", () => {
    // Rollover is checked first on purpose, so a half-filled form is reset
    // against the new day rather than silently kept for the old one.
    expect(
      planSubmission({
        captured: CAPTURED,
        current: { ...CAPTURED, date: "2026-07-31" },
        draft: EMPTY_DRAFT,
      }).kind,
    ).toBe("rollover");
  });

  it("never returns the captured date once it has gone stale", () => {
    const stalePairs: readonly [string, LocalDateStamp][] = [
      ["next day", { date: "2026-07-31", offsetMinutes: -420 }],
      ["previous day", { date: "2026-07-29", offsetMinutes: -420 }],
      ["same day, new offset", { date: "2026-07-30", offsetMinutes: 60 }],
    ];

    const leaked = stalePairs
      .filter(([, current]) => {
        const plan = planSubmission({
          captured: CAPTURED,
          current,
          draft: COMPLETE_DRAFT,
        });

        return plan.kind === "submit";
      })
      .map(([name]) => name);

    expect(leaked).toEqual([]);
  });
});
