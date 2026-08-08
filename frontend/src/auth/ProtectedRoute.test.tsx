import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ProtectedRoute } from "./ProtectedRoute";
import { useAuth } from "./useAuth";

vi.mock("./useAuth");

const mockedUseAuth = vi.mocked(useAuth);

function authValue(
  overrides: Partial<ReturnType<typeof useAuth>>,
): ReturnType<typeof useAuth> {
  return {
    loading: false,
    session: null,
    user: null,
    signInWithEmail: vi.fn().mockResolvedValue(undefined),
    signInWithPassword: vi.fn().mockResolvedValue(undefined),
    signInWithGoogle: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

function SignInLocation() {
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  return <p>signin from {from ?? "unknown"}</p>;
}

function renderProtected(path = "/lesson?unit=2") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/signin" element={<SignInLocation />} />
        <Route element={<ProtectedRoute />}>
          <Route path="*" element={<p>protected content</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("shows a spinner while the first session is resolving", () => {
    mockedUseAuth.mockReturnValue(authValue({ loading: true }));
    renderProtected();
    expect(
      screen.getByRole("status", { name: /checking your session/i }),
    ).toBeInTheDocument();
  });

  it("redirects signed-out users and preserves the attempted path", () => {
    mockedUseAuth.mockReturnValue(authValue({}));
    renderProtected();
    expect(screen.getByText("signin from /lesson?unit=2")).toBeInTheDocument();
  });

  it("renders children for a signed-in user", () => {
    mockedUseAuth.mockReturnValue(
      authValue({
        session: { access_token: "token" },
        user: { id: "user-1" },
      }),
    );
    renderProtected();
    expect(screen.getByText("protected content")).toBeInTheDocument();
  });
});
