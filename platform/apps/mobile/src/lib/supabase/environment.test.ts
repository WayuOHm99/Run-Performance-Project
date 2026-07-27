import { describe, expect, it } from "vitest";

import {
  PublicSupabaseEnvironmentError,
  validatePublicSupabaseEnvironment,
} from "./environment";

const projectUrl = "https://altlphxckxsudnuwhqfw.supabase.co";
const syntheticPublishableKey = [
  "sb",
  "publishable",
  "synthetic-client-key-for-tests-only",
].join("_");

function expectSafeEnvironmentError(
  input: Parameters<typeof validatePublicSupabaseEnvironment>[0],
  forbiddenValue?: string,
) {
  let thrown: unknown;

  try {
    validatePublicSupabaseEnvironment(input);
  } catch (error) {
    thrown = error;
  }

  expect(thrown).toBeInstanceOf(PublicSupabaseEnvironmentError);

  if (forbiddenValue && thrown instanceof Error) {
    expect(thrown.message).not.toContain(forbiddenValue);
  }
}

describe("validatePublicSupabaseEnvironment", () => {
  it("accepts the configured project and a synthetic publishable key", () => {
    expect(
      validatePublicSupabaseEnvironment({
        url: projectUrl,
        publishableKey: syntheticPublishableKey,
      }),
    ).toEqual({
      url: projectUrl,
      publishableKey: syntheticPublishableKey,
    });
  });

  it("rejects missing variables", () => {
    expectSafeEnvironmentError({
      url: undefined,
      publishableKey: undefined,
    });
    expectSafeEnvironmentError({
      url: projectUrl,
      publishableKey: undefined,
    });
  });

  it("rejects a different Supabase project without echoing its URL", () => {
    const differentProjectUrl = "https://synthetic-project.supabase.co";

    expectSafeEnvironmentError(
      {
        url: differentProjectUrl,
        publishableKey: syntheticPublishableKey,
      },
      differentProjectUrl,
    );
  });

  it.each([
    ["sb", "secret", "synthetic-server-key-for-tests-only"].join("_"),
    ["ey", "Jsynthetic-legacy-jwt-key-for-tests-only"].join(""),
  ])("rejects a server-capable key format without echoing it", (key) => {
    expectSafeEnvironmentError(
      {
        url: projectUrl,
        publishableKey: key,
      },
      key,
    );
  });

  it("rejects an invalid publishable key format without echoing it", () => {
    const invalidKey = "not-a-publishable-key";

    expectSafeEnvironmentError(
      {
        url: projectUrl,
        publishableKey: invalidKey,
      },
      invalidKey,
    );
  });
});
