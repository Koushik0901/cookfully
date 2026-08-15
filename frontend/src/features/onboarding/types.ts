export type OnboardingAction = "manual_recipe" | "import_recipe" | "view_plan";

export type ReferenceDataChoice = "both" | "foundation_sr_legacy" | "none";

export type OnboardingState = {
  state: "pending" | "completed" | "dismissed";
  firstAction: OnboardingAction | null;
  referenceDataChoice: ReferenceDataChoice | null;
  resolvedAt: string | null;
  version: number;
};
