import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      {
        id: 8,
        reason: "other",
        note: "Needs review",
        reporter_id: "user-3",
        status: "open",
        created_at: "2026-08-14T00:00:00Z",
        meta_language: null,
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
    expect(screen.getAllByText("wrong translation")).not.toHaveLength(0);
    expect(container).not.toBeEmptyDOMElement();
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/v1/admin/flags", {
      authenticated: true,
    });
  });

  it("resolves a flag with the correct request and removes it without reloading", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(profile("admin") as never)
      .mockResolvedValueOnce(queue as never)
      .mockResolvedValueOnce({} as never);
    render(<AdminRoute />);

    await user.type(
      await screen.findByLabelText("Resolution note for flag 7"),
      "Fixed",
    );
    await user.click(screen.getByRole("button", { name: "Resolve flag 7" }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenLastCalledWith("/v1/admin/flags/7", {
        authenticated: true,
        method: "PATCH",
        body: JSON.stringify({ status: "resolved", resolution_note: "Fixed" }),
      }),
    );
    expect(screen.queryByText("wrong translation")).not.toBeInTheDocument();
    expect(screen.getByText("Flag resolved")).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledTimes(3);
  });

  it("rejects with a note and blocks rejection without one", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(profile("admin") as never)
      .mockResolvedValueOnce(queue as never)
      .mockResolvedValueOnce({} as never);
    render(<AdminRoute />);

    await user.click(
      await screen.findByRole("button", { name: "Reject flag 7" }),
    );
    expect(
      screen.getByText("A resolution note is required to reject a flag"),
    ).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledTimes(2);

    await user.type(
      screen.getByLabelText("Resolution note for flag 7"),
      "Not reproducible",
    );
    await user.click(screen.getByRole("button", { name: "Reject flag 7" }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenLastCalledWith("/v1/admin/flags/7", {
        authenticated: true,
        method: "PATCH",
        body: JSON.stringify({
          status: "rejected",
          resolution_note: "Not reproducible",
        }),
      }),
    );
  });

  it("resolves all flags for an item and removes the item", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(profile("admin") as never)
      .mockResolvedValueOnce(queue as never)
      .mockResolvedValueOnce({} as never);
    render(<AdminRoute />);

    await user.type(
      await screen.findByLabelText("Shared resolution note for Ndewo"),
      "Updated audio",
    );
    await user.click(
      screen.getByRole("button", { name: "Resolve all flags for Ndewo" }),
    );

    await waitFor(() =>
      expect(apiFetch).toHaveBeenLastCalledWith(
        "/v1/admin/content/42/flags/resolve",
        {
          authenticated: true,
          method: "POST",
          body: JSON.stringify({ resolution_note: "Updated audio" }),
        },
      ),
    );
    expect(screen.queryByText("Ndewo")).not.toBeInTheDocument();
    expect(screen.getByText("All flags resolved")).toBeInTheDocument();
  });

  it("handles a 409 as already resolved and refreshes the affected item", async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(profile("admin") as never)
      .mockResolvedValueOnce(queue as never)
      .mockRejectedValueOnce({ status: 409 })
      .mockResolvedValueOnce([] as never);
    render(<AdminRoute />);

    await user.click(
      await screen.findByRole("button", { name: "Resolve flag 7" }),
    );

    expect(
      await screen.findByText("This flag was already resolved"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("Ndewo")).not.toBeInTheDocument(),
    );
    expect(apiFetch).toHaveBeenLastCalledWith("/v1/admin/flags", {
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
