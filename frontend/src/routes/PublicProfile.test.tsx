import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { PublicProfile } from "./PublicProfile";

vi.mock("../lib/api");

function renderProfile() {
  render(
    <MemoryRouter initialEntries={["/u/ada-learner"]}>
      <Routes>
        <Route path="/u/:shareSlug" element={<PublicProfile />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PublicProfile", () => {
  it("renders the privacy-safe profile for a signed-out visitor", async () => {
    const response = {
      display_name: "Ada Learner",
      current_streak: 7,
      longest_streak: 19,
      total_mastered: 42,
      language: "ibo",
      language_name: "Igbo",
      language_endonym: "Asụsụ Igbo",
      joined_month: "2024-03",
    };
    vi.mocked(apiFetch).mockResolvedValue(response);

    renderProfile();

    expect(await screen.findByRole("heading", { name: "Ada Learner" }))
      .toBeInTheDocument();
    expect(screen.getByText(/7 day current streak/i)).toBeInTheDocument();
    expect(screen.getByText(/19 day longest streak/i)).toBeInTheDocument();
    expect(screen.getByText(/42 mastered/i)).toBeInTheDocument();
    expect(screen.getByText(/learning Igbo \(Asụsụ Igbo\)/i)).toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(`\\b${response.language.toUpperCase()}\\b`)),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/joined March 2024/i)).toBeInTheDocument();
    expect(Object.keys(response).sort()).toEqual([
      "current_streak",
      "display_name",
      "joined_month",
      "language",
      "language_endonym",
      "language_name",
      "longest_streak",
      "total_mastered",
    ]);
    expect(response).not.toHaveProperty("email");
    expect(response).not.toHaveProperty("id");
    expect(response).not.toHaveProperty("preferences");
  });

  it("renders a friendly state for a missing profile", async () => {
    vi.mocked(apiFetch).mockRejectedValue({ status: 404, detail: "profile not found" });
    renderProfile();
    expect(await screen.findByRole("heading", {
      name: /this profile isn't available/i,
    })).toBeInTheDocument();
    expect(screen.queryByText(/profile not found/i)).not.toBeInTheDocument();
  });
});
