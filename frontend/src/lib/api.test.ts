import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Session, User } from "@supabase/supabase-js";

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

const auth = vi.mocked(supabase.auth);
const user: User = {
  id: "user-1",
  aud: "authenticated",
  role: "authenticated",
  email: "ada@example.com",
  app_metadata: {},
  user_metadata: {},
  created_at: "2026-08-02T00:00:00Z",
};

function session(accessToken: string): Session {
  return {
    access_token: accessToken,
    refresh_token: "refresh-token",
    expires_in: 3600,
    token_type: "bearer",
    user,
  };
}

describe("apiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.mocked(auth.getSession).mockResolvedValue({
      data: { session: session("fresh-token") },
      error: null,
    });
    vi.mocked(auth.refreshSession).mockResolvedValue({
      data: { session: session("refreshed-token"), user },
      error: null,
    });
    vi.mocked(auth.signOut).mockResolvedValue({ error: null });
  });

  it("reads and attaches the current bearer token", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await apiFetch<{ ok: boolean }>("/health", { authenticated: true });
    expect(fetch).toHaveBeenCalledWith(
      "https://jale-api.onrender.com/health",
      expect.objectContaining({
        headers: expect.objectContaining({
          authorization: "Bearer fresh-token",
        }),
      }),
    );
  });

  it("refreshes once after a 401 and retries with the rotated token", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "expired" }), { status: 401 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    await expect(
      apiFetch<{ ok: boolean }>("/v1/me", { authenticated: true }),
    ).resolves.toEqual({ ok: true });
    expect(auth.refreshSession).toHaveBeenCalledOnce();
    expect(fetch).toHaveBeenLastCalledWith(
      "https://jale-api.onrender.com/v1/me",
      expect.objectContaining({
        headers: expect.objectContaining({
          authorization: "Bearer refreshed-token",
        }),
      }),
    );
  });

  it("signs out after the single refreshed request is also unauthorized", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "still expired" }), {
        status: 401,
      }),
    );
    await expect(
      apiFetch("/v1/me", { authenticated: true }),
    ).rejects.toMatchObject({ status: 401 });
    expect(auth.refreshSession).toHaveBeenCalledOnce();
    expect(auth.signOut).toHaveBeenCalledOnce();
    expect(window.location.pathname).toBe("/signin");
  });

  it("throws an ApiError with the response status and detail", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
    );
    await expect(apiFetch("/missing")).rejects.toMatchObject({
      status: 404,
      detail: "Not found",
    });
  });
});
