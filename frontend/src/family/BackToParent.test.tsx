import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { setUiLanguage } from "../i18n/useUiStrings";
import { BackToParent } from "./BackToParent";
import { switchProfile } from "./switchProfile";

vi.mock("../lib/api");
vi.mock("./switchProfile");

function mockApi(hasPin: boolean, valid = true) {
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path === "/v1/me/pin") return { has_pin: hasPin } as never;
    return { valid } as never;
  });
}

describe("back to parent", () => {
  beforeEach(() => {
    setUiLanguage("eng");
    vi.mocked(switchProfile).mockReset().mockResolvedValue(undefined);
  });

  it("leaves child mode straight away when no PIN is set", async () => {
    mockApi(false);
    render(<BackToParent />);
    const button = await screen.findByRole("button", {
      name: "Back to parent",
    });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await waitFor(() => expect(switchProfile).toHaveBeenCalledWith(null));
  });

  it("keeps the lock on when the PIN is wrong", async () => {
    mockApi(true, false);
    render(<BackToParent />);
    const button = await screen.findByRole("button", {
      name: "Back to parent",
    });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await userEvent.type(screen.getByLabelText("Enter parent PIN"), "9999");
    await userEvent.click(screen.getByRole("button", { name: "Unlock" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That PIN is not correct.",
    );
    expect(switchProfile).not.toHaveBeenCalled();
  });

  it("leaves child mode after the right PIN", async () => {
    mockApi(true, true);
    render(<BackToParent />);
    const button = await screen.findByRole("button", {
      name: "Back to parent",
    });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    await userEvent.type(screen.getByLabelText("Enter parent PIN"), "1234");
    await userEvent.click(screen.getByRole("button", { name: "Unlock" }));
    await waitFor(() => expect(switchProfile).toHaveBeenCalledWith(null));
  });

  it("explains when the device is offline and progress is unsent", async () => {
    mockApi(false);
    vi.mocked(switchProfile).mockRejectedValue(new Error("offline"));
    render(<BackToParent />);
    const button = await screen.findByRole("button", {
      name: "Back to parent",
    });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Connect to the internet/,
    );
  });
});
