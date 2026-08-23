import { describe, expect, it } from "vitest";

import manifest from "../public/manifest.json";

describe("app identity", () => {
  it("uses Jalɛ for the installed app name", () => {
    expect(manifest.name).toBe("Jalɛ");
    expect(manifest.short_name).toBe("Jalɛ");
  });
});
