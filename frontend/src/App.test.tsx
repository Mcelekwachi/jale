import { render, screen } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { apiFetch } from "./lib/api";

vi.mock("./auth/AuthProvider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("./auth/ProtectedRoute", () => ({
  ProtectedRoute: () => <Outlet />,
}));
vi.mock("./lib/api");

describe("App admin route", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/admin");
    vi.mocked(apiFetch).mockReset();
  });

  it("renders a non-empty loading state while the admin profile resolves", () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));

    const { container } = render(<App />);

    expect(container).not.toBeEmptyDOMElement();
    expect(
      screen.getByRole("status", { name: /loading admin profile/i }),
    ).toBeInTheDocument();
  });

  it("renders the content list through the router for an admin", async () => {
    window.history.replaceState({}, "", "/admin/content");
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        id: "admin-1",
        role: "admin",
        is_active: true,
        created_at: "2026-08-16T00:00:00Z",
        preferences: {
          active_language: "ibo",
          reminder_enabled: false,
          timezone: "Europe/Berlin",
          placement_skipped: false,
          onboarding_status: "completed",
          updated_at: "2026-08-16T00:00:00Z",
        },
      } as never)
      .mockResolvedValueOnce({ items: [], total: 0, limit: 50, offset: 0 });

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /content management/i }),
    ).toBeInTheDocument();
  });

  it("renders the content detail through the router for an admin", async () => {
    window.history.replaceState({}, "", "/admin/content/42");
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        id: "admin-1",
        role: "admin",
        is_active: true,
        created_at: "2026-08-16T00:00:00Z",
        preferences: {
          active_language: "ibo",
          reminder_enabled: false,
          timezone: "Europe/Berlin",
          placement_skipped: false,
          onboarding_status: "completed",
          updated_at: "2026-08-16T00:00:00Z",
        },
      } as never)
      .mockResolvedValueOnce({
        item: { id: 42, target_text: "Ndewo" },
        translations: [],
      });

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: /edit content/i }),
    ).toBeInTheDocument();
  });

  it.each(["/admin/content", "/admin/content/42"])(
    "shows no access for a learner at %s",
    async (path) => {
      window.history.replaceState({}, "", path);
      vi.mocked(apiFetch).mockResolvedValueOnce({
        id: "learner-1",
        role: "learner",
        is_active: true,
        created_at: "2026-08-16T00:00:00Z",
        preferences: {
          active_language: "ibo",
          reminder_enabled: false,
          timezone: "Europe/Berlin",
          placement_skipped: false,
          onboarding_status: "completed",
          updated_at: "2026-08-16T00:00:00Z",
        },
      } as never);

      render(<App />);

      expect(
        await screen.findByRole("heading", { name: /no admin access/i }),
      ).toBeInTheDocument();
      expect(apiFetch).toHaveBeenCalledTimes(1);
    },
  );

  it("renders a not-found screen for an unknown path", () => {
    window.history.replaceState({}, "", "/definitely-not-a-route");

    render(<App />);

    expect(
      screen.getByRole("heading", { name: /page not found/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /home/i })).toHaveAttribute(
      "href",
      "/",
    );
  });

  it("shows a non-blocking offline indicator", () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      value: false,
    });
    window.history.replaceState({}, "", "/definitely-not-a-route");

    render(<App />);

    expect(screen.getByRole("status", { name: /offline/i })).toBeInTheDocument();
  });
});
