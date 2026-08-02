import { getEnvironment } from "./env";
import { supabase } from "./supabase";

const REQUEST_TIMEOUT_MS = 90_000;
const SLOW_REQUEST_MS = 5_000;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

export interface ApiFetchOptions extends RequestInit {
  authenticated?: boolean;
  onSlowChange?: (slow: boolean) => void;
}

async function responseDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.clone().json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
  } catch {
    // The status text below remains useful for non-JSON proxy errors.
  }
  return response.statusText || `Request failed with status ${response.status}`;
}

function redirectToSignIn(): void {
  window.history.replaceState({}, "", "/signin");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const {
    authenticated = false,
    onSlowChange,
    headers: initialHeaders,
    signal,
    ...request
  } = options;
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort(signal?.reason);
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  const timeout = window.setTimeout(
    () => controller.abort("API request timed out"),
    REQUEST_TIMEOUT_MS,
  );
  const slowTimer = window.setTimeout(
    () => onSlowChange?.(true),
    SLOW_REQUEST_MS,
  );
  const url = `${getEnvironment().apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;

  const send = async (accessToken?: string): Promise<Response> => {
    const headers = new Headers(initialHeaders);
    headers.set("Accept", "application/json");
    if (request.body && !headers.has("Content-Type"))
      headers.set("Content-Type", "application/json");
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    return fetch(url, {
      ...request,
      headers: Object.fromEntries(headers.entries()),
      signal: controller.signal,
    });
  };

  try {
    let accessToken: string | undefined;
    if (authenticated) {
      const { data, error } = await supabase.auth.getSession();
      if (error) throw error;
      accessToken = data.session?.access_token;
    }

    let response = await send(accessToken);
    if (authenticated && response.status === 401) {
      const { data, error } = await supabase.auth.refreshSession();
      if (!error && data.session)
        response = await send(data.session.access_token);
      if (error || !data.session || response.status === 401) {
        await supabase.auth.signOut();
        redirectToSignIn();
      }
    }

    if (!response.ok)
      throw new ApiError(response.status, await responseDetail(response));
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        408,
        "The server took too long to respond. Please try again.",
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    window.clearTimeout(slowTimer);
    signal?.removeEventListener("abort", abortFromCaller);
    onSlowChange?.(false);
  }
}
