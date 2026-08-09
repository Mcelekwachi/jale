import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { Home } from "./Home";

vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ signOut: vi.fn() }) }));
vi.mock("../lib/api");

const track = {
  track: {
    slug: "ibo_foundations",
    name: "Foundations",
    min_difficulty: "beginner",
    max_difficulty: "intermediate",
    is_default: true,
    units: [
      {
        position: 1,
        title: "Greetings",
        mode: "flashcard",
        item_count: 10,
        available: 10,
      },
      {
        position: 2,
        title: "Proverbs",
        mode: "proverbs",
        item_count: 4,
        available: 0,
      },
    ],
  },
  is_fallback: true,
};

describe("Home", () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset());

  it("shows track, due review, progress, and disables unavailable units", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 3,
        today_goal_met: true,
      } as never)
      .mockResolvedValueOnce({ items: [{ id: 99 }] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: "nld" } } as never)
      .mockResolvedValueOnce([{ code: "nld", name: "Dutch" }] as never);

    render(<Home />, { wrapper: MemoryRouter });

    expect(
      await screen.findByRole("link", { name: /settings/i }),
    ).toHaveAttribute("href", "/settings");
    expect(screen.getByText("Foundations")).toBeInTheDocument();
    expect(screen.getByText(/learning with Dutch/i)).toBeInTheDocument();
    expect(screen.getByText(/3 day streak/i)).toBeInTheDocument();
    expect(screen.getByText(/today's goal met/i)).toBeInTheDocument();
    expect(screen.getByText(/review due/i)).toHaveTextContent("1");
    expect(screen.getByRole("link", { name: /greetings/i })).toHaveAttribute(
      "href",
      "/study/ibo_foundations/1",
    );
    expect(
      screen.queryByRole("link", { name: /proverbs/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/content is being prepared/i)).toBeInTheDocument();
  });

  it("invites a new learner instead of rendering a zero streak badge", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(track as never)
      .mockResolvedValueOnce({
        current_streak: 0,
        today_goal_met: false,
      } as never)
      .mockResolvedValueOnce({ items: [] } as never)
      .mockResolvedValueOnce({ preferences: { meta_language: null } } as never)
      .mockResolvedValueOnce([{ code: "eng", name: "English" }] as never);
    render(<Home />, { wrapper: MemoryRouter });
    expect(
      await screen.findByText(/start your streak today/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/0 day streak/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/review due/i)).not.toBeInTheDocument();
  });
});
