import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { SignIn } from "./SignIn";
import { useAuth } from "../auth/useAuth";

vi.mock("../auth/useAuth");

const mockedUseAuth = vi.mocked(useAuth);

function authValue(
  overrides: Partial<ReturnType<typeof useAuth>> = {},
): ReturnType<typeof useAuth> {
  return {
    loading: false,
    session: null,
    user: null,
    signInWithEmail: vi.fn().mockResolvedValue(undefined),
    signInWithGoogle: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe("SignIn", () => {
  it("shows a check-your-email state after sending a magic link", async () => {
    mockedUseAuth.mockReturnValue(authValue());
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.click(
      screen.getByRole("button", { name: /send magic link/i }),
    );
    expect(await screen.findByText(/check your email/i)).toBeInTheDocument();
  });

  it("shows a friendly message when Google auth is not enabled", async () => {
    mockedUseAuth.mockReturnValue(
      authValue({
        signInWithGoogle: vi
          .fn()
          .mockRejectedValue(
            new Error("Unsupported provider: provider is not enabled"),
          ),
      }),
    );
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /continue with google/i }),
    );
    expect(
      await screen.findByText("Google sign-in is not available yet"),
    ).toBeInTheDocument();
  });
});
