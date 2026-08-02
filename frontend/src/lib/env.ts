export interface FrontendEnvironment {
  supabaseUrl: string;
  supabaseAnonKey: string;
  apiBaseUrl: string;
}

const keys = [
  "VITE_SUPABASE_URL",
  "VITE_SUPABASE_ANON_KEY",
  "VITE_API_BASE_URL",
] as const;

export function readEnvironment(
  source: Record<string, string | undefined>,
): FrontendEnvironment {
  const missing = keys.filter((key) => !source[key]?.trim());
  if (missing.length > 0) {
    throw new Error(
      `Missing frontend environment variables: ${missing.join(", ")}`,
    );
  }

  return {
    supabaseUrl: source.VITE_SUPABASE_URL!.trim(),
    supabaseAnonKey: source.VITE_SUPABASE_ANON_KEY!.trim(),
    apiBaseUrl: source.VITE_API_BASE_URL!.trim().replace(/\/$/, ""),
  };
}

export function getEnvironment(): FrontendEnvironment {
  return readEnvironment(import.meta.env);
}
