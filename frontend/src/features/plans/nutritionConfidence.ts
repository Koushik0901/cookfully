import { nutritionPresentation } from "../../components/cookfully/nutritionState";

export function nutritionConfidenceLabel(status: string, coverageRatio: string) {
  const coverage = Math.round(Number(coverageRatio) * 100);
  if (coverage < 90 && !["failed", "manual", "stale"].includes(status)) return "Needs review";
  return nutritionPresentation(status, status).label;
}
