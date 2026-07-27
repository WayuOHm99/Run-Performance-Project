import { describe, expect, it } from "vitest";

import {
  INITIAL_SEQUENCE_TOKEN,
  nextSequenceToken,
  shouldApplyResult,
} from "./sequence";

describe("nextSequenceToken", () => {
  it("increases monotonically", () => {
    let token = INITIAL_SEQUENCE_TOKEN;
    const issued: number[] = [];

    for (let index = 0; index < 5; index += 1) {
      token = nextSequenceToken(token);
      issued.push(token);
    }

    expect(issued).toEqual([1, 2, 3, 4, 5]);
  });

  it("never issues the initial token", () => {
    expect(nextSequenceToken(INITIAL_SEQUENCE_TOKEN)).toBeGreaterThan(
      INITIAL_SEQUENCE_TOKEN,
    );
  });
});

describe("shouldApplyResult", () => {
  it("applies the first result", () => {
    expect(shouldApplyResult(1, INITIAL_SEQUENCE_TOKEN)).toBe(true);
  });

  it("applies a newer result", () => {
    expect(shouldApplyResult(3, 2)).toBe(true);
  });

  it("drops a result that a newer signal already superseded", () => {
    // The ordering bug this exists to prevent: a restore started at launch
    // resolving after a sign-out that was observed later.
    expect(shouldApplyResult(1, 2)).toBe(false);
  });

  it("drops a repeated result for the token already applied", () => {
    expect(shouldApplyResult(2, 2)).toBe(false);
  });

  it("keeps a signed-out result from being overwritten by a stale restore", () => {
    let applied = INITIAL_SEQUENCE_TOKEN;
    const outcomes: (string | null)[] = [];

    // Restore claims token 1, sign-out is observed as token 2.
    const restoreToken = 1;
    const signOutToken = 2;

    // Sign-out resolves first.
    if (shouldApplyResult(signOutToken, applied)) {
      applied = signOutToken;
      outcomes.push(null);
    }

    // The slow restore resolves afterwards, carrying the older token.
    if (shouldApplyResult(restoreToken, applied)) {
      applied = restoreToken;
      outcomes.push("restored-user");
    }

    expect(outcomes).toEqual([null]);
    expect(applied).toBe(signOutToken);
  });

  it("applies results in order when they resolve out of order", () => {
    let applied = INITIAL_SEQUENCE_TOKEN;
    const settled: number[] = [];

    // Three signals resolve in the order 2, 1, 3.
    for (const token of [2, 1, 3]) {
      if (shouldApplyResult(token, applied)) {
        applied = token;
        settled.push(token);
      }
    }

    expect(settled).toEqual([2, 3]);
    expect(applied).toBe(3);
  });
});
