import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PwaPrompts } from "./PwaPrompts";

function installEvent() {
  const event = new Event("beforeinstallprompt", { cancelable: true });
  Object.assign(event, {
    prompt: vi.fn().mockResolvedValue(undefined),
    userChoice: Promise.resolve({ outcome: "dismissed", platform: "web" }),
  });
  return event;
}

describe("PwaPrompts", () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value: "Mozilla/5.0 Chrome/140 Safari/537.36",
    });
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
  });

  it("does not offer installation before a completed study session", () => {
    render(<PwaPrompts />);
    window.dispatchEvent(installEvent());
    expect(screen.queryByText(/add Jalɛ to your home screen/i)).not
      .toBeInTheDocument();
  });

  it("does not offer installation in standalone mode", () => {
    localStorage.setItem("jale:completed-study-session", "true");
    vi.mocked(matchMedia).mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList);
    render(<PwaPrompts />);
    window.dispatchEvent(installEvent());
    expect(screen.queryByText(/add Jalɛ to your home screen/i)).not
      .toBeInTheDocument();
  });

  it("shows iOS Safari manual instructions after a completed session", () => {
    localStorage.setItem("jale:completed-study-session", "true");
    Object.defineProperty(navigator, "userAgent", {
      configurable: true,
      value: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
    });
    render(<PwaPrompts />);
    expect(screen.getByText(/tap share, then add to home screen/i))
      .toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^add$/i })).not
      .toBeInTheDocument();
  });
});
