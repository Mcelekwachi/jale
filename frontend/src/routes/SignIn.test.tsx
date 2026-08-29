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
    signInWithPassword: vi.fn().mockResolvedValue(undefined),
    signInWithGoogle: vi.fn().mockResolvedValue(undefined),
    signOut: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

describe("SignIn", () => {
  it("renders enabled Google sign-in first as the primary action", () => {
    vi.stubEnv("VITE_GOOGLE_ENABLED", "true");
    mockedUseAuth.mockReturnValue(authValue());
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );

    const google = screen.getByRole("button", {
      name: /continue with google/i,
    });
    const email = screen.getByLabelText(/email address/i);
    const magicLink = screen.getByRole("button", { name: /send magic link/i });

    expect(
      google.compareDocumentPosition(email) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(google).toHaveClass("bg-indigo-deep");
    expect(magicLink).not.toHaveClass("bg-indigo-deep");
  });

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

  it("hides Google auth and its divider unless explicitly enabled", () => {
    vi.stubEnv("VITE_GOOGLE_ENABLED", "false");
    mockedUseAuth.mockReturnValue(authValue());
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("button", { name: /continue with google/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/or continue with email/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /send magic link/i }),
    ).toHaveClass("bg-indigo-deep");
  });

  it("toggles from the magic-link form to the password form", async () => {
    mockedUseAuth.mockReturnValue(authValue());
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );

    await userEvent.click(
      screen.getByRole("button", { name: /sign in with a password instead/i }),
    );

    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^sign in$/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /send magic link/i }),
    ).not.toBeInTheDocument();
  });

  it("submits the entered email and password", async () => {
    const signInWithPassword = vi.fn().mockResolvedValue(undefined);
    mockedUseAuth.mockReturnValue(authValue({ signInWithPassword }));
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sign in with a password instead/i }),
    );
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "secret-pass");

    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(signInWithPassword).toHaveBeenCalledWith(
      "ada@example.com",
      "secret-pass",
    );
  });

  it("shows a generic credential error and preserves password mode and email", async () => {
    const signInWithPassword = vi
      .fn()
      .mockRejectedValue(
        new Error("Invalid login credentials: user does not exist"),
      );
    mockedUseAuth.mockReturnValue(authValue({ signInWithPassword }));
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sign in with a password instead/i }),
    );
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrong-password");

    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(
      await screen.findByText("That email or password is not correct."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/user does not exist/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toHaveValue("ada@example.com");
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("toggles back to the magic-link form", async () => {
    mockedUseAuth.mockReturnValue(authValue());
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /sign in with a password instead/i }),
    );

    await userEvent.click(
      screen.getByRole("button", { name: /use a magic link instead/i }),
    );

    expect(
      screen.getByRole("button", { name: /send magic link/i }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  });

  it("explains that sign-in needs a connection when offline", async () => {
    Object.defineProperty(navigator, "onLine", {
      configurable: true,
      value: false,
    });
    const signInWithEmail = vi.fn();
    mockedUseAuth.mockReturnValue(authValue({ signInWithEmail }));
    render(
      <MemoryRouter>
        <SignIn />
      </MemoryRouter>,
    );
    await userEvent.type(screen.getByLabelText(/email/i), "ada@example.com");
    await userEvent.click(screen.getByRole("button", { name: /send magic link/i }));

    expect(screen.getByText(/sign-in requires an internet connection/i))
      .toBeInTheDocument();
    expect(signInWithEmail).not.toHaveBeenCalled();
  });
});
