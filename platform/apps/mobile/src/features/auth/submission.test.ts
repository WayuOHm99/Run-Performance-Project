import { describe, expect, it } from "vitest";

import { beginSubmission, endSubmission, isSubmitting } from "./submission";

describe("beginSubmission", () => {
  it("accepts the first attempt", () => {
    expect(beginSubmission("idle")).toEqual({
      accepted: true,
      next: "submitting",
    });
  });

  it("drops a second attempt while the first is in flight", () => {
    expect(beginSubmission("submitting")).toEqual({
      accepted: false,
      next: "submitting",
    });
  });

  it("drops every attempt in a rapid double tap", () => {
    let state = endSubmission();
    const accepted: boolean[] = [];

    for (let tap = 0; tap < 5; tap += 1) {
      const attempt = beginSubmission(state);

      accepted.push(attempt.accepted);
      state = attempt.next;
    }

    expect(accepted).toEqual([true, false, false, false, false]);
  });

  it("accepts again once the previous attempt finished", () => {
    const first = beginSubmission("idle");
    const settled = endSubmission();

    expect(first.accepted).toBe(true);
    expect(beginSubmission(settled).accepted).toBe(true);
  });
});

describe("isSubmitting", () => {
  it("reports the in-flight state", () => {
    expect(isSubmitting("idle")).toBe(false);
    expect(isSubmitting("submitting")).toBe(true);
  });
});
