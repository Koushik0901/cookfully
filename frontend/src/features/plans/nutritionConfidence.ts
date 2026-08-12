export function nutritionConfidenceLabel(status: string, coverageRatio: string) {
  const coverage = Math.round(Number(coverageRatio) * 100);
  if (status === "manual") return "Nutrition reviewed";
  if (status === "failed") return "Nutrition unavailable";
  if (status === "stale") return "Nutrition needs a refresh";
  if (coverage >= 90) return "Nutrition estimate supported";
  return "Nutrition estimate incomplete";
}
