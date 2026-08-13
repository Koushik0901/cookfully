export type OnboardingAction = "manual_recipe" | "import_recipe" | "view_plan";

export type OnboardingState = {
  state: "pending" | "completed" | "dismissed";
  firstAction: OnboardingAction | null;
  resolvedAt: string | null;
  version: number;
};
