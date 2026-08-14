import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { AdminErrorBoundary, AdminRoute } from "./Admin";

vi.mock("../lib/api");

const profile = (role: string) => ({
  id: "user-1",
  role,
  is_active: true,
  created_at: "2026-08-14T00:00:00Z",
  preferences: {
    active_language: "ibo",
    reminder_enabled: false,
    timezone: "Europe/Berlin",
    placement_skipped: false,
    onboarding_status: "completed",
    updated_at: "2026-08-14T00:00:00Z",
  },
});

const queue = [
  {
    content_id: 42,
    target_text: "Ndewo",
    content_type: "word",
    translation: "Hello",
    flag_count: 2,
    oldest_flag_at: "2026-08-13T00:00:00Z",
    reasons: ["wrong_translation", "other"],
    reporter_count: 2,
    flags: [
      {
        id: 7,
        reason: "wrong_translation",
        note: null,
        reporter_id: "user-2",
        status: "open",
        created_at: "2026-08-13T00:00:00Z",
        meta_language: "eng",
      },
    ],
  },
];

function ThrowingChild(): never {
  throw new Error("queue exploded");
}

describe("AdminRoute", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset();
  });

  it("renders a spinner while the profile is loading and never renders empty", () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    const { container } = render(<AdminRoute />);

    expect(
      screen.getByRole("status", { name: /loading admin profile/i }),
    ).toBeInTheDocument();
    expect(container).not.toBeEmptyDOMElement();
  });

  it("renders the no-access page for a loaded learner and never renders empty", async () => {
    vi.mocked(apiFetch).mockResolvedValue(profile("learner") as never);
    const { container } = render(<AdminRoute />);

    expect(
      await screen.findByRole("heading", { name: /no admin access/i }),
    ).toBeInTheDocument();
    expect(container).not.toBeEmptyDOMElement();
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("renders the flag queue for a loaded admin and never renders empty", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(profile("admin") as never)
      .mockResolvedValueOnce(queue as never);
    const { container } = render(<AdminRoute />);

    expect(
      await screen.findByRole("heading", { name: /flag queue/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Ndewo")).toBeInTheDocument();
    expect(screen.getByText("wrong translation")).toBeInTheDocument();
    expect(container).not.toBeEmptyDOMElement();
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/v1/admin/flags", {
      authenticated: true,
    });
  });
});

describe("AdminErrorBoundary", () => {
  it("catches a throwing child and renders readable reload UI", () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);

    render(
      <AdminErrorBoundary>
        <ThrowingChild />
      </AdminErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      /admin page hit an error/i,
    );
    expect(
      screen.getByRole("button", { name: /reload admin page/i }),
    ).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
