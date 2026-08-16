import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AudioButton } from "./AudioButton";

const url = "https://example.test/audio.mp3";

describe("AudioButton", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("disables missing audio even when a URL is present", () => {
    render(<AudioButton url={url} state="missing" />);

    expect(
      screen.getByRole("button", { name: /audio coming soon/i }),
    ).toBeDisabled();
  });

  it("plays placeholder audio and shows its marker", async () => {
    const play = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("Audio", vi.fn(() => ({ play })));
    render(<AudioButton url={url} state="placeholder" />);

    await userEvent.click(screen.getByRole("button", { name: /play audio/i }));

    expect(screen.getByRole("button", { name: /sample/i })).toBeEnabled();
    expect(play).toHaveBeenCalledOnce();
  });

  it("plays verified audio without a placeholder marker", async () => {
    const play = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("Audio", vi.fn(() => ({ play })));
    render(<AudioButton url={url} state="verified" />);

    const button = screen.getByRole("button", { name: /play audio/i });
    await userEvent.click(button);

    expect(button).not.toHaveTextContent(/sample/i);
    expect(play).toHaveBeenCalledOnce();
  });

  it("disables verified audio when its URL is null", () => {
    render(<AudioButton url={null} state="verified" />);

    expect(
      screen.getByRole("button", { name: /audio coming soon/i }),
    ).toBeDisabled();
  });
});
