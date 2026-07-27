import { describe, expect, it, vi } from "vitest";

import { createAuthPersistenceOptions } from "./auth-options";

const storage = {
  getItem: () => Promise.resolve(null),
  setItem: () => Promise.resolve(),
  removeItem: () => Promise.resolve(),
};

describe("createAuthPersistenceOptions", () => {
  it("gives web no way to persist a session", () => {
    const createStorage = vi.fn(() => storage);

    const options = createAuthPersistenceOptions({
      isWeb: true,
      createStorage,
    });

    expect(options.persistSession).toBe(false);
    // Absent, not merely undefined, so nothing can be persisted anywhere.
    expect("storage" in options).toBe(false);
    // The native adapter is never even constructed on web.
    expect(createStorage).not.toHaveBeenCalled();
  });

  it("gives native the encrypted adapter", () => {
    const createStorage = vi.fn(() => storage);

    const options = createAuthPersistenceOptions({
      isWeb: false,
      createStorage,
    });

    expect(options.persistSession).toBe(true);
    expect(options.storage).toBe(storage);
    expect(createStorage).toHaveBeenCalledTimes(1);
  });

  it("never detects a session in the URL on either platform", () => {
    for (const isWeb of [true, false]) {
      expect(
        createAuthPersistenceOptions({ isWeb, createStorage: () => storage })
          .detectSessionInUrl,
      ).toBe(false);
    }
  });
});
