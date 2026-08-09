import { describe, expect, it } from "vitest";

import { connectionChoicesFor, goalChoicesFor } from "./options";

const values = <T extends string>(choices: { value: T }[]) =>
  choices.map(({ value }) => value);

describe("adaptive onboarding options", () => {
  it("removes parent connections and adult goals for a child", () => {
    expect(values(connectionChoicesFor("child_u13"))).not.toEqual(
      expect.arrayContaining(["igbo_parent_abroad", "mixed_parent_abroad"]),
    );
    expect(values(goalChoicesFor("child_u13", null))).not.toEqual(
      expect.arrayContaining([
        "teach_my_children",
        "academic_professional",
        "improve_proverbs_vocab",
      ]),
    );
  });

  it("does not offer new-language as a goal to a native speaker", () => {
    expect(
      values(goalChoicesFor("adult_25_plus", "aboriginal_native")),
    ).not.toContain("new_language");
  });

  it("keeps every option for an adult with another connection", () => {
    expect(connectionChoicesFor("adult_25_plus")).toHaveLength(8);
    expect(
      goalChoicesFor("adult_25_plus", "language_enthusiast"),
    ).toHaveLength(7);
  });
});
