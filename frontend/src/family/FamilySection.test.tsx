import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../lib/api";
import { setUiLanguage } from "../i18n/useUiStrings";
import { FamilySection } from "./FamilySection";

vi.mock("../lib/api");
vi.mock("./switchProfile");

const ada = {
  id: "child-1",
  nickname: "Ada",
  birth_year: 2018,
  created_at: "2026-10-10T00:00:00Z",
};

function mockApi(children = [ada]) {
  vi.mocked(apiFetch).mockImplementation(async (path, options) => {
    if (path === "/v1/me/children" && options?.method === "POST")
      return { ...ada, id: "child-2", nickname: "Ben" } as never;
    if (path === "/v1/me/children") return children as never;
    if (path === "/v1/me/pin") return { has_pin: false } as never;
    return undefined as never;
  });
}

describe("family section", () => {
  beforeEach(() => {
    setUiLanguage("eng");
    vi.mocked(apiFetch).mockReset();
  });

  it("lists children and needs the consent box before adding one", async () => {
    mockApi();
    render(<FamilySection onAccountDeleted={vi.fn()} />);
    expect(await screen.findByText(/Ada · 2018/)).toBeInTheDocument();

    const add = screen.getByRole("button", { name: "Add child" });
    await userEvent.type(screen.getByLabelText(/Nickname/), "Ben");
    expect(add).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    expect(add).toBeEnabled();

    await userEvent.click(add);
    expect(await screen.findByText(/Ben · 2018/)).toBeInTheDocument();
    const post = vi
      .mocked(apiFetch)
      .mock.calls.find(([, options]) => options?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      nickname: "Ben",
      consent: true,
    });
  });

  it("asks before deleting a child profile", async () => {
    mockApi();
    render(<FamilySection onAccountDeleted={vi.fn()} />);
    await screen.findByText(/Ada · 2018/);
    await userEvent.click(
      screen.getByRole("button", { name: "Delete profile" }),
    );
    expect(apiFetch).not.toHaveBeenCalledWith(
      "/v1/me/children/child-1",
      expect.anything(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() =>
      expect(screen.queryByText(/Ada · 2018/)).not.toBeInTheDocument(),
    );
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/me/children/child-1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("asks before deleting the whole account", async () => {
    mockApi([]);
    const onDeleted = vi.fn();
    render(<FamilySection onAccountDeleted={onDeleted} />);
    await screen.findByText("No child profiles yet.");
    await userEvent.click(
      screen.getByRole("button", { name: "Delete my account" }),
    );
    expect(onDeleted).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/me?confirm=true",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
