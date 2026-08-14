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
});
