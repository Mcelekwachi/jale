import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Outlet } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { apiFetch } from "../lib/api";

vi.mock("../auth/AuthProvider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../auth/ProtectedRoute", () => ({ ProtectedRoute: () => <Outlet /> }));
vi.mock("../lib/api");
vi.mock("./Home", () => ({ Home: () => <p>Home screen</p> }));

const mockedApiFetch = vi.mocked(apiFetch);

const basePreferences = {
  active_language: "ibo",
  meta_language: null,
  age_band: null,
  connection: null,
  goal: null,
  style: null,
  daily_minutes: null,
  reminder_enabled: false,
  reminder_time: null,
  timezone: "UTC",
  placement_level: null,
  placement_skipped: false,
  onboarding_status: "not_started",
  onboarding_last_screen: null,
  updated_at: "2026-08-02T00:00:00Z",
};

function profile(overrides: Record<string, unknown> = {}) {
  return {
    id: "user-1",
    role: "learner",
    is_active: true,
    created_at: "2026-08-02T00:00:00Z",
    preferences: { ...basePreferences, ...overrides },
  };
}

function renderPath(path: string) {
  window.history.replaceState({}, "", path);
  return render(<App />);
}

describe("onboarding", () => {
  beforeEach(() => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      return profile() as never;
    });
  });

  it("patches only the screen answer and reached screen before advancing", async () => {
    renderPath("/onboarding/2");
    await userEvent.click(
      await screen.findByRole("button", { name: /adult 25\+/i }),
    );

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          age_band: "adult_25_plus",
          onboarding_last_screen: 3,
        }),
      }),
    );
    expect(
      await screen.findByRole("heading", { name: /your connection/i }),
    ).toBeInTheDocument();
  });

  it.each([
    [1, "Get started", { onboarding_last_screen: 2 }],
    [
      3,
      "Language enthusiast",
      { connection: "language_enthusiast", onboarding_last_screen: 4 },
    ],
    [
      4,
      "Visiting Nigeria",
      { goal: "visiting_nigeria", onboarding_last_screen: 5 },
    ],
    [5, "A mix of both", { style: "mixed", onboarding_last_screen: 6 }],
    [6, "15 minutes", { daily_minutes: 15, onboarding_last_screen: 7 }],
  ])(
    "screen %i writes only its answer and resume marker",
    async (step, label, body) => {
      renderPath(`/onboarding/${step}`);
      await userEvent.click(await screen.findByRole("button", { name: label }));
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/v1/me/preferences",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify(body),
        }),
      );
    },
  );

  it("saves reminder fields with the detected timezone", async () => {
    renderPath("/onboarding/7");
    await userEvent.click(
      await screen.findByRole("button", { name: /set reminder/i }),
    );
    const call = mockedApiFetch.mock.calls.find(
      ([path]) => path === "/v1/me/preferences",
    );
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body).toEqual({
      reminder_enabled: true,
      reminder_time: "09:00:00",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      onboarding_last_screen: 8,
    });
  });

  it("shows retry and does not advance after a failed patch", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      throw new Error("Save failed");
    });
    renderPath("/onboarding/4");
    await userEvent.click(
      await screen.findByRole("button", { name: /visiting nigeria/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Save failed");
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/onboarding/4");
  });

  it("skips from screen four with its current screen", async () => {
    renderPath("/onboarding/4");
    await userEvent.click(
      await screen.findByRole("button", { name: /skip for now/i }),
    );

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/onboarding/skip",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ onboarding_last_screen: 4 }),
      }),
    );
    await waitFor(() => expect(window.location.pathname).toBe("/"));
  });

  it("resumes an unfinished user and leaves completed users on home", async () => {
    mockedApiFetch.mockResolvedValueOnce(
      profile({ onboarding_last_screen: 5 }) as never,
    );
    const view = renderPath("/");
    expect(
      await screen.findByRole("heading", { name: /learning style/i }),
    ).toBeInTheDocument();

    view.unmount();
    mockedApiFetch.mockReset();
    mockedApiFetch.mockResolvedValue(
      profile({ onboarding_status: "completed" }) as never,
    );
    renderPath("/");
    expect(await screen.findByText("Home screen")).toBeInTheDocument();
  });

  it("shows a saved answer selected after back navigation", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me")
        return profile({ age_band: "adult_25_plus" }) as never;
      return profile({ age_band: "adult_25_plus" }) as never;
    });
    renderPath("/onboarding/3");
    await screen.findByRole("heading", { name: /your connection/i });
    await userEvent.click(screen.getByRole("button", { name: /back/i }));

    expect(
      await screen.findByRole("button", { name: /adult 25\+/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("scores two placement answers as intermediate", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      if (path.startsWith("/v1/content")) {
        const difficulty = new URL(`https://test${path}`).searchParams.get(
          "difficulty",
        );
        return {
          items: [
            {
              id: 1,
              content_type: "word",
              target_text: `Prompt ${difficulty}`,
              translation: `Right ${difficulty}`,
            },
            {
              id: 2,
              content_type: "word",
              target_text: "a",
              translation: `Wrong A ${difficulty}`,
            },
            {
              id: 3,
              content_type: "word",
              target_text: "b",
              translation: `Wrong B ${difficulty}`,
            },
            {
              id: 4,
              content_type: "word",
              target_text: "c",
              translation: `Wrong C ${difficulty}`,
            },
          ],
        } as never;
      }
      return profile() as never;
    });
    renderPath("/onboarding/8");

    await userEvent.click(
      await screen.findByRole("button", { name: "Right beginner" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Right intermediate" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Wrong A advanced" }),
    );

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          placement_level: "intermediate",
          onboarding_last_screen: 8,
        }),
      }),
    );
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/onboarding/complete",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("skips placement without patching placement and still completes", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      if (path.startsWith("/v1/content")) return { items: [] } as never;
      return profile() as never;
    });
    renderPath("/onboarding/8");
    await userEvent.click(
      await screen.findByRole("button", { name: /skip this/i }),
    );

    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({ body: expect.stringContaining("placement") }),
    );
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/onboarding/complete",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
