import { useSyncExternalStore } from "react";

import { en, type UiStrings } from "./en";
import { nl, type DeepPartial } from "./nl";
import { defaultMetaLanguage } from "../lib/locale";

const UI_LANGUAGE_KEY = "jale:meta-language";
const listeners = new Set<() => void>();

type UiLanguage = "eng" | "nld";

function normalizeLanguage(language?: string | null): UiLanguage {
  return language === "nld" ? "nld" : "eng";
}

let currentLanguage = normalizeLanguage(
  typeof localStorage === "undefined"
    ? defaultMetaLanguage()
    : (localStorage.getItem(UI_LANGUAGE_KEY) ?? defaultMetaLanguage()),
);

function mergeWithEnglish<T extends Record<string, unknown>>(
  english: T,
  translated: DeepPartial<T>,
): T {
  return Object.fromEntries(
    Object.entries(english).map(([key, englishValue]) => {
      const translatedValue = translated[key as keyof T];
      if (typeof englishValue === "string") {
        return [
          key,
          typeof translatedValue === "string" ? translatedValue : englishValue,
        ];
      }
      return [
        key,
        mergeWithEnglish(
          englishValue as Record<string, unknown>,
          (translatedValue ?? {}) as DeepPartial<Record<string, unknown>>,
        ),
      ];
    }),
  ) as T;
}

const dutch = mergeWithEnglish(en, nl) as UiStrings;

export function setUiLanguage(language?: string | null): void {
  const next = normalizeLanguage(language);
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(UI_LANGUAGE_KEY, next);
  }
  if (next === currentLanguage) return;
  currentLanguage = next;
  listeners.forEach((listener) => listener());
}

export function useUiLanguage(): UiLanguage {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => currentLanguage,
    () => "eng",
  );
}

export function useUiStrings(): UiStrings {
  const language = useUiLanguage();
  return language === "nld" ? dutch : en;
}

export function getUiStrings(): UiStrings {
  return currentLanguage === "nld" ? dutch : en;
}
