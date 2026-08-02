import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { Home } from "./Home";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ signOut: vi.fn() }) }));
vi.mock("../lib/api");

it("links to settings as the supported preference editing path", async () => {
  vi.mocked(apiFetch)
    .mockResolvedValueOnce({
      id: "user-1",
      role: "learner",
      is_active: true,
      created_at: "2026-08-02T00:00:00Z",
      preferences: {},
    } as never)
    .mockResolvedValueOnce({
      track: {
        slug: "ibo_foundations",
        name: "Foundations",
        min_difficulty: "beginner",
        max_difficulty: "intermediate",
        is_default: true,
        units: [],
      },
      is_fallback: true,
    } as never);

  render(<Home />, { wrapper: MemoryRouter });

  expect(
    await screen.findByRole("link", { name: /settings/i }),
  ).toHaveAttribute("href", "/settings");
});
