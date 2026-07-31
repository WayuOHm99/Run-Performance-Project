import { describe, expect, it } from "vitest";

import {
  PublicSupabaseEnvironmentError,
  resolveSupabaseEnvironmentMode,
  validatePublicSupabaseEnvironment,
} from "./environment";

const projectUrl = "https://altlphxckxsudnuwhqfw.supabase.co";
const localUrl = "http://127.0.0.1:54321";
const androidEmulatorUrl = "http://10.0.2.2:54321";
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

// TASK-017. Local mode is a separate, explicitly declared mode rather than a
// widening of the accepted URL set.
describe("resolveSupabaseEnvironmentMode", () => {
  it("defaults to hosted when the variable is absent or empty", () => {
    expect(resolveSupabaseEnvironmentMode(undefined)).toBe("hosted");
    expect(resolveSupabaseEnvironmentMode("")).toBe("hosted");
  });

  it("accepts the two declared modes", () => {
    expect(resolveSupabaseEnvironmentMode("hosted")).toBe("hosted");
    expect(resolveSupabaseEnvironmentMode("local")).toBe("local");
  });

  // A typo must stop the app rather than silently aiming it at the hosted
  // project, which is what a fallback-to-hosted default would do.
  it.each(["locl", "LOCAL", "Local", "development", "dev", "prod", " local"])(
    "rejects the unrecognised mode %j rather than falling back",
    (mode) => {
      expect(() => resolveSupabaseEnvironmentMode(mode)).toThrow(
        PublicSupabaseEnvironmentError,
      );
    },
  );
});

describe("local mode", () => {
  it("accepts the canonical local endpoint", () => {
    expect(
      validatePublicSupabaseEnvironment({
        url: localUrl,
        publishableKey: syntheticPublishableKey,
        mode: "local",
      }),
    ).toEqual({
      url: localUrl,
      publishableKey: syntheticPublishableKey,
    });
  });

  it("accepts the emulator alias only on Android", () => {
    expect(
      validatePublicSupabaseEnvironment({
        url: androidEmulatorUrl,
        publishableKey: syntheticPublishableKey,
        mode: "local",
        isAndroid: true,
      }),
    ).toEqual({
      url: androidEmulatorUrl,
      publishableKey: syntheticPublishableKey,
    });
  });

  it.each([undefined, false])(
    "rejects the emulator alias when isAndroid is %j",
    (isAndroid) => {
      expectSafeEnvironmentError(
        {
          url: androidEmulatorUrl,
          publishableKey: syntheticPublishableKey,
          mode: "local",
          isAndroid,
        },
        androidEmulatorUrl,
      );
    },
  );

  // Every rejection category decision 4 names, each as its own case.
  it.each([
    ["the hosted project", projectUrl],
    ["another hosted project", "https://synthetic-project.supabase.co"],
    ["an arbitrary LAN host", "http://192.168.1.10:54321"],
    ["another LAN host", "http://10.0.0.5:54321"],
    ["localhost", "http://localhost:54321"],
    ["the IPv6 loopback", "http://[::1]:54321"],
    ["another port", "http://127.0.0.1:54322"],
    ["the studio port", "http://127.0.0.1:54323"],
    ["no port", "http://127.0.0.1"],
    ["an https scheme", "https://127.0.0.1:54321"],
    ["userinfo", "http://user:password@127.0.0.1:54321"],
    ["userinfo without a password", "http://user@127.0.0.1:54321"],
    ["a path", "http://127.0.0.1:54321/rest/v1"],
    ["a trailing slash", "http://127.0.0.1:54321/"],
    ["a query", "http://127.0.0.1:54321?apikey=x"],
    ["a fragment", "http://127.0.0.1:54321#x"],
    ["leading whitespace", " http://127.0.0.1:54321"],
    ["trailing whitespace", "http://127.0.0.1:54321 "],
    ["a decimal-encoded loopback", "http://2130706433:54321"],
  ])("rejects %s without echoing it", (_label, url) => {
    expectSafeEnvironmentError(
      {
        url,
        publishableKey: syntheticPublishableKey,
        mode: "local",
        isAndroid: true,
      },
      url,
    );
  });

  it("still requires a publishable key", () => {
    expectSafeEnvironmentError({
      url: localUrl,
      publishableKey: undefined,
      mode: "local",
    });
  });

  // Local mode must not become a way to smuggle a server key into the client:
  // the local stack has a service-role key too, and it is just as dangerous in a
  // bundle as a hosted one.
  it.each([
    [
      "a secret key",
      ["sb", "secret", "synthetic-local-secret-for-tests"].join("_"),
    ],
    ["a legacy JWT", ["ey", "Jsynthetic-legacy-jwt-for-tests-only"].join("")],
    ["a database URL", "postgresql://postgres:pw@127.0.0.1:54322/postgres"],
    ["a bare password", "synthetic-password"],
    ["a malformed key", "sb_publishable_short"],
  ])("rejects %s in local mode without echoing it", (_label, key) => {
    expectSafeEnvironmentError(
      {
        url: localUrl,
        publishableKey: key,
        mode: "local",
      },
      key,
    );
  });
});

describe("hosted mode", () => {
  // The mirror of the rule above: declaring hosted mode must not let a local
  // endpoint through either.
  it.each([localUrl, androidEmulatorUrl])(
    "rejects the local endpoint %s",
    (url) => {
      expectSafeEnvironmentError(
        {
          url,
          publishableKey: syntheticPublishableKey,
          mode: "hosted",
          isAndroid: true,
        },
        url,
      );
    },
  );

  it("rejects the local endpoint when no mode is declared at all", () => {
    expectSafeEnvironmentError(
      {
        url: localUrl,
        publishableKey: syntheticPublishableKey,
      },
      localUrl,
    );
  });

  it("fails on an unusable mode before it reports anything about the URL", () => {
    let thrown: unknown;

    try {
      validatePublicSupabaseEnvironment({
        url: undefined,
        publishableKey: undefined,
        mode: "nonsense",
      });
    } catch (error) {
      thrown = error;
    }

    expect(thrown).toBeInstanceOf(PublicSupabaseEnvironmentError);
    expect((thrown as Error).message).toContain(
      "EXPO_PUBLIC_SUPABASE_ENVIRONMENT",
    );
  });
});
