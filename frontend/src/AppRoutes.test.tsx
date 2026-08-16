import { render } from "@testing-library/react";
import { Outlet } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./auth/AuthProvider", () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("./auth/ProtectedRoute", () => ({ ProtectedRoute: () => <Outlet /> }));
vi.mock("./auth/OnboardingGuard", () => ({
  OnboardingGuard: () => <Outlet />,
}));
vi.mock("./routes/Admin", () => ({
  AdminErrorBoundary: ({ children }: { children: React.ReactNode }) => children,
  AdminRoute: ({ children }: { children?: React.ReactNode }) =>
    children ?? <main>Flag queue</main>,
}));
vi.mock("./routes/AdminContent", () => ({
  AdminContentList: () => <main>Content management</main>,
  AdminContentDetailRoute: () => <main>Edit content</main>,
}));
vi.mock("./routes/AuthCallback", () => ({
  AuthCallback: () => <main>Callback</main>,
}));
vi.mock("./routes/Home", () => ({ Home: () => <main>Home</main> }));
vi.mock("./routes/Onboarding", () => ({
  Onboarding: () => <main>Onboarding</main>,
}));
vi.mock("./routes/Settings", () => ({ Settings: () => <main>Settings</main> }));
vi.mock("./routes/SignIn", () => ({ SignIn: () => <main>Sign in</main> }));
vi.mock("./routes/Study", () => ({ Study: () => <main>Study</main> }));

describe("registered routes", () => {
  it.each([
    "/signin",
    "/auth/callback",
    "/admin",
    "/admin/content",
    "/admin/content/42",
    "/onboarding",
    "/onboarding/age",
    "/",
    "/settings",
    "/study/foundations/1",
  ])("never renders an empty document at %s", (path) => {
    window.history.replaceState({}, "", path);
    const { container } = render(<App />);
    expect(container).not.toBeEmptyDOMElement();
  });
});
