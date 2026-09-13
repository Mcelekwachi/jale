import type { UiStrings } from "./en";

export type DeepPartial<T> = {
  [Key in keyof T]?: T[Key] extends string ? string : DeepPartial<T[Key]>;
};

export const nl = {
  shared: {
    loading: "Laden",
    pleaseWait: "Even geduld…",
  },
  home: {
    continueCta: "Doorgaan",
  },
  onboarding: {},
} satisfies DeepPartial<UiStrings>;
