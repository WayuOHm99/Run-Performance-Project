import { describe, expect, it } from "vitest";

import {
  PASSWORD_MIN_LENGTH,
  credentialMessage,
  normalizeEmail,
  validateCredentials,
} from "./credentials";

const VALID_PASSWORD = "synthetic-password";

describe("normalizeEmail", () => {
  it("trims and lower-cases", () => {
    expect(normalizeEmail("  Athlete-A@Example.TEST ")).toBe(
      "athlete-a@example.test",
    );
  });
});

describe("validateCredentials", () => {
  it("accepts a valid pair and returns the normalized email", () => {
    const result = validateCredentials({
      email: "  Athlete-A@Example.TEST ",
      password: VALID_PASSWORD,
    });

    expect(result).toEqual({
      ok: true,
      value: { email: "athlete-a@example.test", password: VALID_PASSWORD },
    });
  });

  it("never trims or alters the password", () => {
    const password = "  spaced password  ";
    const result = validateCredentials({
      email: "athlete-a@example.test",
      password,
    });

    expect(result.ok).toBe(true);
    // Whitespace is legitimate password content. Trimming it here would lock a
    // user out of an account they typed correctly.
    expect(result.ok ? result.value.password : null).toBe(password);
  });

  it("does not lower-case the password", () => {
    const password = "MiXeDCaseValue";
    const result = validateCredentials({
      email: "athlete-a@example.test",
      password,
    });

    expect(result.ok ? result.value.password : null).toBe(password);
  });

  it("rejects an empty email", () => {
    expect(
      validateCredentials({ email: "   ", password: VALID_PASSWORD }),
    ).toEqual({ ok: false, field: "email", reason: "email-required" });
  });

  it("rejects a malformed email", () => {
    expect(
      validateCredentials({ email: "not-an-email", password: VALID_PASSWORD }),
    ).toEqual({ ok: false, field: "email", reason: "email-invalid" });
  });

  it("rejects an email with a space inside", () => {
    expect(
      validateCredentials({
        email: "a b@example.test",
        password: VALID_PASSWORD,
      }),
    ).toEqual({ ok: false, field: "email", reason: "email-invalid" });
  });

  it("rejects an empty password", () => {
    expect(
      validateCredentials({ email: "athlete-a@example.test", password: "" }),
    ).toEqual({ ok: false, field: "password", reason: "password-required" });
  });

  it("rejects a password below the minimum length", () => {
    expect(
      validateCredentials({
        email: "athlete-a@example.test",
        password: "x".repeat(PASSWORD_MIN_LENGTH - 1),
      }),
    ).toEqual({ ok: false, field: "password", reason: "password-too-short" });
  });

  it("accepts a password at exactly the minimum length", () => {
    const result = validateCredentials({
      email: "athlete-a@example.test",
      password: "x".repeat(PASSWORD_MIN_LENGTH),
    });

    expect(result.ok).toBe(true);
  });

  it("reports the email problem first when both fields are wrong", () => {
    const result = validateCredentials({ email: "", password: "" });

    expect(result.ok ? null : result.field).toBe("email");
  });
});

describe("credentialMessage", () => {
  it("returns a message for every rejection reason", () => {
    expect(credentialMessage("email-required")).not.toBe("");
    expect(credentialMessage("email-invalid")).not.toBe("");
    expect(credentialMessage("password-required")).not.toBe("");
    expect(credentialMessage("password-too-short")).not.toBe("");
  });

  it("never echoes a submitted value", () => {
    const messages = [
      credentialMessage("email-required"),
      credentialMessage("email-invalid"),
      credentialMessage("password-required"),
      credentialMessage("password-too-short"),
    ];

    for (const message of messages) {
      expect(message).not.toContain("@");
      expect(message.toLowerCase()).not.toContain("synthetic");
    }
  });
});
