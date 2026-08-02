import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Outlet } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { apiFetch } from "../lib/api";

vi.mock("../auth/AuthProvider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../auth/ProtectedRoute", () => ({ ProtectedRoute: () => <Outlet /> }));
vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ signOut: vi.fn() }) }));
vi.mock("../lib/api");

const mockedApiFetch = vi.mocked(apiFetch);

describe("settings", () => {
  beforeEach(() => {
    mockedApiFetch.mockImplementation(async (path) => {
      if (path === "/v1/languages/meta") {
        return [
          {
            code: "eng",
            name: "English",
            is_active: true,
            translated_count: 157,
            total_count: 157,
          },
          {
            code: "nld",
            name: "Dutch",
            is_active: true,
            translated_count: 0,
            total_count: 157,
          },
        ] as never;
      }
      return {
        id: "user-1",
        role: "learner",
        is_active: true,
        created_at: "2026-08-02T00:00:00Z",
        preferences: {
          active_language: "ibo",
          meta_language: null,
          reminder_enabled: false,
          timezone: "Europe/Amsterdam",
          placement_skipped: false,
          onboarding_status: "completed",
          updated_at: "2026-08-02T00:00:00Z",
        },
      } as never;
    });
  });

  it("shows coverage and patches explanation language as a code only", async () => {
    window.history.replaceState({}, "", "/settings");
    render(<App />);

    expect(await screen.findByText(/Dutch.*0.*157/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Dutch/i }));
    expect(mockedApiFetch).toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ meta_language: "nld" }),
      }),
    );
  });

  it("defaults null explanation language from nl-NL without patching", async () => {
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("nl-NL");
    window.history.replaceState({}, "", "/settings");
    render(<App />);

    expect(
      await screen.findByRole("button", { name: /Dutch/i }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/v1/me/preferences",
      expect.anything(),
    );
  });
});
