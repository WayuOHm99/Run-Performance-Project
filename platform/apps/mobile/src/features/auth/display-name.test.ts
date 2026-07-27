import { describe, expect, it } from "vitest";

import {
  DISPLAY_NAME_MAX_LENGTH,
  displayNameMessage,
  hasCompletedProfile,
  normalizeDisplayName,
  validateDisplayName,
} from "./display-name";

describe("normalizeDisplayName", () => {
  it("trims surrounding whitespace", () => {
    expect(normalizeDisplayName("  athlete-a  ")).toBe("athlete-a");
  });

  it("collapses interior whitespace runs", () => {
    expect(normalizeDisplayName("athlete   a")).toBe("athlete a");
  });

  it("collapses tabs and newlines", () => {
    expect(normalizeDisplayName("athlete\t\na")).toBe("athlete a");
  });

  it("returns an empty string for whitespace only", () => {
    expect(normalizeDisplayName("   ")).toBe("");
  });
});

describe("validateDisplayName", () => {
  it("accepts an ordinary name", () => {
    expect(validateDisplayName("athlete-a")).toEqual({
      ok: true,
      value: "athlete-a",
    });
  });

  it("accepts a Thai name", () => {
    expect(validateDisplayName("นักกีฬา")).toEqual({
      ok: true,
      value: "นักกีฬา",
    });
  });

  it("returns the normalized value, not the raw input", () => {
    expect(validateDisplayName("  athlete   a  ")).toEqual({
      ok: true,
      value: "athlete a",
    });
  });

  it("rejects an empty string", () => {
    expect(validateDisplayName("")).toEqual({ ok: false, reason: "empty" });
  });

  it("rejects whitespace only, matching the database constraint", () => {
    expect(validateDisplayName("   ")).toEqual({ ok: false, reason: "empty" });
  });

  it("accepts a name at the maximum length", () => {
    const name = "x".repeat(DISPLAY_NAME_MAX_LENGTH);

    expect(validateDisplayName(name)).toEqual({ ok: true, value: name });
  });

  it("rejects a name one character over the maximum", () => {
    expect(
      validateDisplayName("x".repeat(DISPLAY_NAME_MAX_LENGTH + 1)),
    ).toEqual({ ok: false, reason: "too-long" });
  });
});

describe("hasCompletedProfile", () => {
  it("is false for a profile created by the signup trigger", () => {
    expect(hasCompletedProfile(null)).toBe(false);
  });

  it("is false for undefined", () => {
    expect(hasCompletedProfile(undefined)).toBe(false);
  });

  it("is false for a blank stored name", () => {
    expect(hasCompletedProfile("   ")).toBe(false);
  });

  it("is true once a real name is stored", () => {
    expect(hasCompletedProfile("athlete-a")).toBe(true);
  });

  it("is false for a non-string value", () => {
    expect(hasCompletedProfile(42 as unknown as string)).toBe(false);
  });
});

describe("displayNameMessage", () => {
  it("returns a message for every rejection reason", () => {
    expect(displayNameMessage("empty")).not.toBe("");
    expect(displayNameMessage("too-long")).not.toBe("");
  });
});
