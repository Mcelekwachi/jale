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

const catalogue = {
  learnable: [
    { code: "ibo", name: "Igbo", endonym: "Asụsụ Igbo", available: true, content_count: 157 },
  ],
  meta: [
    { code: "eng", name: "English", endonym: "English", available: true, translated_count: 157, total_count: 157 },
    { code: "nld", name: "Dutch", endonym: "Nederlands", available: true, translated_count: 0, total_count: 157 },
  ],
};

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
      if (path === "/v1/languages/catalogue") return catalogue as never;
      return profile() as never;
    });
  });

  it("shows the language catalogue, disabled roadmap entries, and coverage", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      if (path === "/v1/languages/catalogue")
        return {
          learnable: [
            {
              code: "ibo",
              name: "Igbo",
              endonym: "Asụsụ Igbo",
              available: true,
              translated_count: 157,
              total_count: 157,
            },
            {
              code: "yor",
              name: "Yoruba",
              endonym: "Èdè Yorùbá",
              available: false,
              translated_count: 0,
              total_count: 0,
            },
            {
              code: "hau",
              name: "Hausa",
              endonym: "Harshen Hausa",
              available: true,
              translated_count: 0,
              total_count: 0,
            },
          ],
          meta: [
            {
              code: "eng",
              name: "English",
              endonym: "English",
              available: true,
              translated_count: 157,
              total_count: 157,
            },
            {
              code: "nld",
              name: "Dutch",
              endonym: "Nederlands",
              available: true,
              translated_count: 0,
              total_count: 157,
            },
          ],
        } as never;
      return profile() as never;
    });

    renderPath("/onboarding/2");

    const target = await screen.findByLabelText("What do you want to learn?");
    expect(target).toBeInstanceOf(HTMLSelectElement);
    expect(
      screen.queryByLabelText("What language do you want to learn with?"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Èdè Yorùbá.*coming soon/i }),
    ).toBeDisabled();

    await userEvent.selectOptions(target, "ibo");
    const meta = screen.getByLabelText(
      "What language do you want to learn with?",
    );
    expect(meta).toBeInstanceOf(HTMLSelectElement);
    expect(
      screen.queryByRole("option", { name: /English.*157\/157/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /Dutch.*0\/157 translated/i }),
    ).toBeInTheDocument();

    await userEvent.selectOptions(meta, "nld");
    expect(screen.getByText(/Dutch translations are still being written/i)).toBeInTheDocument();

    await userEvent.selectOptions(target, "hau");
    expect(meta).toHaveValue("nld");
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.anything(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        body: JSON.stringify({
          active_language: "hau",
          meta_language: "nld",
          onboarding_last_screen: 3,
        }),
      }),
    );
  });

  it("patches only the screen answer and reached screen before advancing", async () => {
    renderPath("/onboarding/3");
    await userEvent.click(
      await screen.findByRole("button", { name: /adult 25\+/i }),
    );

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          age_band: "adult_25_plus",
          onboarding_last_screen: 4,
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
      4,
      "Language enthusiast",
      { connection: "language_enthusiast", onboarding_last_screen: 5 },
    ],
    [
      5,
      "Visiting Nigeria",
      { goal: "visiting_nigeria", onboarding_last_screen: 6 },
    ],
    [6, "A mix of both", { style: "mixed", onboarding_last_screen: 7 }],
    [7, "15 minutes", { daily_minutes: 15, onboarding_last_screen: 8 }],
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
    renderPath("/onboarding/8");
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
      onboarding_last_screen: 9,
    });
  });

  it("shows retry and does not advance after a failed patch", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      throw new Error("Save failed");
    });
    renderPath("/onboarding/5");
    await userEvent.click(
      await screen.findByRole("button", { name: /visiting nigeria/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Save failed");
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/onboarding/5");
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
      profile({ onboarding_last_screen: 6 }) as never,
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
    renderPath("/onboarding/4");
    await screen.findByRole("heading", { name: /your connection/i });
    await userEvent.click(screen.getByRole("button", { name: /back/i }));

    expect(
      await screen.findByRole("button", { name: /adult 25\+/i }),
    ).toHaveAttribute("aria-pressed", "true");
  });

  it("clears an invalid saved goal and explains that it needs revisiting", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me")
        return profile({
          age_band: "adult_25_plus",
          connection: "language_enthusiast",
          goal: "teach_my_children",
        }) as never;
      return profile() as never;
    });
    renderPath("/onboarding/3");

    await userEvent.click(
      await screen.findByRole("button", { name: /child under 13/i }),
    );

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        body: JSON.stringify({
          age_band: "child_u13",
          goal: null,
          onboarding_last_screen: 5,
        }),
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      /goal no longer fits.*choose it again/i,
    );
    expect(window.location.pathname).toBe("/onboarding/5");
  });

  it("shows the completion summary and completes only on the primary action", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me")
        return profile({
          meta_language: "nld",
          connection: "language_enthusiast",
          goal: "visiting_nigeria",
          daily_minutes: 15,
          onboarding_last_screen: 10,
        }) as never;
      if (path === "/v1/languages/catalogue") return catalogue as never;
      return profile() as never;
    });
    renderPath("/onboarding/10");

    expect(await screen.findByText("Visiting Nigeria")).toBeInTheDocument();
    expect(screen.getByText("Igbo with Dutch")).toBeInTheDocument();
    expect(screen.getByText("15 minutes")).toBeInTheDocument();
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/v1/me/onboarding/complete",
      expect.anything(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /start learning/i }),
    );
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/onboarding/complete",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("resumes directly on completion under the new numbering", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me")
        return profile({ onboarding_last_screen: 10 }) as never;
      if (path === "/v1/languages/catalogue") return catalogue as never;
      return profile() as never;
    });
    renderPath("/");

    expect(
      await screen.findByRole("heading", { name: /ready to begin/i }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/onboarding/10");
  });

  it("marks screen transitions as disabled for reduced motion", async () => {
    renderPath("/onboarding/3");
    const heading = await screen.findByRole("heading", { name: /who are you/i });
    expect(heading.closest("section")).toHaveClass("motion-reduce:animate-none");
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
      if (path === "/v1/languages/catalogue") return catalogue as never;
      return profile() as never;
    });
    renderPath("/onboarding/9");

    await userEvent.click(
      await screen.findByRole("button", { name: "Right beginner" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Right intermediate" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Wrong A advanced" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          placement_level: "intermediate",
          onboarding_last_screen: 10,
        }),
      }),
    );
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/v1/me/onboarding/complete",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("treats I'm not sure as neutral and incorrect while revealing the answer", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      if (path.startsWith("/v1/content")) {
        const difficulty = new URL(`https://test${path}`).searchParams.get(
          "difficulty",
        );
        return {
          items: [
            {
              id: difficulty === "beginner" ? 11 : difficulty === "intermediate" ? 21 : 31,
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
      if (path === "/v1/languages/catalogue") return catalogue as never;
      return profile() as never;
    });
    renderPath("/onboarding/9");

    await userEvent.click(
      await screen.findByRole("button", { name: "I'm not sure" }),
    );

    expect(
      screen.getByRole("button", { name: /I'm not sure.*Your answer.*Not sure/i }),
    ).toHaveClass("bg-[#eee9df]");
    expect(
      screen.getByRole("button", { name: /Right beginner.*Correct answer/i }),
    ).toHaveTextContent("✓");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    await userEvent.click(
      screen.getByRole("button", { name: "Right intermediate" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(screen.getByRole("button", { name: "Right advanced" }));
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        body: expect.stringContaining('"placement_level":"intermediate"'),
      }),
    );
  });

  it("skips placement without patching placement and still completes", async () => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/me") return profile() as never;
      if (path.startsWith("/v1/content")) return { items: [] } as never;
      if (path === "/v1/languages/catalogue") return catalogue as never;
      return profile() as never;
    });
    renderPath("/onboarding/9");
    await userEvent.click(
      await screen.findByRole("button", { name: /skip this/i }),
    );

    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({ body: expect.stringContaining("placement") }),
    );
    expect(window.location.pathname).toBe("/onboarding/10");
  });
});
