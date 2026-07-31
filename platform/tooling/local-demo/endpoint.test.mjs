import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ANDROID_EMULATOR_SUPABASE_URL,
  assertCanonicalLocalUrl,
  DemoEndpointError,
  LOCAL_SUPABASE_URL,
  resolveSurfaceUrl,
} from "./endpoint.mjs";

// Every category decision 4 names, each as its own case, so a regression says
// which class of URL started being accepted.
const REJECTED_URLS = {
  "hosted project": "https://altlphxckxsudnuwhqfw.supabase.co",
  "any hosted supabase host": "https://synthetic-project.supabase.co",
  "arbitrary LAN host": "http://192.168.1.10:54321",
  "another LAN host": "http://10.0.0.5:54321",
  "the android alias (not canonical)": "http://10.0.2.2:54321",
  localhost: "http://localhost:54321",
  "IPv6 loopback": "http://[::1]:54321",
  "another port": "http://127.0.0.1:54322",
  "the studio port": "http://127.0.0.1:54323",
  "no port": "http://127.0.0.1",
  "https scheme": "https://127.0.0.1:54321",
  userinfo: "http://user:password@127.0.0.1:54321",
  "userinfo without a password": "http://user@127.0.0.1:54321",
  "a path": "http://127.0.0.1:54321/rest/v1",
  "a trailing slash": "http://127.0.0.1:54321/",
  "a query": "http://127.0.0.1:54321?apikey=x",
  "a fragment": "http://127.0.0.1:54321#x",
  "leading whitespace": " http://127.0.0.1:54321",
  "trailing whitespace": "http://127.0.0.1:54321 ",
  "a decimal-encoded loopback": "http://2130706433:54321",
  empty: "",
};

describe("assertCanonicalLocalUrl", () => {
  it("accepts exactly the canonical local endpoint", () => {
    assert.equal(
      assertCanonicalLocalUrl(LOCAL_SUPABASE_URL),
      "http://127.0.0.1:54321",
    );
  });

  for (const [label, url] of Object.entries(REJECTED_URLS)) {
    it(`rejects ${label}`, () => {
      assert.throws(() => assertCanonicalLocalUrl(url), DemoEndpointError);
    });
  }

  it("never echoes the rejected value", () => {
    for (const url of Object.values(REJECTED_URLS)) {
      if (url === "") {
        continue;
      }

      try {
        assertCanonicalLocalUrl(url);
        assert.fail("expected a rejection");
      } catch (error) {
        assert.ok(
          !error.message.includes(url),
          "the rejection message must not quote the rejected URL",
        );
      }
    }
  });

  it("rejects non-string input", () => {
    for (const value of [undefined, null, 0, {}, []]) {
      assert.throws(() => assertCanonicalLocalUrl(value), DemoEndpointError);
    }
  });
});

describe("resolveSurfaceUrl", () => {
  it("maps web to the canonical loopback endpoint", () => {
    assert.equal(resolveSurfaceUrl("web"), LOCAL_SUPABASE_URL);
  });

  it("maps android to the emulator host-loopback alias", () => {
    assert.equal(resolveSurfaceUrl("android"), ANDROID_EMULATOR_SUPABASE_URL);
  });

  it("keeps both surfaces on port 54321 and on http", () => {
    for (const surface of ["web", "android"]) {
      const url = new URL(resolveSurfaceUrl(surface));
      assert.equal(url.port, "54321");
      assert.equal(url.protocol, "http:");
      assert.equal(url.pathname, "/");
      assert.equal(url.search, "");
      assert.equal(url.hash, "");
      assert.equal(url.username, "");
      assert.equal(url.password, "");
    }
  });

  it("refuses every out-of-scope surface", () => {
    for (const surface of ["ios", "device", "lan", "tunnel", "", undefined]) {
      assert.throws(() => resolveSurfaceUrl(surface), DemoEndpointError);
    }
  });
});
