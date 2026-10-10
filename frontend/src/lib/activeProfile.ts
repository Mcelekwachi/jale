import { useSyncExternalStore } from "react";

// The child profile the parent is currently using on this device, if any.
// apiFetch sends it as X-Profile-Id; the backend only honours the parent's own
// children, so a stale or forged id can never reach anyone else's data.
const KEY = "jale:active-profile";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

let current = read();

export function getActiveProfileId(): string | null {
  return current;
}

export function setActiveProfileId(id: string | null): void {
  current = id;
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {
    // Private mode: the selection simply lasts until reload.
  }
  listeners.forEach((listener) => listener());
}

export function useActiveProfileId(): string | null {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
    () => null,
  );
}
