export function defaultMetaLanguage(
  locale = navigator.language,
): "eng" | "nld" {
  return locale.toLowerCase().startsWith("nl-") ? "nld" : "eng";
}
