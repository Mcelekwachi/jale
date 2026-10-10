import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { setUiLanguage } from "../i18n/useUiStrings";
import { OnboardingGuard } from "./OnboardingGuard";

vi.mock("../lib/api");

function profile(extra: Record<string, unknown>) {
  return {
    id: "user-1",
    role: "learner",
    is_active: true,
    created_at: "2026-10-10T00:00:00Z",
    preferences: { onboarding_status: "completed" },
    ...extra,
  } as never;
}

function renderGuard() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/age" element={<p>age gate</p>} />
        <Route element={<OnboardingGuard />}>
          <Route path="/" element={<p>home</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("age gate redirect", () => {
  beforeEach(() => {
    setUiLanguage("eng");
    vi.mocked(apiFetch).mockReset();
  });

  it("sends people who have not confirmed their age to the age gate", async () => {
    vi.mocked(apiFetch).mockResolvedValue(profile({ age_confirmed_at: null }));
    renderGuard();
    expect(await screen.findByText("age gate")).toBeInTheDocument();
  });

  it("lets confirmed adults and child profiles through", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      profile({ age_confirmed_at: "2026-10-10T00:00:00Z" }),
    );
    renderGuard();
    expect(await screen.findByText("home")).toBeInTheDocument();
  });

  it("does not gate a child profile", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      profile({ is_child: true, age_confirmed_at: null }),
    );
    renderGuard();
    expect(await screen.findByText("home")).toBeInTheDocument();
  });
});
