import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UpdatePrompt } from "./UpdatePrompt";

const update = vi.fn().mockResolvedValue(undefined);
let needRefresh: (() => void) | undefined;
vi.mock("virtual:pwa-register", () => ({
  registerSW: vi.fn((options: { onNeedRefresh: () => void }) => {
    needRefresh = options.onNeedRefresh;
    return update;
  }),
}));

describe("UpdatePrompt", () => {
  it("waits for the learner to choose Reload before applying an update", async () => {
    render(<UpdatePrompt />);
    expect(update).not.toHaveBeenCalled();
    act(() => needRefresh?.());
    expect(screen.getByText(/update available/i)).toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /reload/i }));
    expect(update).toHaveBeenCalledWith(true);
  });
});
