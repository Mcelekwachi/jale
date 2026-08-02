import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

vi.stubEnv("VITE_SUPABASE_URL", "https://test.supabase.co");
vi.stubEnv("VITE_SUPABASE_ANON_KEY", "test-anon-key");
vi.stubEnv("VITE_API_BASE_URL", "https://jale-api.onrender.com");

afterEach(() => {
  cleanup();
  window.history.replaceState({}, "", "/");
});
