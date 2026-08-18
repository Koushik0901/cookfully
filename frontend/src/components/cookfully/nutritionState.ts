export type NutritionPresentationKey =
  | "ready"
  | "needs_review"
  | "updating"
  | "unavailable"
  | "manual";

export type NutritionPresentation = {
  key: NutritionPresentationKey;
  label: string;
  description: string;
};

const PRESENTATIONS: Record<NutritionPresentationKey, NutritionPresentation> = {
  ready: {
    key: "ready",
    label: "Ready",
    description: "This estimate is ready to use for planning.",
  },
  needs_review: {
    key: "needs_review",
    label: "Needs review",
    description: "The recipe is usable, but some nutrition evidence needs attention.",
  },
  updating: {
    key: "updating",
    label: "Updating",
    description: "Cookfully is still working on this estimate.",
  },
  unavailable: {
    key: "unavailable",
    label: "Unavailable",
    description: "A nutrition estimate is not currently available.",
  },
  manual: {
    key: "manual",
    label: "Manual",
    description: "These values were supplied or corrected by you.",
  },
};

export function nutritionPresentation(
  nutritionState: string,
  nutritionStatus?: string | null,
): NutritionPresentation {
  if (["stale", "partial"].includes(nutritionState)) return PRESENTATIONS.needs_review;
  if (["pending", "processing", "retry_wait"].includes(nutritionState)) return PRESENTATIONS.updating;
  if (["failed", "unavailable"].includes(nutritionState)) return PRESENTATIONS.unavailable;
  if (nutritionStatus === "manual") return PRESENTATIONS.manual;
  return PRESENTATIONS.ready;
}
