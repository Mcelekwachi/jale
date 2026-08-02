import { describe, expect, it } from "vitest";

import { readEnvironment } from "../lib/env";

describe("readEnvironment", () => {
  it("reports every missing variable in a readable startup error", () => {
    expect(() => readEnvironment({ VITE_SUPABASE_URL: "" })).toThrow(
      "Missing frontend environment variables: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_BASE_URL",
    );
  });
});
