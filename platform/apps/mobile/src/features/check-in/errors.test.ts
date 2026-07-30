import { describe, expect, it } from "vitest";

import {
  CheckInDataError,
  UNEXPECTED_CHECK_IN_MESSAGE,
  checkInErrorFrom,
  checkInErrorMessage,
} from "./errors";

/**
 * Only fixed application strings are ever asserted here, so every value printed
 * on a failure is one this repository already contains in plain text.
 */

/** Anything that must never reach the athlete or a log. */
const FORBIDDEN_FRAGMENTS: readonly string[] = [
  "row-level security",
  "permission denied",
  "violates",
  "constraint",
  "daily_check_ins",
  "athlete_profile_id",
  "check_in_date",
  "overall_feeling",
  "pain_status",
  "rpe",
  "42501",
  "23505",
  "22023",
  "PGRST",
  "supabase",
  "postgres",
  "sql",
  "table",
  "row",
  "insert",
  "update",
  "select",
  "http",
  "token",
  "jwt",
  "Failing row",
  "@",
];

const EVERY_MESSAGE: readonly string[] = [
  new CheckInDataError("load", "offline").message,
  new CheckInDataError("load", "denied").message,
  new CheckInDataError("load", "unknown").message,
  new CheckInDataError("save", "offline").message,
  new CheckInDataError("save", "denied").message,
  new CheckInDataError("save", "unknown").message,
  UNEXPECTED_CHECK_IN_MESSAGE,
];

describe("CheckInDataError", () => {
  it("carries a non-empty fixed message for every intent and failure", () => {
    expect(EVERY_MESSAGE.filter((message) => message.length === 0)).toEqual([]);
  });

  it("exposes no database or transport terminology in any message", () => {
    const leaks = FORBIDDEN_FRAGMENTS.filter((fragment) =>
      EVERY_MESSAGE.some((message) =>
        message.toLowerCase().includes(fragment.toLowerCase()),
      ),
    );

    expect(leaks).toEqual([]);
  });

  it("distinguishes a failed load from a failed save", () => {
    expect(new CheckInDataError("load", "unknown").message).not.toBe(
      new CheckInDataError("save", "unknown").message,
    );
  });

  it("keeps nothing from the original error", () => {
    const raw = {
      code: "42501",
      message: 'permission denied for table "daily_check_ins"',
      details: "Failing row contains (6, 3, none)",
      hint: "daily_check_ins_update_own",
    };

    const error = checkInErrorFrom("save", raw);

    // No message, detail, hint, code, or cause is retained anywhere on the error.
    expect(error.message.includes("denied for table")).toBe(false);
    expect((error as { cause?: unknown }).cause).toBeUndefined();
    expect(Object.keys(error).sort()).toEqual(["failure", "intent", "name"]);
  });

  it("classifies the failure category without reading the message", () => {
    expect(checkInErrorFrom("load", { code: "42501" }).failure).toBe("denied");
    expect(checkInErrorFrom("load", { code: "PGRST301" }).failure).toBe(
      "denied",
    );
    expect(
      checkInErrorFrom("save", new TypeError("Network request failed")).failure,
    ).toBe("offline");
    expect(checkInErrorFrom("save", { code: "23505" }).failure).toBe("unknown");
    expect(checkInErrorFrom("save", null).failure).toBe("unknown");
  });

  it("records the intent it was built for", () => {
    expect(checkInErrorFrom("load", null).intent).toBe("load");
    expect(checkInErrorFrom("save", null).intent).toBe("save");
  });
});

describe("checkInErrorMessage", () => {
  it("uses the sanitized message of a check-in error", () => {
    const error = new CheckInDataError("load", "offline");

    expect(checkInErrorMessage(error)).toBe(error.message);
  });

  it("discards the message of an unsanitized thrown value", () => {
    const raw = new Error('permission denied for table "daily_check_ins"');

    // A value that never went through sanitization is replaced wholesale rather
    // than displayed, so an unexpected throw cannot become a leak.
    expect(checkInErrorMessage(raw)).toBe(UNEXPECTED_CHECK_IN_MESSAGE);
    expect(checkInErrorMessage(raw).includes("denied")).toBe(false);
  });

  it("handles a thrown value that is not an error at all", () => {
    const values: readonly unknown[] = [
      null,
      undefined,
      "boom",
      42,
      { code: "42501" },
    ];

    const wrong = values.filter(
      (value) => checkInErrorMessage(value) !== UNEXPECTED_CHECK_IN_MESSAGE,
    ).length;

    expect(wrong).toBe(0);
  });
});
