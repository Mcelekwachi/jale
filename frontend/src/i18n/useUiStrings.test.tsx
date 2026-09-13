import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { setUiLanguage, useUiStrings } from "./useUiStrings";

describe("useUiStrings", () => {
  afterEach(() => setUiLanguage("eng"));

  it("returns Dutch strings for the Dutch meta-language", () => {
    setUiLanguage("nld");
    const { result } = renderHook(() => useUiStrings());
    expect(result.current.home.continueCta).toBe("Doorgaan");
  });

  it.each(["eng", null, undefined, "fra"])(
    "returns English strings for %s",
    (language) => {
      setUiLanguage(language);
      const { result } = renderHook(() => useUiStrings());
      expect(result.current.home.continueCta).toBe("Continue");
    },
  );

  it("reacts when the current meta-language changes", () => {
    const { result } = renderHook(() => useUiStrings());
    act(() => setUiLanguage("nld"));
    expect(result.current.home.continueCta).toBe("Doorgaan");
  });

  it("falls back to English for a key missing from Dutch", () => {
    setUiLanguage("nld");
    const { result } = renderHook(() => useUiStrings());
    expect(result.current.onboarding.heritageSpeaker).toBe(
      "Igbo heritage speaker",
    );
  });

  it("uses the Dutch browser locale when no preference is cached", async () => {
    localStorage.clear();
    const language = vi
      .spyOn(window.navigator, "language", "get")
      .mockReturnValue("nl-NL");
    vi.resetModules();

    const fresh = await import("./useUiStrings");

    expect(fresh.getUiStrings().home.continueCta).toBe("Doorgaan");
    fresh.setUiLanguage("eng");
    language.mockRestore();
  });
});
