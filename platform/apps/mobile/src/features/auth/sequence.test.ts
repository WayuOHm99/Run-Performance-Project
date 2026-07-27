import { describe, expect, it } from "vitest";

import {
  INITIAL_SEQUENCE_TOKEN,
  isNewerSignal,
  nextSequenceToken,
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

describe("isNewerSignal", () => {
  it("accepts the first observation", () => {
    expect(isNewerSignal(1, INITIAL_SEQUENCE_TOKEN)).toBe(true);
  });

  it("accepts a newer observation", () => {
    expect(isNewerSignal(3, 2)).toBe(true);
  });

  it("rejects an observation that a newer one already superseded", () => {
    expect(isNewerSignal(1, 2)).toBe(false);
  });

  it("rejects a repeated observation", () => {
    expect(isNewerSignal(2, 2)).toBe(false);
  });
});

// Ordering *observations* is not the same question as applying a validation
// *result*. `isNewerSignal` deliberately answers only the first. The second
// lives in `canApplyValidation`, which additionally requires the result's token
// to still be the latest observed signal, and is tested in auth-state.test.ts.
