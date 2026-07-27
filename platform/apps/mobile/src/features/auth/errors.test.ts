import { describe, expect, it } from "vitest";

import {
  authErrorMessage,
  classifyAuthError,
  classifyDataError,
  dataErrorMessage,
} from "./errors";

describe("classifyAuthError", () => {
  it("classifies a wrong password as invalid credentials", () => {
    expect(classifyAuthError({ code: "invalid_credentials" })).toBe(
      "invalid-credentials",
    );
  });

  it("classifies an unknown account the same as a wrong password", () => {
    // Separating these would let a caller enumerate registered addresses.
    expect(classifyAuthError({ code: "user_not_found" })).toBe(
      classifyAuthError({ code: "invalid_credentials" }),
    );
  });

  it("classifies an already-registered address the same way", () => {
    expect(classifyAuthError({ code: "user_already_exists" })).toBe(
      classifyAuthError({ code: "invalid_credentials" }),
    );
    expect(classifyAuthError({ code: "email_exists" })).toBe(
      classifyAuthError({ code: "invalid_credentials" }),
    );
  });

  it("classifies a weak password", () => {
    expect(classifyAuthError({ code: "weak_password" })).toBe("weak-password");
  });

  it("classifies rate limiting", () => {
    expect(classifyAuthError({ code: "over_request_rate_limit" })).toBe(
      "rate-limited",
    );
    expect(classifyAuthError({ status: 429 })).toBe("rate-limited");
  });

  it("classifies a transport failure as offline", () => {
    const failure = new TypeError("Network request failed");

    expect(classifyAuthError(failure)).toBe("offline");
  });

  it("classifies a retryable auth fetch error as offline", () => {
    expect(classifyAuthError({ name: "AuthRetryableFetchError" })).toBe(
      "offline",
    );
  });

  it("falls back to unknown for anything unrecognised", () => {
    expect(classifyAuthError({ code: "something_new" })).toBe("unknown");
    expect(classifyAuthError(null)).toBe("unknown");
    expect(classifyAuthError("a string")).toBe("unknown");
    expect(classifyAuthError(undefined)).toBe("unknown");
  });
});

describe("classifyDataError", () => {
  it("classifies an insufficient-privilege refusal as denied", () => {
    expect(classifyDataError({ code: "42501" })).toBe("denied");
  });

  it("classifies a rejected JWT as denied", () => {
    expect(classifyDataError({ code: "PGRST301" })).toBe("denied");
  });

  it("classifies a transport failure as offline", () => {
    expect(classifyDataError(new TypeError("failed to fetch"))).toBe("offline");
  });

  it("falls back to unknown", () => {
    expect(classifyDataError({ code: "PGRST116" })).toBe("unknown");
  });
});

describe("message sanitization", () => {
  const leakyError = {
    code: "invalid_credentials",
    message:
      "Invalid login for athlete-a@example.test with token sb_secret_xyz",
    status: 400,
    request: { email: "athlete-a@example.test", password: "hunter2" },
    token: "eyJhbGciOiJIUzI1NiJ9.synthetic",
  };

  it("never includes the original message", () => {
    expect(authErrorMessage(leakyError)).not.toContain("Invalid login");
  });

  it("never includes an email address", () => {
    expect(authErrorMessage(leakyError)).not.toContain("@");
    expect(authErrorMessage(leakyError)).not.toContain("example.test");
  });

  it("never includes a token or key", () => {
    const message = authErrorMessage(leakyError);

    expect(message).not.toContain("sb_secret");
    expect(message).not.toContain("eyJ");
  });

  it("never includes a password from the request payload", () => {
    expect(authErrorMessage(leakyError)).not.toContain("hunter2");
  });

  it("returns the same fixed string for every error of one category", () => {
    expect(authErrorMessage({ code: "invalid_credentials" })).toBe(
      authErrorMessage(leakyError),
    );
  });

  it("sanitizes data errors the same way", () => {
    const message = dataErrorMessage({
      code: "42501",
      message: "permission denied for table profiles as user athlete-a",
      details: "athlete-a@example.test",
    });

    expect(message).not.toContain("@");
    expect(message).not.toContain("permission denied");
    expect(message).not.toContain("profiles");
  });

  it("returns a non-empty message for every input", () => {
    for (const input of [null, undefined, {}, new Error("boom"), 0, ""]) {
      expect(authErrorMessage(input).length).toBeGreaterThan(0);
      expect(dataErrorMessage(input).length).toBeGreaterThan(0);
    }
  });
});
