import { describe, expect, it } from "vitest";

import { roleOptions } from "./role-options";

describe("role preview options", () => {
  it("keeps the athlete experience first", () => {
    expect(roleOptions[0]?.id).toBe("athlete");
  });

  it("uses one unique route per role", () => {
    const routes = roleOptions.map((role) => role.route);

    expect(new Set(routes).size).toBe(roleOptions.length);
  });
});
