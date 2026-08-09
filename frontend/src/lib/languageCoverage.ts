export function hasIncompleteCoverage(language: {
  translated_count?: number;
  total_count?: number;
}) {
  return (
    language.translated_count !== undefined &&
    language.total_count !== undefined &&
    language.translated_count < language.total_count
  );
}

export function coverageLabel(language: {
  translated_count?: number;
  total_count?: number;
}) {
  return hasIncompleteCoverage(language)
    ? `${language.translated_count}/${language.total_count} translated`
    : null;
}
