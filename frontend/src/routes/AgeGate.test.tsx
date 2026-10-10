import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { setUiLanguage } from "../i18n/useUiStrings";
import { AgeGate } from "./AgeGate";

const signOut = vi.fn();
vi.mock("../auth/useAuth", () => ({ useAuth: () => ({ signOut }) }));
vi.mock("../lib/api");

function renderGate() {
  render(
    <MemoryRouter initialEntries={["/age"]}>
      <Routes>
        <Route path="/age" element={<AgeGate />} />
        <Route path="/" element={<p>home</p>} />
        <Route path="/settings" element={<p>settings</p>} />
        <Route path="/signin" element={<p>sign in</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("age gate", () => {
  beforeEach(() => {
    setUiLanguage("eng");
    vi.mocked(apiFetch)
      .mockReset()
      .mockResolvedValue(undefined as never);
    signOut.mockReset().mockResolvedValue(undefined);
  });

  it("confirms 16+ and continues to home", async () => {
    renderGate();
    await userEvent.click(screen.getByRole("button", { name: /16 or older/ }));
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/me/age",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await screen.findByText("home")).toBeInTheDocument();
  });

  it("sends a parent to settings to add a child", async () => {
    renderGate();
    await userEvent.click(
      screen.getByRole("button", { name: /parent or guardian setting/ }),
    );
    expect(await screen.findByText("settings")).toBeInTheDocument();
  });

  it("removes an under-16's details and signs them out", async () => {
    renderGate();
    await userEvent.click(screen.getByRole("button", { name: /under 16/ }));
    expect(apiFetch).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: /Remove my details/ }),
    );
    await waitFor(() => expect(signOut).toHaveBeenCalled());
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/me?confirm=true",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(await screen.findByText("sign in")).toBeInTheDocument();
  });
});
