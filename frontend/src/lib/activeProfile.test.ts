import type { Session } from "@supabase/supabase-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getActiveProfileId, setActiveProfileId } from "./activeProfile";
import { apiFetch } from "./api";
import { supabase } from "./supabase";

vi.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn(),
      refreshSession: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

describe("active child profile", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: { access_token: "token" } as Session },
      error: null,
    });
  });
  afterEach(() => setActiveProfileId(null));

  it("sends X-Profile-Id only while a child profile is selected", async () => {
    vi.mocked(fetch).mockImplementation(
      async () => new Response(JSON.stringify({}), { status: 200 }),
    );
    await apiFetch("/v1/me", { authenticated: true });
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).not.toHaveProperty(
      "x-profile-id",
    );

    setActiveProfileId("child-1");
    await apiFetch("/v1/me", { authenticated: true });
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.headers).toMatchObject({
      "x-profile-id": "child-1",
    });
  });

  it("never sends the profile header on unauthenticated requests", async () => {
    vi.mocked(fetch).mockImplementation(
      async () => new Response(JSON.stringify({}), { status: 200 }),
    );
    setActiveProfileId("child-1");
    await apiFetch("/v1/languages/meta");
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).not.toHaveProperty(
      "x-profile-id",
    );
  });

  it("falls back to the parent when the selected profile no longer exists", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Profile not found" }), {
        status: 404,
      }),
    );
    setActiveProfileId("deleted-child");
    await expect(
      apiFetch("/v1/me", { authenticated: true }),
    ).rejects.toMatchObject({ status: 404 });
    expect(getActiveProfileId()).toBeNull();
  });
});
