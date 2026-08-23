import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("app identity", () => {
  it("uses Jalɛ for the document title and installed app name", () => {
    const projectRoot = resolve(import.meta.dirname, "..");
    const html = readFileSync(resolve(projectRoot, "index.html"), "utf8");
    const manifestPath = resolve(projectRoot, "public", "manifest.json");

    expect(html).toContain("<title>Jalɛ</title>");
    expect(existsSync(manifestPath)).toBe(true);

    const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as {
      name: string;
      short_name: string;
    };
    expect(manifest.name).toBe("Jalɛ");
    expect(manifest.short_name).toBe("Jalɛ");
  });
});
